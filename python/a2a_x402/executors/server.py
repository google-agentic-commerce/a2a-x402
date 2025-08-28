"""Server-side executor for merchant implementations."""

from typing import Optional, Dict, List

from a2a.types import TextPart
from x402.common import find_matching_payment_requirements

from .base import X402BaseExecutor
from ..core import verify_payment, settle_payment
from ..core.merchant import create_payment_requirements
from ..types import (
    AgentExecutor,
    RequestContext,
    EventQueue,
    PaymentStatus,
    PaymentRequirements,
    SettleResponse,
    X402ExtensionConfig,
    X402ServerConfig,
    FacilitatorClient,
    X402ErrorCode,
    Message,
    Task,
    TaskStatus,
    TaskState,
    x402PaymentRequiredResponse
)


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
        server_config: X402ServerConfig,
        facilitator_client: Optional[FacilitatorClient] = None
    ):
        """Initialize server executor.
        
        Args:
            delegate: Underlying agent executor for business logic
            config: x402 extension configuration
            server_config: Server payment requirements configuration
            facilitator_client: Optional facilitator client for payment operations
        """
        super().__init__(delegate, config)
        self.server_config = server_config
        self.facilitator_client = facilitator_client or FacilitatorClient()
        
        # In-memory storage for payment requirements arrays by taskId
        self._payment_requirements_store: Dict[str, List[PaymentRequirements]] = {}
    
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Payment middleware: verify → execute service → settle."""
        if not self.is_active(context):
            try:
                return await self._delegate.execute(context, event_queue)
            except Exception as e:
                # Handle payment required exceptions when extension is not active
                await self._handle_payment_required_exception(e, context, event_queue)
                return

        task = getattr(context, 'current_task', None)
        if not task:
            try:
                return await self._delegate.execute(context, event_queue)
            except Exception as e:
                # Handle payment required exceptions when no task context
                await self._handle_payment_required_exception(e, context, event_queue)
                return
            
        status = self.utils.get_payment_status(task)

        if status == PaymentStatus.PAYMENT_SUBMITTED:
            # Handle payment flow: verify → execute → settle
            return await self._process_paid_request(task, context, event_queue)
        
        # Normal business logic for non-payment requests
        try:
            return await self._delegate.execute(context, event_queue)
        except Exception as e:
            # Handle payment required exceptions during normal execution
            await self._handle_payment_required_exception(e, context, event_queue)
            return
    
    async def _process_paid_request(
        self,
        task,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Process paid request: verify → execute → settle."""

        payment_payload = self.utils.get_payment_payload(task)
        if not payment_payload:
            return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, "Missing payment data", event_queue)
        

        payment_requirements = self._extract_payment_requirements_from_context(task)
        if not payment_requirements:
            return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, "Missing payment requirements", event_queue)
        

        try:
            verify_response = await verify_payment(payment_payload, payment_requirements, self.facilitator_client)
            if not verify_response.is_valid:
                return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, verify_response.invalid_reason or "Invalid payment", event_queue)
        except Exception as e:
            return await self._fail_payment(task, X402ErrorCode.INVALID_SIGNATURE, f"Verification failed: {e}", event_queue)
        

        if not hasattr(task.status, 'message') or not task.status.message:
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment is being processed.")],
                metadata={}
            )
        

        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}
        try:
            await self._delegate.execute(context, event_queue)
        except Exception as e:
            return await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Service failed: {e}", event_queue)
        

        try:
            settle_response = await settle_payment(payment_payload, payment_requirements, self.facilitator_client)
            if settle_response.success:
                task = self.utils.record_payment_success(task, settle_response)

                self._payment_requirements_store.pop(task.id, None)
            else:
                error_code = X402ErrorCode.INSUFFICIENT_FUNDS if "insufficient" in (settle_response.error_reason or "").lower() else X402ErrorCode.SETTLEMENT_FAILED
                task = self.utils.record_payment_failure(task, error_code, settle_response)

                self._payment_requirements_store.pop(task.id, None)
            await event_queue.enqueue_event(task)
        except Exception as e:
            await self._fail_payment(task, X402ErrorCode.SETTLEMENT_FAILED, f"Settlement failed: {e}", event_queue)
    
    def _extract_payment_requirements_from_context(self, task) -> Optional[PaymentRequirements]:
        """Extract the matching payment requirements based on the payment payload.
        
        Uses the stored accepts array and the payment payload to find which
        requirement the client chose to satisfy.
        """

        accepts_array = self._payment_requirements_store.get(task.id)
        if not accepts_array:
            return None
        

        payment_payload = self.utils.get_payment_payload(task)
        if not payment_payload:
            return None
        

        matching_requirement = find_matching_payment_requirements(accepts_array, payment_payload)
        
        return matching_requirement
    
    async def _handle_payment_required_exception(self, exception: Exception, context: RequestContext, event_queue: EventQueue):
        """Handle exceptions that indicate payment is required."""

        task = getattr(context, 'current_task', None)
        if not task:
            task = Task(
                id=f"payment-task-{id(context)}",
                contextId=getattr(context, 'context_id', 'unknown'),
                status=TaskStatus(state=TaskState.input_required),
                metadata={}
            )
        

        payment_requirements = self._create_payment_requirements_from_config(context=context)
        

        accepts_array = [payment_requirements]
        self._payment_requirements_store[task.id] = accepts_array
        
        payment_required = x402PaymentRequiredResponse(
            x402_version=1,
            accepts=accepts_array,
            error=str(exception)
        )
        

        task = self.utils.create_payment_required_task(task, payment_required)
        

        await event_queue.enqueue_event(task)
    
    def _create_payment_requirements_from_config(self, context: Optional[RequestContext] = None) -> PaymentRequirements:
        """Create payment requirements from server configuration.
        
        Args:
            context: Optional request context to extract dynamic resource path from.
        """

        resource = self.server_config.resource
        if not resource and context:
            if hasattr(context, 'request') and hasattr(context.request, 'url') and hasattr(context.request.url, 'path'):
                resource = context.request.url.path
        if not resource:
            resource = "/service"
            
        return create_payment_requirements(
            price=self.server_config.price,
            pay_to_address=self.server_config.pay_to_address,
            resource=resource,
            network=self.server_config.network,
            description=self.server_config.description,
            mime_type=self.server_config.mime_type,
            max_timeout_seconds=self.server_config.max_timeout_seconds
        )

    async def _fail_payment(self, task, error_code: str, error_reason: str, event_queue: EventQueue):
        """Handle payment failure."""
        failure_response = SettleResponse(success=False, network="base", error_reason=error_reason)
        task = self.utils.record_payment_failure(task, error_code, failure_response)
        

        self._payment_requirements_store.pop(task.id, None)
        
        await event_queue.enqueue_event(task)