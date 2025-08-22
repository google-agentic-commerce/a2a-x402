"""State management utilities for x402 protocol."""

from typing import Optional
from ..types import (
    Task,
    Message,
    PaymentStatus,
    X402Metadata,
    x402PaymentRequiredResponse,
    x402SettleRequest,
    x402SettleResponse
)
from a2a.types import TextPart


def create_payment_submission_message(
    task_id: str,
    settle_request: x402SettleRequest,
    text: str = "Payment authorization provided"
) -> Message:
    """Creates correlated payment submission message per spec."""
    import uuid
    return Message(
        messageId=str(uuid.uuid4()),  # Required by A2A Message type
        task_id=task_id,  # Spec mandates this correlation
        role="user",
        parts=[TextPart(kind="text", text=text)],
        metadata={
            X402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            X402Metadata.PAYLOAD_KEY: settle_request.model_dump(by_alias=True)
        }
    )


def extract_task_correlation(message: Message) -> Optional[str]:
    """Extracts task ID for correlation from payment message."""
    if isinstance(message, dict):
        return message.get('task_id')
    return getattr(message, 'task_id', None)


class X402Utils:
    """Core utilities for x402 protocol state management."""
    
    # Metadata keys as defined by spec
    STATUS_KEY = X402Metadata.STATUS_KEY
    REQUIRED_KEY = X402Metadata.REQUIRED_KEY
    PAYLOAD_KEY = X402Metadata.PAYLOAD_KEY
    RECEIPT_KEY = X402Metadata.RECEIPT_KEY
    ERROR_KEY = X402Metadata.ERROR_KEY
    
    def get_payment_status(self, task: Task) -> Optional[PaymentStatus]:
        """Extract payment status from task metadata."""
        if not task or not task.metadata:
            return None
        
        status_value = task.metadata.get(self.STATUS_KEY)
        if status_value:
            try:
                return PaymentStatus(status_value)
            except ValueError:
                return None
        return None
    
    def get_payment_requirements(self, task: Task) -> Optional[x402PaymentRequiredResponse]:
        """Extract payment requirements from task metadata."""
        if not task or not task.metadata:
            return None
            
        req_data = task.metadata.get(self.REQUIRED_KEY)
        if req_data:
            try:
                return x402PaymentRequiredResponse.model_validate(req_data)
            except Exception:
                return None
        return None
        
    def get_settle_request(self, task: Task) -> Optional[x402SettleRequest]:
        """Extract settle request from task metadata."""
        if not task or not task.metadata:
            return None
            
        payload_data = task.metadata.get(self.PAYLOAD_KEY)
        if payload_data:
            try:
                return x402SettleRequest.model_validate(payload_data)
            except Exception:
                return None
        return None
    
    def create_payment_required_task(
        self,
        task: Task,
        payment_required: x402PaymentRequiredResponse
    ) -> Task:
        """Set task to payment required state with proper metadata."""
        if task.metadata is None:
            task.metadata = {}
            
        task.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_REQUIRED.value
        task.metadata[self.REQUIRED_KEY] = payment_required.model_dump(by_alias=True)
        return task
    
    def record_payment_submission(
        self,
        task: Task,
        settle_request: x402SettleRequest
    ) -> Task:
        """Record payment submission in task metadata."""  
        if task.metadata is None:
            task.metadata = {}
            
        task.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_SUBMITTED.value
        task.metadata[self.PAYLOAD_KEY] = settle_request.model_dump(by_alias=True)
        # Clean up requirements after submission
        task.metadata.pop(self.REQUIRED_KEY, None)
        return task
    
    def record_payment_success(
        self,
        task: Task,
        settle_response: x402SettleResponse
    ) -> Task:
        """Record successful payment with settlement response."""
        if task.metadata is None:
            task.metadata = {}
            
        task.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_COMPLETED.value
        task.metadata[self.RECEIPT_KEY] = settle_response.model_dump(by_alias=True)
        # Clean up intermediate data
        task.metadata.pop(self.PAYLOAD_KEY, None)
        return task
    
    def record_payment_failure(
        self,
        task: Task,
        error_code: str,
        settle_response: x402SettleResponse
    ) -> Task:
        """Record payment failure with error details."""
        if task.metadata is None:
            task.metadata = {}
            
        task.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_FAILED.value
        task.metadata[self.ERROR_KEY] = error_code
        task.metadata[self.RECEIPT_KEY] = settle_response.model_dump(by_alias=True)
        # Clean up intermediate data
        task.metadata.pop(self.PAYLOAD_KEY, None)
        return task