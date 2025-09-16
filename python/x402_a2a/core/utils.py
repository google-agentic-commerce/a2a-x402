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
"""State management utilities for x402 protocol."""

import logging
import uuid
from typing import Optional
from ..types import (
    Task,
    Message,
    PaymentStatus,
    x402Metadata,
    x402PaymentRequiredResponse,
    PaymentPayload,
    ExactPaymentPayload,
    SettleResponse,
    TaskState,
    TaskStatus
)
from a2a.types import TextPart


def _parse_payment_payload(payload_data: dict) -> PaymentPayload:
    """Parse the payment payload using the top-level Pydantic model."""
    # The PaymentPayload model from x402.types is designed to handle the
    # entire structure, including the nested payload based on the scheme.
    return PaymentPayload.model_validate(payload_data)


def create_payment_submission_message(
    task_id: str,
    payment_payload: PaymentPayload,
    text: str = "Payment authorization provided",
    message_id: Optional[str] = None
) -> Message:
    """Creates correlated payment submission message per spec.
    
    Args:
        task_id: Task ID for correlation
        payment_payload: Payment data to include
        text: Message text content
        message_id: Optional specific message ID; generates UUID if not provided
    """
    msg_id = message_id if message_id is not None else str(uuid.uuid4())
    return Message(
        messageId=msg_id,  # Use provided ID or generate UUID
        task_id=task_id,  # Spec mandates this correlation
        role="user",
        parts=[TextPart(kind="text", text=text)],
        metadata={
            x402Metadata.STATUS_KEY: PaymentStatus.PAYMENT_SUBMITTED.value,
            x402Metadata.PAYLOAD_KEY: payment_payload.model_dump(by_alias=True)
        }
    )


def extract_task_id(message: Message) -> Optional[str]:
    """Extracts task ID for correlation from payment message."""
    if isinstance(message, dict):
        return message.get('task_id')
    return getattr(message, 'task_id', None)


class x402Utils:
    """Core utilities for x402 protocol state management."""
    

    STATUS_KEY = x402Metadata.STATUS_KEY
    REQUIRED_KEY = x402Metadata.REQUIRED_KEY
    PAYLOAD_KEY = x402Metadata.PAYLOAD_KEY
    RECEIPTS_KEY = x402Metadata.RECEIPTS_KEY
    ERROR_KEY = x402Metadata.ERROR_KEY
    

    def get_payment_status_from_message(self, message: Message) -> Optional[PaymentStatus]:
        """Extract payment status from message metadata."""
        if not message or not hasattr(message, 'metadata') or not message.metadata:
            return None
        
        status_value = message.metadata.get(self.STATUS_KEY)
        if status_value:
            try:
                return PaymentStatus(status_value)
            except ValueError:
                return None
        return None
    
    def get_payment_status_from_task(self, task: Task) -> Optional[PaymentStatus]:
        """Extract payment status from task's status message metadata."""
        if not task or not hasattr(task, 'status') or not task.status:
            return None
        if not hasattr(task.status, 'message') or not task.status.message:
            return None
        
        return self.get_payment_status_from_message(task.status.message)
    
    def get_payment_status(self, task: Task) -> Optional[PaymentStatus]:
        """Extract payment status from task metadata (updated to use task status message)."""
        return self.get_payment_status_from_task(task)
    
    def get_payment_requirements_from_message(self, message: Message) -> Optional[x402PaymentRequiredResponse]:
        """Extract payment requirements from message metadata."""
        if not message or not hasattr(message, 'metadata') or not message.metadata:
            return None
            
        req_data = message.metadata.get(self.REQUIRED_KEY)
        if req_data:
            try:
                return x402PaymentRequiredResponse.model_validate(req_data)
            except Exception:
                return None
        return None
    
    def get_payment_requirements_from_task(self, task: Task) -> Optional[x402PaymentRequiredResponse]:
        """Extract payment requirements from task's status message metadata."""
        if not task or not hasattr(task, 'status') or not task.status:
            return None
        if not hasattr(task.status, 'message') or not task.status.message:
            return None
        
        return self.get_payment_requirements_from_message(task.status.message)
    
    def get_payment_requirements(self, task: Task) -> Optional[x402PaymentRequiredResponse]:
        """Extract payment requirements from task metadata (updated to use task status message)."""
        return self.get_payment_requirements_from_task(task)
        
    def get_payment_payload_from_message(self, message: Message) -> Optional[PaymentPayload]:
        """Extract payment payload from message metadata."""
        if not message or not hasattr(message, 'metadata') or not message.metadata:
            return None
            
        payload_data = message.metadata.get(self.PAYLOAD_KEY)
        if payload_data:
            try:
                return _parse_payment_payload(payload_data)
            except Exception as e:
                logging.error(f"Failed to parse payment payload: {e}", exc_info=True)
                return None
        return None
    
    def get_payment_payload_from_task(self, task: Task) -> Optional[PaymentPayload]:
        """Extract payment payload from task's status message metadata."""
        if not task or not hasattr(task, 'status') or not task.status:
            return None
        if not hasattr(task.status, 'message') or not task.status.message:
            return None
        
        return self.get_payment_payload_from_message(task.status.message)
    
    def get_payment_payload(self, task: Task) -> Optional[PaymentPayload]:
        """Extract payment payload from task metadata (updated to use task status message)."""
        return self.get_payment_payload_from_task(task)
    
    def create_payment_required_task(
        self,
        task: Task,
        payment_required: x402PaymentRequiredResponse
    ) -> Task:
        """Set task to payment required state with proper metadata."""
        # Set task status to input-required as per A2A spec
        if task.status:
            task.status.state = TaskState.input_required
        else:
            task.status = TaskStatus(state=TaskState.input_required)
        
        # Ensure task has a status message for metadata
        if not hasattr(task.status, 'message') or not task.status.message:
            from ..types import Message
            from a2a.types import TextPart
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment is required for this service.")],
                metadata={}
            )
        
        # Ensure message has metadata
        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}
            
        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_REQUIRED.value
        task.status.message.metadata[self.REQUIRED_KEY] = payment_required.model_dump(by_alias=True)
        return task
    
    def record_payment_verified(
        self,
        task: Task,
    ) -> Task:
        """Record payment verification in task metadata."""
        # Ensure task has a status message for metadata
        if not hasattr(task.status, 'message') or not task.status.message:
            from ..types import Message
            from a2a.types import TextPart
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment verification recorded.")],
                metadata={}
            )

        # Ensure message has metadata
        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}

        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_VERIFIED.value
        return task
    
    def record_payment_success(
        self,
        task: Task,
        settle_response: SettleResponse
    ) -> Task:
        """Record successful payment with settlement response."""
        # Ensure task has a status message for metadata
        if not hasattr(task.status, 'message') or not task.status.message:
            from ..types import Message
            from a2a.types import TextPart
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment completed successfully.")],
                metadata={}
            )
        
        # Ensure message has metadata
        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}
            
        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_COMPLETED.value
        # Append to receipts array (spec requirement for complete history)
        if self.RECEIPTS_KEY not in task.status.message.metadata:
            task.status.message.metadata[self.RECEIPTS_KEY] = []
        task.status.message.metadata[self.RECEIPTS_KEY].append(settle_response.model_dump(by_alias=True))
        # Clean up intermediate data
        task.status.message.metadata.pop(self.PAYLOAD_KEY, None)
        task.status.message.metadata.pop(self.REQUIRED_KEY, None)
        return task
    
    def record_payment_failure(
        self,
        task: Task,
        error_code: str,
        settle_response: SettleResponse
    ) -> Task:
        """Record payment failure with error details."""
        # Ensure task has a status message for metadata
        if not hasattr(task.status, 'message') or not task.status.message:
            from ..types import Message
            from a2a.types import TextPart
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment failed.")],
                metadata={}
            )
        
        # Ensure message has metadata
        if not hasattr(task.status.message, 'metadata') or not task.status.message.metadata:
            task.status.message.metadata = {}
            
        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_FAILED.value
        task.status.message.metadata[self.ERROR_KEY] = error_code
        # Append to receipts array (spec requirement for complete history)
        if self.RECEIPTS_KEY not in task.status.message.metadata:
            task.status.message.metadata[self.RECEIPTS_KEY] = []
        task.status.message.metadata[self.RECEIPTS_KEY].append(settle_response.model_dump(by_alias=True))
        # Clean up intermediate data
        task.status.message.metadata.pop(self.PAYLOAD_KEY, None)
        return task
    
    def get_payment_receipts_from_message(self, message: Message) -> list[SettleResponse]:
        """Get all payment receipts from message metadata."""
        if not message or not hasattr(message, 'metadata') or not message.metadata:
            return []
            
        receipts_data = message.metadata.get(self.RECEIPTS_KEY, [])
        receipts = []
        for receipt_data in receipts_data:
            try:
                receipts.append(SettleResponse.model_validate(receipt_data))
            except Exception:
                continue
        return receipts
    
    def get_payment_receipts_from_task(self, task: Task) -> list[SettleResponse]:
        """Get all payment receipts from task's status message metadata."""
        if not task or not hasattr(task, 'status') or not task.status:
            return []
        if not hasattr(task.status, 'message') or not task.status.message:
            return []
        
        return self.get_payment_receipts_from_message(task.status.message)
    
    def get_payment_receipts(self, task: Task) -> list[SettleResponse]:
        """Get all payment receipts from task metadata (updated to use task status message)."""
        return self.get_payment_receipts_from_task(task)
    
    def get_latest_receipt(self, task: Task) -> Optional[SettleResponse]:
        """Get the most recent payment receipt from task metadata."""
        receipts = self.get_payment_receipts(task)
        return receipts[-1] if receipts else None
