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
"""Keep a paid response open until its settlement result can be delivered."""

from a2a.server.events import Event, EventQueue
from a2a.types import Message, Task, TaskState, TaskStatusUpdateEvent

from ..types import x402Metadata


class PaymentEventQueue(EventQueue):
    """Forward progress, but retain the delegate's response-ending event.

    The A2A consumer closes its queue on a final status, a Message, or a Task
    in an interrupt/terminal state. Forwarding those before settlement loses
    the receipt. Only one final event is retained; progress and artifacts are
    forwarded immediately, without an unbounded buffer or a background task.
    """

    def __init__(self, destination: EventQueue):
        super().__init__()
        self._destination = destination
        self._final_event: Event | None = None

    async def enqueue_event(self, event: Event) -> None:
        ends_response = (
            isinstance(event, Message)
            or (isinstance(event, TaskStatusUpdateEvent) and event.final)
            or (
                isinstance(event, (Task, TaskStatusUpdateEvent))
                and event.status.state
                in (
                    TaskState.completed,
                    TaskState.canceled,
                    TaskState.failed,
                    TaskState.rejected,
                    TaskState.unknown,
                    TaskState.input_required,
                    TaskState.auth_required,
                )
            )
        )
        if ends_response:
            self._final_event = event.model_copy(deep=True)
        else:
            await self._destination.enqueue_event(event.model_copy(deep=True))

    async def publish_result(self, payment_task: Task, success: bool) -> None:
        """Attach payment metadata before emitting a single final response."""
        payment_message = payment_task.status.message
        assert payment_message is not None
        event = self._final_event
        if event is None or (isinstance(event, Message) and not success):
            event = TaskStatusUpdateEvent(
                task_id=payment_task.id,
                context_id=payment_task.context_id,
                status=payment_task.status.model_copy(deep=True),
                final=True,
            )

        if isinstance(event, (Task, TaskStatusUpdateEvent)):
            if not success:
                event.status.state = TaskState.failed
            if isinstance(event, TaskStatusUpdateEvent):
                event.final = True
            if event.status.message is None:
                event.status.message = payment_message.model_copy(deep=True)
            message = event.status.message
        else:
            # The retained event can only be a Message, Task, or status update.
            assert isinstance(event, Message)
            message = event

        metadata = dict(message.metadata or {})
        payment_metadata = payment_message.metadata or {}
        for key in (
            x402Metadata.STATUS_KEY,
            x402Metadata.RECEIPTS_KEY,
            x402Metadata.ERROR_KEY,
            x402Metadata.PAYLOAD_KEY,
            x402Metadata.REQUIRED_KEY,
        ):
            metadata.pop(key, None)
            if key in payment_metadata:
                metadata[key] = payment_metadata[key]
        message.metadata = metadata
        await self._destination.enqueue_event(event)
