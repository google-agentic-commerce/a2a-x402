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
import time
from abc import ABCMeta, abstractmethod
from typing import Dict, List, Optional, Tuple

from a2a.server.tasks import TaskUpdater

from .base import x402BaseExecutor
from .nonce_store import InMemoryPaymentNonceStore, PaymentNonceStore
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
)


logger = logging.getLogger(__name__)

# Task metadata key that tells the delegate the current turn carries a verified
# payment. It is only valid for the duration of the delegate call on that turn.
PAYMENT_VERIFIED_KEY = "x402_payment_verified"

# Used when no nonce store is supplied. Shared by every executor in the process
# so replays are caught even if executors are created per request.
_DEFAULT_NONCE_STORE = InMemoryPaymentNonceStore()


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
        nonce_store: Optional[PaymentNonceStore] = None,
    ):
        """Initialize server executor.

        Args:
            delegate: Underlying agent executor for business logic
            config: x402 extension configuration
            nonce_store: Records used payment nonces to block replays. Defaults
                to a process-local in-memory store; multi-replica deployments
                must supply a shared store.
        """
        super().__init__(delegate, config)
        self._payment_requirements_store: Dict[str, List[PaymentRequirements]] = {}
        self._nonce_store = (
            nonce_store if nonce_store is not None else _DEFAULT_NONCE_STORE
        )

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
        # Never trust a verification flag carried over from an earlier turn.
        # Clear it before updater.start_work() so the cleaned metadata is saved
        # even when TaskStore serializes Task objects on write.
        _clear_payment_verified(context.current_task)

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        task = context.current_task or Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.working),
        )
        self.utils.get_payment_status(task)

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

        # Reserve the nonce only after the signature is verified, so a forged
        # payload cannot burn another payer's nonce. This must happen before
        # the delegate runs, because settlement (the on-chain replay check)
        # only happens after the service has been delivered.
        rejection = await self._reserve_payment_nonce(
            payment_payload, payment_requirements
        )
        if rejection is not None:
            error_code, reason = rejection
            logger.warning(f"Rejecting payment for task {task.id}: {reason}")
            return await self._fail_payment(task, error_code, reason, event_queue)

        logger.info("Payment verified successfully. Recording and updating task.")
        task = self.utils.record_payment_verified(task)
        await event_queue.enqueue_event(task)

        # Add the verification status to the task metadata for the delegate agent.
        if not task.metadata:
            task.metadata = {}
        task.metadata[PAYMENT_VERIFIED_KEY] = True
        logger.info(f"Set {PAYMENT_VERIFIED_KEY}=True in task.metadata")

        if task.status.message is not None and (
            not hasattr(task.status.message, "metadata")
            or not task.status.message.metadata
        ):
            task.status.message.metadata = {}
        delegate_error: Optional[Exception] = None
        try:
            logger.info("Executing delegate agent...")
            await self._delegate.execute(context, event_queue)
            logger.info("Delegate agent execution finished.")
        except Exception as e:
            delegate_error = e
        finally:
            # The flag is a per-turn signal. Clear it before any further task
            # events are enqueued so it is never persisted for later turns.
            _clear_payment_verified(task)

        if delegate_error is not None:
            logger.error(
                f"Exception during delegate execution: {delegate_error}",
                exc_info=delegate_error,
            )
            return await self._fail_payment(
                task,
                x402ErrorCode.SETTLEMENT_FAILED,
                f"Service failed: {delegate_error}",
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
            await event_queue.enqueue_event(task)
            logger.info("Settlement processing finished.")
        except Exception as e:
            logger.error(f"Exception during settlement: {e}", exc_info=True)
            await self._fail_payment(
                task,
                x402ErrorCode.SETTLEMENT_FAILED,
                f"Settlement failed: {e}",
                event_queue,
            )

    async def _reserve_payment_nonce(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> Optional[Tuple[str, str]]:
        """Marks the payment's nonce as used.

        Returns:
            None if the payment may proceed, or an (error_code, reason) tuple
            if it must be rejected.
        """
        authorization = getattr(payload.payload, "authorization", None)
        if authorization is None:
            return x402ErrorCode.INVALID_SIGNATURE, "Missing payment authorization"
        try:
            valid_before = int(authorization.valid_before)
        except (TypeError, ValueError):
            return x402ErrorCode.INVALID_SIGNATURE, "Invalid authorization expiry"
        # Expired authorizations are rejected here so that nonce store entries
        # can be dropped once their authorization expires.
        if valid_before <= time.time():
            return x402ErrorCode.EXPIRED_PAYMENT, "Payment authorization has expired"

        key = json.dumps(
            [
                payload.network.strip().lower(),
                _normalize_hex(requirements.asset),
                _normalize_hex(authorization.from_),
                _normalize_hex(authorization.nonce),
            ]
        )
        try:
            reserved = await self._nonce_store.reserve(key, valid_before)
        except Exception as e:
            logger.error(f"Exception while recording payment nonce: {e}", exc_info=True)
            return x402ErrorCode.SETTLEMENT_FAILED, "Unable to record payment nonce"
        if not reserved:
            return (
                x402ErrorCode.DUPLICATE_NONCE,
                "Payment nonce has already been used",
            )
        return None

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

        await event_queue.enqueue_event(task)


def _clear_payment_verified(task: Optional[Task]) -> None:
    """Removes the per-turn payment verification flag from a task, if present."""
    if task is not None and task.metadata:
        task.metadata.pop(PAYMENT_VERIFIED_KEY, None)


def _normalize_hex(value: str) -> str:
    """Normalizes hex identifiers (addresses, nonces) to lowercase without 0x."""
    return value.strip().lower().removeprefix("0x")
