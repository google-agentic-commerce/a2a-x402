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
"""Payment gating tests for x402ServerExecutor."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.server.tasks import InMemoryTaskStore, TaskManager, TaskUpdater
from a2a.types import Message, Task, TaskState, TaskStatus, TextPart

from x402_a2a.executors.server import PAYMENT_VERIFIED_KEY, x402ServerExecutor
from x402_a2a.types import (
    PaymentPayload,
    PaymentRequirements,
    PaymentStatus,
    SettleResponse,
    VerifyResponse,
    x402Metadata,
    x402PaymentRequiredException,
)


class RecordingDelegate:
    """Delegate that records whether each call saw a verified payment."""

    def __init__(self, fail_on_paid_turn: bool = False):
        self.fail_on_paid_turn = fail_on_paid_turn
        self.saw_verified: list[bool] = []

    async def execute(self, context, event_queue):
        metadata = context.current_task.metadata or {}
        verified = bool(metadata.get(PAYMENT_VERIFIED_KEY))
        self.saw_verified.append(verified)
        if verified and self.fail_on_paid_turn:
            raise RuntimeError("delegate failed")

    async def cancel(self, context, event_queue):
        pass


class FakeServerExecutor(x402ServerExecutor):
    def __init__(self, delegate):
        super().__init__(delegate=delegate, config=MagicMock())
        self.verify_payment = AsyncMock(
            return_value=VerifyResponse(is_valid=True, payer="0x789")
        )
        self.settle_payment = AsyncMock(return_value=SettleResponse(success=True))

    async def verify_payment(self, payload, requirements):
        raise NotImplementedError

    async def settle_payment(self, payload, requirements):
        raise NotImplementedError


def _requirements() -> PaymentRequirements:
    return PaymentRequirements(
        scheme="exact",
        network="base-sepolia",
        max_amount_required="100",
        resource="/test",
        description="Test",
        mime_type="text/plain",
        pay_to="0x123",
        max_timeout_seconds=60,
        asset="0x456",
    )


def _payload(nonce: str = "0xdef") -> PaymentPayload:
    return PaymentPayload(
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
                "nonce": nonce,
            },
        },
    )


def _context(task: Task, metadata: dict) -> MagicMock:
    context = MagicMock()
    context.task_id = task.id
    context.context_id = task.context_id
    context.current_task = task
    context.message = Message(
        messageId="msg",
        role="user",
        parts=[TextPart(text="hello")],
        metadata=metadata,
    )
    return context


def _paid_context(executor: x402ServerExecutor, task: Task, nonce: str = "0xdef"):
    executor._payment_requirements_store[task.id] = [_requirements()]
    return _context(
        task,
        {
            x402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            x402Metadata.PAYLOAD_KEY: _payload(nonce).model_dump(by_alias=True),
        },
    )


def _new_task(task_id: str) -> Task:
    return Task(
        id=task_id,
        contextId="ctx",
        status=TaskStatus(state=TaskState.working),
        metadata={},
    )


@pytest.mark.asyncio
async def test_verified_flag_does_not_persist_after_paid_turn():
    delegate = RecordingDelegate()
    executor = FakeServerExecutor(delegate)
    task = _new_task("task-sticky")

    await executor.execute(_paid_context(executor, task), AsyncMock())
    assert PAYMENT_VERIFIED_KEY not in (task.metadata or {})

    # Later turns on the same task carry no payment and must not look paid.
    await executor.execute(_context(task, {}), AsyncMock())
    await executor.execute(_context(task, {}), AsyncMock())

    assert delegate.saw_verified == [True, False, False]
    executor.verify_payment.assert_called_once()
    executor.settle_payment.assert_called_once()


@pytest.mark.asyncio
async def test_verified_flag_cleared_when_delegate_fails():
    delegate = RecordingDelegate(fail_on_paid_turn=True)
    executor = FakeServerExecutor(delegate)
    task = _new_task("task-zero-cost")

    await executor.execute(_paid_context(executor, task), AsyncMock())
    executor.settle_payment.assert_not_called()
    assert PAYMENT_VERIFIED_KEY not in (task.metadata or {})

    await executor.execute(_context(task, {}), AsyncMock())
    assert delegate.saw_verified == [True, False]


@pytest.mark.asyncio
async def test_stale_verified_flag_is_ignored_on_unpaid_turn():
    delegate = RecordingDelegate()
    executor = FakeServerExecutor(delegate)
    task = _new_task("task-stale")
    assert task.metadata is not None
    task.metadata[PAYMENT_VERIFIED_KEY] = True

    await executor.execute(_context(task, {}), AsyncMock())

    assert delegate.saw_verified == [False]
    executor.verify_payment.assert_not_called()


@pytest.mark.asyncio
async def test_task_manager_persistence_across_turns_clears_verified_flag():
    """End-to-end check through a2a-sdk TaskManager + InMemoryTaskStore."""
    paid_deliveries: list[str] = []

    class GateDelegate:
        async def execute(self, context, event_queue):
            meta = (
                context.current_task.metadata if context.current_task else None
            ) or {}
            if not meta.get(PAYMENT_VERIFIED_KEY):
                raise x402PaymentRequiredException("item", _requirements())
            paid_deliveries.append(context.message.message_id)
            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            await updater.update_status(TaskState.input_required)

        async def cancel(self, context, event_queue):
            pass

    store = InMemoryTaskStore()
    executor = FakeServerExecutor(GateDelegate())

    async def run_turn(task_id: str, msg_id: str, metadata: dict) -> Task:
        msg = Message(
            messageId=msg_id,
            taskId=task_id,
            contextId="ctx-1",
            role="user",
            parts=[TextPart(text=msg_id)],
            metadata=metadata,
        )
        tm = TaskManager(
            task_id=task_id, context_id="ctx-1", task_store=store, initial_message=msg
        )
        task = await tm.get_task()
        if task:
            task = tm.update_with_message(msg, task)
        ctx = MagicMock()
        ctx.task_id = task_id
        ctx.context_id = "ctx-1"
        ctx.current_task = task
        ctx.message = msg
        queue = AsyncMock()
        queue.enqueue_event.side_effect = tm.process
        await executor.execute(ctx, queue)
        saved = await store.get(task_id)
        assert saved is not None
        return saved

    t1 = await run_turn("task-tm", "m1", {})
    assert t1.status.state == TaskState.input_required
    assert paid_deliveries == []

    t2 = await run_turn(
        "task-tm",
        "m2",
        {
            x402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            x402Metadata.PAYLOAD_KEY: _payload("0xdef").model_dump(by_alias=True),
        },
    )
    assert paid_deliveries == ["m2"]
    assert PAYMENT_VERIFIED_KEY not in (t2.metadata or {})

    t3 = await run_turn("task-tm", "m3", {})
    assert paid_deliveries == ["m2"]
    assert t3.status.message is not None
    assert t3.status.message.metadata is not None
    assert (
        t3.status.message.metadata.get(x402Metadata.STATUS_KEY)
        == PaymentStatus.PAYMENT_REQUIRED.value
    )
