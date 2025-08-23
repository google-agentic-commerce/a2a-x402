"""State management utilities for x402 protocol."""

from typing import Optional
from ..types import (
    Task,
    Message,
    PaymentStatus,
    X402Metadata,
    x402PaymentRequiredResponse,
    PaymentPayload,
    x402SettleResponse
)
from a2a.types import TextPart


def create_payment_submission_message(
    task_id: str,
    payment_payload: PaymentPayload,
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
            X402Metadata.PAYLOAD_KEY: payment_payload.model_dump(by_alias=True)
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
    RECEIPTS_KEY = X402Metadata.RECEIPTS_KEY
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
        
    def get_payment_payload(self, task: Task) -> Optional[PaymentPayload]:
        """Extract payment payload from task metadata."""
        if not task or not task.metadata:
            return None
            
        payload_data = task.metadata.get(self.PAYLOAD_KEY)
        if payload_data:
            try:
                return PaymentPayload.model_validate(payload_data)
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
        payment_payload: PaymentPayload
    ) -> Task:
        """Record payment submission in task metadata."""  
        if task.metadata is None:
            task.metadata = {}
            
        task.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_SUBMITTED.value
        task.metadata[self.PAYLOAD_KEY] = payment_payload.model_dump(by_alias=True)
        # Note: Keep requirements for verification - will be cleaned up after settlement
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
        # Append to receipts array (spec requirement for complete history)
        if self.RECEIPTS_KEY not in task.metadata:
            task.metadata[self.RECEIPTS_KEY] = []
        task.metadata[self.RECEIPTS_KEY].append(settle_response.model_dump(by_alias=True))
        # Clean up intermediate data
        task.metadata.pop(self.PAYLOAD_KEY, None)
        task.metadata.pop(self.REQUIRED_KEY, None)
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
        # Append to receipts array (spec requirement for complete history)
        if self.RECEIPTS_KEY not in task.metadata:
            task.metadata[self.RECEIPTS_KEY] = []
        task.metadata[self.RECEIPTS_KEY].append(settle_response.model_dump(by_alias=True))
        # Clean up intermediate data
        task.metadata.pop(self.PAYLOAD_KEY, None)
        return task
    
    def get_payment_receipts(self, task: Task) -> list[x402SettleResponse]:
        """Get all payment receipts from task metadata."""
        if not task or not task.metadata:
            return []
            
        receipts_data = task.metadata.get(self.RECEIPTS_KEY, [])
        receipts = []
        for receipt_data in receipts_data:
            try:
                receipts.append(x402SettleResponse.model_validate(receipt_data))
            except Exception:
                continue
        return receipts
    
    def get_latest_receipt(self, task: Task) -> Optional[x402SettleResponse]:
        """Get the most recent payment receipt from task metadata."""
        receipts = self.get_payment_receipts(task)
        return receipts[-1] if receipts else None