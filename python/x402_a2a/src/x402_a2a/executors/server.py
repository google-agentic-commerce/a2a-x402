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
"""Server-side executor for merchant implementations."""

import logging
from abc import ABCMeta, abstractmethod
from typing import Optional, Dict, List

from a2a.server.tasks import TaskUpdater
from a2a.types import Role, TaskStatusUpdateEvent

from .base import x402BaseExecutor
from ._payment_event_queue import PaymentEventQueue
from ..types import (
    AgentExecutor,
    RequestContext,
    EventQueue,
    PaymentStatus,
    PaymentRequirements,
    SettleResponse,
    x402ExtensionConfig,
    x402ErrorCode,
    x402PaymentRequiredException,
    PaymentPayload,
    Task,
    TaskStatus,
    TaskState,
    x402PaymentRequiredResponse,
    VerifyResponse,
    x402Metadata,
)


logger = logging.getLogger(__name__)


class x402ServerExecutor(x402BaseExecutor, metaclass=ABCMeta):
    """Server-side payment middleware for merchant agents.

    Exception-based payment requirements:
    Delegate agents throw x402PaymentRequiredException to request payment dynamically.

    Example:
        # Create executor (no configuration needed)
        server = x402ServerExecutor(my_agent, config)

        # In your delegate agent:
        raise x402PaymentRequiredException.for_service(
            price="$1.00",
            pay_to_address="0x123...",
            resource="/premium-feature"
        )
    """

    def __init__(
        self,
        delegate: AgentExecutor,
        config: x402ExtensionConfig,
    ):
        """Initialize server executor.

        Args:
            delegate: Underlying agent executor for business logic
            config: x402 extension configuration
        """
        super().__init__(delegate, config)
        self._payment_requirements_store: Dict[str, List[PaymentRequirements]] = {}

    @abstractmethod
    async def verify_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """Verifies the payment with a facilitator."""
        raise NotImplementedError

    @abstractmethod
    async def settle_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """Settles the payment with a facilitator."""
        raise NotImplementedError

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Payment middleware: verify → execute service → settle."""
        if not context.task_id or not context.context_id:
            raise ValueError("Task ID and Context ID cannot be None")
        payment_status_task = (
            self.utils.get_payment_status_from_task(context.current_task)
            if context.current_task
            else None
        )
        payment_status_message = (
            self.utils.get_payment_status_from_message(context.message)
            if context.message
            else None
        )

        if (
            payment_status_task == PaymentStatus.PAYMENT_SUBMITTED
            or payment_status_message == PaymentStatus.PAYMENT_SUBMITTED
        ):
            return await self._process_paid_request(context, event_queue)

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        try:
            return await self._delegate.execute(context, event_queue)
        except x402PaymentRequiredException as e:
            await self._handle_payment_required_exception(e, context, event_queue)
            return

    async def _process_paid_request(
        self, context: RequestContext, event_queue: EventQueue
    ):
        """Process paid request: verify → execute → settle."""
        logger.info("Starting payment processing...")
        task = context.current_task
        if not task:
            logger.error("Task not found in context during payment processing.")
            raise ValueError("Task not found in context")

        # Keep receipt history independent of TaskManager status updates.
        current_task = task
        task = task.model_copy(deep=True)
        task.status.state = TaskState.working
        # The request handler moves the previous status message into history.
        # Its most recent receipt array is cumulative; do not concatenate it
        # with older snapshots or accept a receipt supplied by the client.
        if task.status.message is None:
            for message in reversed(task.history or []):
                # A payment submission can itself use role=agent. It is still
                # incoming data, not a previously issued payment receipt.
                if context.message and message.message_id == context.message.message_id:
                    continue
                if message.role == Role.agent and (message.metadata or {}).get(
                    x402Metadata.RECEIPTS_KEY
                ):
                    task.status.message = message.model_copy(deep=True)
                    task.status.message.metadata = {
                        x402Metadata.RECEIPTS_KEY: (message.metadata or {})[
                            x402Metadata.RECEIPTS_KEY
                        ]
                    }
                    break
        await TaskUpdater(event_queue, task.id, task.context_id).start_work(
            message=task.status.message.model_copy(deep=True)
            if task.status.message
            else None
        )

        logger.info(
            f"✅ Received payment payload. Beginning verification for task: {task.id}"
        )

        payment_payload = (
            self.utils.get_payment_payload(task)
            or self.utils.get_payment_payload_from_message(context.message)
            if context.message
            else None
        )
        if not payment_payload:
            logger.warning(
                "Payment payload missing from both task and message metadata."
            )
            return await self._fail_payment(
                task,
                x402ErrorCode.INVALID_SIGNATURE,
                "Missing payment data",
                event_queue,
            )

        logger.info(
            f"Retrieved payment payload: {payment_payload.model_dump_json(indent=2)}"
        )

        logger.info(
            f"Attempting to retrieve payment requirements for task ID: {task.id}"
        )
        payment_requirements = self._extract_payment_requirements_from_context(
            task, context
        )
        if not payment_requirements:
            logger.warning("Payment requirements missing from context.")
            return await self._fail_payment(
                task,
                x402ErrorCode.INVALID_SIGNATURE,
                "Missing payment requirements",
                event_queue,
            )

        logger.info(
            f"Retrieved payment requirements: {payment_requirements.model_dump_json(indent=2)}"
        )

        try:
            logger.info("Calling self.verify_payment...")
            verify_response = await self.verify_payment(
                payment_payload, payment_requirements
            )
            logger.info(
                f"Verification response: {verify_response.model_dump_json(indent=2)}"
            )
            if not verify_response.is_valid:
                logger.warning(
                    f"Payment verification failed: {verify_response.invalid_reason}"
                )
                return await self._fail_payment(
                    task,
                    x402ErrorCode.INVALID_SIGNATURE,
                    verify_response.invalid_reason or "Invalid payment",
                    event_queue,
                )
        except Exception as e:
            logger.error(f"Exception during payment verification: {e}", exc_info=True)
            return await self._fail_payment(
                task,
                x402ErrorCode.INVALID_SIGNATURE,
                f"Verification failed: {e}",
                event_queue,
            )

        logger.info("Payment verified successfully. Recording and updating task.")
        task = self.utils.record_payment_verified(task)
        # Add the verification status to the task metadata for the delegate agent.
        if not task.metadata:
            task.metadata = {}
        task.metadata["x402_payment_verified"] = True
        if current_task.metadata is None:
            current_task.metadata = {}
        current_task.metadata["x402_payment_verified"] = True
        current_task.status = task.status.model_copy(deep=True)
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=task.status.model_copy(deep=True),
                metadata={"x402_payment_verified": True},
                final=False,
            )
        )
        logger.info("Set x402_payment_verified=True in task.metadata")

        if task.status.message is not None and (
            not hasattr(task.status.message, "metadata")
            or not task.status.message.metadata
        ):
            task.status.message.metadata = {}
        payment_events = PaymentEventQueue(event_queue)
        try:
            logger.info("Executing delegate agent...")
            await self._delegate.execute(context, payment_events)
            logger.info("Delegate agent execution finished.")
        except Exception as e:
            logger.error(f"Exception during delegate execution: {e}", exc_info=True)
            return await self._fail_payment(
                task,
                x402ErrorCode.SETTLEMENT_FAILED,
                f"Service failed: {e}",
                event_queue,
            )

        logger.info("Delegate execution complete. Proceeding to settlement.")

        try:
            logger.info("Calling self.settle_payment...")
            settle_response = await self.settle_payment(
                payment_payload, payment_requirements
            )
            logger.info(
                f"Settlement response: {settle_response.model_dump_json(indent=2)}"
            )
            if settle_response.success:
                logger.info("Settlement successful. Recording payment success.")
                task = self.utils.record_payment_success(task, settle_response)

                self._payment_requirements_store.pop(task.id, None)
            else:
                logger.warning(f"Settlement failed: {settle_response.error_reason}")
                error_code = (
                    x402ErrorCode.INSUFFICIENT_FUNDS
                    if "insufficient" in (settle_response.error_reason or "").lower()
                    else x402ErrorCode.SETTLEMENT_FAILED
                )
                task = self.utils.record_payment_failure(
                    task, error_code, settle_response
                )

                self._payment_requirements_store.pop(task.id, None)
            await payment_events.publish_result(task, settle_response.success)
            logger.info("Settlement processing finished.")
        except Exception as e:
            logger.error(f"Exception during settlement: {e}", exc_info=True)
            await self._fail_payment(
                task,
                x402ErrorCode.SETTLEMENT_FAILED,
                f"Settlement failed: {e}",
                event_queue,
            )

    def _find_matching_payment_requirement(
        self,
        accepts_array: List[PaymentRequirements],
        payment_payload: PaymentPayload,
    ) -> Optional[PaymentRequirements]:
        """
        Finds a matching payment requirement from the stored list.
        Developers can override this method to implement custom matching logic.
        """
        logger.info("Searching for matching payment requirement...")
        for requirement in accepts_array:
            scheme_match = requirement.scheme == payment_payload.scheme
            network_match = requirement.network == payment_payload.network

            if scheme_match and network_match:
                logger.info("  => Found a matching payment requirement.")
                return requirement

        logger.warning(
            "No matching payment requirement found after checking all options."
        )
        return None

    def _extract_payment_requirements_from_context(
        self, task: Task, context: RequestContext
    ) -> Optional[PaymentRequirements]:
        """
        Extracts the matching payment requirements based on the payment payload.
        """
        accepts_array = self._payment_requirements_store.get(task.id)
        if not accepts_array:
            logger.warning(
                f"No payment requirements found in store for task ID: {task.id}"
            )
            return None

        payment_payload = (
            self.utils.get_payment_payload(task)
            or self.utils.get_payment_payload_from_message(context.message)
            if context.message
            else None
        )
        if not payment_payload:
            logger.warning("Could not extract payment payload from task or message.")
            return None

        return self._find_matching_payment_requirement(accepts_array, payment_payload)

    async def _handle_payment_required_exception(
        self,
        exception: x402PaymentRequiredException,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        """Handle x402PaymentRequiredException to request payment.

        Extracts payment requirements directly from the exception and creates
        a payment required response for the client.
        """
        task = context.current_task
        if not task:
            # If the task object isn't in the context (e.g., on the first turn),
            # create a temporary one using the IDs from the context. The TaskManager
            # will find the real task using the ID.
            if not context.task_id or not context.context_id:
                raise ValueError(
                    "Cannot handle payment exception: task_id or context_id is missing from the context."
                )

            task = Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.input_required),
                metadata={},
            )
        else:
            # Ensure the existing task is always in the input_required state
            task.status.state = TaskState.input_required

        # Extract payment requirements directly from the exception
        accepts_array = exception.get_accepts_array()
        error_message = str(exception)

        # Store payment requirements for later correlation
        self._payment_requirements_store[task.id] = accepts_array

        payment_required = x402PaymentRequiredResponse(
            x402_version=1, accepts=accepts_array, error=error_message
        )

        # Update task with payment requirements
        task = self.utils.create_payment_required_task(task, payment_required)

        # Send the payment required response
        await event_queue.enqueue_event(task)

    async def _fail_payment(
        self, task, error_code: str, error_reason: str, event_queue: EventQueue
    ):
        """Handle payment failure."""
        failure_response = SettleResponse(
            success=False, network="base", error_reason=error_reason
        )
        task = self.utils.record_payment_failure(task, error_code, failure_response)

        self._payment_requirements_store.pop(task.id, None)

        task.status.state = TaskState.failed
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=task.status.model_copy(deep=True),
                final=True,
            )
        )
