"""Server-side executor for merchant implementations."""

from typing import Optional

from .base import X402BaseExecutor
from ..types import (
    AgentExecutor,
    RequestContext,
    EventQueue,
    PaymentStatus,
    x402SettleRequest,
    x402SettleResponse,
    X402ExtensionConfig,
    FacilitatorClient,
    X402ErrorCode
)
from ..core import verify_payment, settle_payment


class X402ServerExecutor(X402BaseExecutor):
    """Server-side payment middleware for merchant agents.
    
    Automatically handles: verify payment → execute service → settle payment
    
    Example:
        server = X402ServerExecutor(my_agent, config)
        # Your agent now accepts payments automatically!
    """
    
    def __init__(
        self,
        delegate: AgentExecutor,
        config: X402ExtensionConfig,
        facilitator_client: Optional[FacilitatorClient] = None
    ):
        """Initialize server executor.
        
        Args:
            delegate: Underlying agent executor for business logic
            config: x402 extension configuration
            facilitator_client: Optional facilitator client for payment operations
        """
        super().__init__(delegate, config)
        self.facilitator_client = facilitator_client or FacilitatorClient()
    
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Payment middleware: verify → execute service → settle."""
        if not self.is_active(context):
            return await self._delegate.execute(context, event_queue)

        task = getattr(context, 'current_task', None)
        if not task:
            return await self._delegate.execute(context, event_queue)
            
        status = self.utils.get_payment_status(task)

        if status == PaymentStatus.PAYMENT_SUBMITTED:
            # Handle payment flow: verify → execute → settle
            return await self._process_paid_request(task, context, event_queue)
        
        # Normal business logic for non-payment requests
        return await self._delegate.execute(context, event_queue)
    
    async def _process_paid_request(
        self,
        task,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Process paid request: verify → execute → settle."""
        # Extract payment data
        settle_request = self.utils.get_settle_request(task)
        if not settle_request:
            return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, "Missing payment data", event_queue)
        
        # 1. Verify payment
        try:
            verify_response = await verify_payment(settle_request, self.facilitator_client)
            if not verify_response.is_valid:
                return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, verify_response.invalid_reason or "Invalid payment", event_queue)
        except Exception as e:
            return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, f"Verification failed: {e}", event_queue)
        
        # 2. Execute business service
        task.metadata[self.utils.STATUS_KEY] = PaymentStatus.PAYMENT_PENDING.value
        try:
            await self._delegate.execute(context, event_queue)
        except Exception as e:
            return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Service failed: {e}", event_queue)
        
        # 3. Settle payment
        try:
            settle_response = await settle_payment(settle_request, self.facilitator_client)
            if settle_response.success:
                task = self.utils.record_payment_success(task, settle_response)
            else:
                error_code = X402ErrorCode.INSUFFICIENT_FUNDS if "insufficient" in (settle_response.error_reason or "").lower() else X402ErrorCode.SETTLEMENT_FAILED
                task = self.utils.record_payment_failure(task, error_code, settle_response)
            await event_queue.enqueue_event(task)
        except Exception as e:
            await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Settlement failed: {e}", event_queue)
    
    async def _fail_payment(self, task, error_code: str, error_reason: str, event_queue: EventQueue):
        """Handle payment failure."""
        failure_response = x402SettleResponse(success=False, network="base", error_reason=error_reason)
        task = self.utils.record_payment_failure(task, error_code, failure_response)
        await event_queue.enqueue_event(task)