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

import json
import logging
from abc import ABCMeta, abstractmethod
from pathlib import Path
from tempfile import gettempdir
from typing import Optional, Dict, List

from a2a.types import Task, TaskState, TaskStatus
from x402.common import find_matching_payment_requirements
from a2a.server.tasks import TaskUpdater

from .base import x402BaseExecutor
from ..core import verify_payment, settle_payment
from ..types import (
    AgentExecutor,
    RequestContext,
    EventQueue,
    PaymentStatus,
    PaymentRequirements,
    SettleResponse,
    x402ExtensionConfig,
    FacilitatorClient,
    x402ErrorCode,
    x402PaymentRequiredException,
    Message,
    PaymentPayload,
    Task,
    TaskStatus,
    TaskState,
    x402PaymentRequiredResponse,
    VerifyResponse
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
    
    # Class-level store to persist across requests for a single server instance.
    _payment_requirements_store: Dict[str, List[PaymentRequirements]] = {}
    
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
    
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Payment middleware: verify → execute service → settle."""
        # The wrapper MUST take responsibility for starting the task.
        # This ensures the task exists in the TaskManager before the delegate runs.
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if not context.current_task:
            await updater.submit()
        await updater.start_work()


        task = context.current_task or Task(
            id=context.task_id,
            contextId=context.context_id,
            status=TaskStatus(state=TaskState.working),
        )
        status = self.utils.get_payment_status(task)


        if (
            self.utils.get_payment_status_from_task(context.current_task)
            == PaymentStatus.PAYMENT_SUBMITTED
            or self.utils.get_payment_status_from_message(context.message)
            == PaymentStatus.PAYMENT_SUBMITTED
        ):
            return await self._process_paid_request(context, event_queue)
        
        try:
            return await self._delegate.execute(context, event_queue)
        except x402PaymentRequiredException as e:
            await self._handle_payment_required_exception(e, context, event_queue)
            return
    
    async def _process_paid_request(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Process paid request: verify → execute → settle."""
        logger.info("Starting payment processing...")
        task = context.current_task
        if not task:
            logger.error("Task not found in context during payment processing.")
            raise ValueError("Task not found in context")

        logger.info(f"✅ Received payment payload. Beginning verification for task: {task.id}")

        payment_payload = self.utils.get_payment_payload(
            task
        ) or self.utils.get_payment_payload_from_message(context.message)
        if not payment_payload:
            logger.warning("Payment payload missing from both task and message metadata.")
            return await self._fail_payment(task, x402ErrorCode.INVALID_SIGNATURE, "Missing payment data", event_queue)
        
        logger.info(f"Retrieved payment payload: {payment_payload.model_dump_json(indent=2)}")

        logger.info(f"Attempting to retrieve payment requirements for task ID: {task.id}")
        payment_requirements = self._extract_payment_requirements_from_context(
            task, context
        )
        if not payment_requirements:
            logger.warning("Payment requirements missing from context.")
            return await self._fail_payment(task, x402ErrorCode.INVALID_SIGNATURE, "Missing payment requirements", event_queue)
        
        logger.info(f"Retrieved payment requirements: {payment_requirements.model_dump_json(indent=2)}")
        
        try:
            logger.info("Calling self.verify_payment...")
            verify_response = await self.verify_payment(
                payment_payload, payment_requirements
            )
            logger.info(f"Verification response: {verify_response.model_dump_json(indent=2)}")
            if not verify_response.is_valid:
                logger.warning(f"Payment verification failed: {verify_response.invalid_reason}")
                return await self._fail_payment(task, x402ErrorCode.INVALID_SIGNATURE, verify_response.invalid_reason or "Invalid payment", event_queue)
        except Exception as e:
            logger.error(f"Exception during payment verification: {e}", exc_info=True)
            return await self._fail_payment(task, x402ErrorCode.INVALID_SIGNATURE, f"Verification failed: {e}", event_queue)
        
        logger.info("Payment verified successfully. Recording and updating task.")
        task = self.utils.record_payment_verified(task)
        await event_queue.enqueue_event(task)

        # Add the verification status to the task metadata for the delegate agent.
        if not task.metadata:
            task.metadata = {}
        task.metadata["x402_payment_verified"] = True
        logger.info("Set x402_payment_verified=True in task.metadata")

        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}
        try:
            logger.info("Executing delegate agent...")
            await self._delegate.execute(context, event_queue)
            logger.info("Delegate agent execution finished.")
        except Exception as e:
            logger.error(f"Exception during delegate execution: {e}", exc_info=True)
            return await self._fail_payment(task, x402ErrorCode.SETTLEMENT_FAILED, f"Service failed: {e}", event_queue)
        
        logger.info("Delegate execution complete. Proceeding to settlement.")

        try:
            logger.info("Calling self.settle_payment...")
            settle_response = await self.settle_payment(
                payment_payload, payment_requirements
            )
            logger.info(f"Settlement response: {settle_response.model_dump_json(indent=2)}")
            if settle_response.success:
                logger.info("Settlement successful. Recording payment success.")
                task = self.utils.record_payment_success(task, settle_response)

                self._payment_requirements_store.pop(task.id, None)
            else:
                logger.warning(f"Settlement failed: {settle_response.error_reason}")
                error_code = x402ErrorCode.INSUFFICIENT_FUNDS if "insufficient" in (settle_response.error_reason or "").lower() else x402ErrorCode.SETTLEMENT_FAILED
                task = self.utils.record_payment_failure(task, error_code, settle_response)

                self._payment_requirements_store.pop(task.id, None)
            await event_queue.enqueue_event(task)
            logger.info("Settlement processing finished.")
        except Exception as e:
            logger.error(f"Exception during settlement: {e}", exc_info=True)
            await self._fail_payment(task, x402ErrorCode.SETTLEMENT_FAILED, f"Settlement failed: {e}", event_queue)
    
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

        logger.warning("No matching payment requirement found after checking all options.")
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

        payment_payload = self.utils.get_payment_payload(
            task
        ) or self.utils.get_payment_payload_from_message(context.message)
        if not payment_payload:
            logger.warning("Could not extract payment payload from task or message.")
            return None

        return self._find_matching_payment_requirement(accepts_array, payment_payload)
    
    async def _handle_payment_required_exception(self, exception: x402PaymentRequiredException, context: RequestContext, event_queue: EventQueue):
        """Handle x402PaymentRequiredException to request payment.
        
        Extracts payment requirements directly from the exception and creates
        a payment required response for the client.
        """
        task = context.current_task
        if not task:
            # If the task object isn't in the context (e.g., on the first turn),
            # create a temporary one using the IDs from the context. The TaskManager
            # will find the real task using the ID.
            if not context.task_id:
                raise ValueError("Cannot handle payment exception: task_id is missing from the context.")
            
            task = Task(
                id=context.task_id,
                contextId=context.context_id,
                status=TaskStatus(state=TaskState.input_required),
                metadata={}
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
            x402_version=1,
            accepts=accepts_array,
            error=error_message
        )
        
        # Update task with payment requirements
        task = self.utils.create_payment_required_task(task, payment_required)
        
        # Send the payment required response
        await event_queue.enqueue_event(task)
    

    async def _fail_payment(self, task, error_code: str, error_reason: str, event_queue: EventQueue):
        """Handle payment failure."""
        failure_response = SettleResponse(success=False, network="base", error_reason=error_reason)
        task = self.utils.record_payment_failure(task, error_code, failure_response)
        

        self._payment_requirements_store.pop(task.id, None)
        
        await event_queue.enqueue_event(task)