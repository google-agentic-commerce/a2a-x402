# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Payment completion must survive the real A2A event consumer."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    Artifact,
    Message,
    MessageSendParams,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from x402_a2a.core.utils import create_payment_submission_message
from x402_a2a.executors.server import x402ServerExecutor
from x402_a2a.types import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
    x402ExtensionConfig,
    x402Metadata,
)


class CopyingTaskStore(InMemoryTaskStore):
    """Model a persistent store: only save(), not mutation, writes state."""

    async def save(self, task):
        await super().save(task.model_copy(deep=True))

    async def get(self, task_id):
        task = await super().get(task_id)
        return task.model_copy(deep=True) if task else None


class ResultDelegate(AgentExecutor):
    def __init__(self, result_kind="status"):
        self.result_kind = result_kind

    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if (context.message.metadata or {}).get(x402Metadata.STATUS_KEY):
            assert context.current_task.metadata["x402_payment_verified"] is True
            assert (
                context.current_task.status.message.metadata[x402Metadata.STATUS_KEY]
                == "payment-verified"
            )
        await updater.add_artifact(
            [Part(root=TextPart(text="result chunk"))], artifact_id="result"
        )
        message = updater.new_agent_message(
            [Part(root=TextPart(text="Service result"))], metadata={"custom": "kept"}
        )
        if self.result_kind == "exception":
            raise RuntimeError("service unavailable")
        if self.result_kind == "task":
            await event_queue.enqueue_event(
                Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=TaskStatus(state=TaskState.completed, message=message),
                    artifacts=[
                        Artifact(
                            artifact_id="result",
                            parts=[Part(root=TextPart(text="result chunk"))],
                        )
                    ],
                )
            )
        elif self.result_kind == "message":
            await event_queue.enqueue_event(message)
        else:
            await updater.complete(message)

    async def cancel(self, context, event_queue):
        pass


class TestMerchant(x402ServerExecutor):
    __test__ = False

    async def verify_payment(self, payload, requirements):
        return VerifyResponse(is_valid=True, payer="0x789")

    async def settle_payment(self, payload, requirements):
        raise NotImplementedError


def setup_request(result_kind="status", task_state=TaskState.input_required):
    merchant = TestMerchant(ResultDelegate(result_kind), x402ExtensionConfig())
    old_receipt = {
        "success": True,
        "network": "base-sepolia",
        "transaction": "0xprevious",
    }
    task = Task(
        id="task-test",
        context_id="context-test",
        status=TaskStatus(
            state=task_state,
            message=Message(
                message_id="previous",
                role="agent",
                parts=[Part(root=TextPart(text="Pay"))],
                metadata={x402Metadata.RECEIPTS_KEY: [old_receipt]},
            ),
        ),
    )
    merchant._payment_requirements_store[task.id] = [
        PaymentRequirements(
            scheme="exact",
            network="base-sepolia",
            max_amount_required="100",
            resource="https://example.test/service",
            description="test",
            mime_type="text/plain",
            pay_to="0x123",
            max_timeout_seconds=60,
            asset="0x456",
        )
    ]
    payload = PaymentPayload(
        x402_version=1,
        scheme="exact",
        network="base-sepolia",
        payload={
            "signature": "0xabc",
            "authorization": {
                "from": "0x789",
                "to": "0x123",
                "value": "100",
                "valid_after": "0",
                "valid_before": "9999999999",
                "nonce": "0xdef",
            },
        },
    )
    message = create_payment_submission_message(task.id, payload)
    message.context_id = task.context_id
    # Client metadata must not replace the server's cumulative receipt history.
    message.metadata[x402Metadata.RECEIPTS_KEY] = [{"transaction": "forged"}]
    task.history = [task.status.message.model_copy(deep=True)]
    return merchant, task, MessageSendParams(message=message), old_receipt


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
@pytest.mark.parametrize("outcome", ["success", "failure", "exception"])
@pytest.mark.parametrize("result_kind", ["status", "task", "message"])
async def test_settlement_precedes_final_response(streaming, outcome, result_kind):
    merchant, task, request, old_receipt = setup_request(result_kind)
    store = CopyingTaskStore()
    await store.save(task)
    queues = InMemoryQueueManager()
    handler = DefaultRequestHandler(merchant, store, queue_manager=queues)
    entered = asyncio.Event()
    release = asyncio.Event()
    events = []

    async def settle(payload, requirements):
        entered.set()
        await release.wait()
        if outcome == "exception":
            raise RuntimeError("facilitator unavailable")
        return SettleResponse(
            success=outcome == "success",
            network="base-sepolia",
            transaction="0xsettled" if outcome == "success" else None,
            error_reason="rejected" if outcome == "failure" else None,
        )

    merchant.settle_payment = AsyncMock(side_effect=settle)

    async def consume():
        if streaming:
            async for event in handler.on_message_send_stream(request):
                events.append(event.model_copy(deep=True))
        else:
            events.append(
                (await handler.on_message_send(request)).model_copy(deep=True)
            )

    consumer = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        queue = await queues.get(task.id)
        await asyncio.wait_for(queue.queue.join(), 2)
        # No timing sleeps: every currently published event has been consumed.
        assert not queue.is_closed(), "delegate closed the response before settlement"
        before = await store.get(task.id)
        assert before.status.state != TaskState.completed
    finally:
        release.set()
        await asyncio.wait_for(consumer, 2)

    if streaming:
        terminal_events = [
            event
            for event in events
            if isinstance(event, Message)
            or (isinstance(event, TaskStatusUpdateEvent) and event.final)
            or (
                isinstance(event, Task)
                and event.status.state
                in (
                    TaskState.completed,
                    TaskState.failed,
                )
            )
        ]
        assert len(terminal_events) == 1
    assert task.id not in merchant._payment_requirements_store
    final = events[-1]
    message = final if isinstance(final, Message) else final.status.message
    assert message.metadata[x402Metadata.STATUS_KEY] == (
        "payment-completed" if outcome == "success" else "payment-failed"
    )
    receipts = message.metadata[x402Metadata.RECEIPTS_KEY]
    assert receipts[0] == old_receipt
    assert len(receipts) == 2
    assert receipts[-1]["success"] == (outcome == "success")
    if outcome == "success":
        assert message.parts[0].root.text == "Service result"
        assert message.metadata["custom"] == "kept"
    else:
        assert final.status.state == TaskState.failed
    if not isinstance(final, Message):
        saved = await store.get(task.id)
        assert saved.status.message.metadata[x402Metadata.RECEIPTS_KEY] == receipts
        assert saved.artifacts[0].parts[0].root.text == "result chunk"
    merchant.settle_payment.assert_awaited_once()


@pytest.mark.asyncio
async def test_delegate_exception_ends_response_without_settlement():
    merchant, task, request, old_receipt = setup_request("exception")
    merchant.settle_payment = AsyncMock()
    store = CopyingTaskStore()
    await store.save(task)
    result = await asyncio.wait_for(
        DefaultRequestHandler(merchant, store).on_message_send(request), 2
    )
    assert result.status.state == TaskState.failed
    assert result.status.message.metadata[x402Metadata.STATUS_KEY] == "payment-failed"
    assert result.status.message.metadata[x402Metadata.RECEIPTS_KEY][0] == old_receipt
    merchant.settle_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_unpaid_request_keeps_delegate_completion():
    merchant, task, request, _ = setup_request()
    request.message.metadata = {}
    merchant.verify_payment = AsyncMock()
    merchant.settle_payment = AsyncMock()
    store = CopyingTaskStore()
    await store.save(task)
    result = await asyncio.wait_for(
        DefaultRequestHandler(merchant, store).on_message_send(request), 2
    )
    assert result.status.state == TaskState.completed
    assert result.status.message.parts[0].root.text == "Service result"
    merchant.verify_payment.assert_not_awaited()
    merchant.settle_payment.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["verification", "payload", "requirements"])
async def test_invalid_payment_ends_response_without_running_service(invalid):
    merchant, task, request, _ = setup_request()
    merchant._delegate.execute = AsyncMock()
    merchant.settle_payment = AsyncMock()
    if invalid == "verification":
        merchant.verify_payment = AsyncMock(
            return_value=VerifyResponse(
                is_valid=False, payer="0x789", invalid_reason="invalid signature"
            )
        )
    elif invalid == "payload":
        request.message.metadata.pop(x402Metadata.PAYLOAD_KEY)
    else:
        merchant._payment_requirements_store.clear()
    store = CopyingTaskStore()
    await store.save(task)
    result = await asyncio.wait_for(
        DefaultRequestHandler(merchant, store).on_message_send(request), 2
    )
    assert result.status.state == TaskState.failed
    assert result.status.message.metadata[x402Metadata.STATUS_KEY] == "payment-failed"
    merchant._delegate.execute.assert_not_awaited()
    merchant.settle_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_during_settlement_does_not_release_completion():
    from a2a.server.agent_execution import RequestContext
    from a2a.server.events import EventQueue
    from a2a.types import TaskStatusUpdateEvent

    merchant, task, request, _ = setup_request()
    entered = asyncio.Event()

    async def settle(payload, requirements):
        entered.set()
        await asyncio.Event().wait()

    merchant.settle_payment = AsyncMock(side_effect=settle)
    queue = EventQueue()
    context = RequestContext(
        request=request, task_id=task.id, context_id=task.context_id, task=task
    )
    execution = asyncio.create_task(merchant.execute(context, queue))
    await asyncio.wait_for(entered.wait(), 2)
    execution.cancel()
    with pytest.raises(asyncio.CancelledError):
        await execution
    while not queue.queue.empty():
        event = await queue.dequeue_event(no_wait=True)
        assert not isinstance(event, Message)
        if isinstance(event, (Task, TaskStatusUpdateEvent)):
            assert event.status.state != TaskState.completed
        queue.task_done()
    # The outcome is unknown; do not invent a successful or failed receipt.
    assert task.id in merchant._payment_requirements_store


@pytest.mark.asyncio
async def test_progress_streams_with_queue_backpressure():
    from a2a.server.events import EventQueue

    class SmallQueueManager(InMemoryQueueManager):
        async def create_or_tap(self, task_id):
            queue = EventQueue(max_queue_size=1)
            await self.add(task_id, queue)
            return queue

    merchant, task, request, _ = setup_request()
    merchant.settle_payment = AsyncMock(
        return_value=SettleResponse(
            success=True, network="base-sepolia", transaction="0xsettled"
        )
    )
    store = CopyingTaskStore()
    await store.save(task)
    handler = DefaultRequestHandler(merchant, store, queue_manager=SmallQueueManager())

    async def collect():
        return [event async for event in handler.on_message_send_stream(request)]

    events = await asyncio.wait_for(collect(), 2)
    assert any(event.kind == "artifact-update" for event in events)
    assert (
        events[-1].status.message.metadata[x402Metadata.STATUS_KEY]
        == "payment-completed"
    )


@pytest.mark.asyncio
async def test_incoming_agent_message_does_not_replace_receipt_history():
    merchant, task, request, old_receipt = setup_request()
    request.message.role = "agent"
    merchant.settle_payment = AsyncMock(
        return_value=SettleResponse(
            success=True, network="base-sepolia", transaction="0xsettled"
        )
    )
    store = CopyingTaskStore()
    await store.save(task)
    result = await asyncio.wait_for(
        DefaultRequestHandler(merchant, store).on_message_send(request), 2
    )
    receipts = result.status.message.metadata[x402Metadata.RECEIPTS_KEY]
    assert receipts[0] == old_receipt
    assert len(receipts) == 2
