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
from typing import Optional, Union

logger = logging.getLogger(__name__)
from ..types import (
    Task,
    Message,
    PaymentStatus,
    x402Metadata,
    # V1 types
    NvmPaymentRequiredResponse,
    # V2 types
    PaymentRequiredResponseV2,
    PaymentPayload,
    SettleResponse,
    TaskState,
    TaskStatus,
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
    message_id: Optional[str] = None,
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
            x402Metadata.PAYLOAD_KEY: payment_payload.model_dump(by_alias=True),
        },
    )


def extract_task_id(message: Message) -> Optional[str]:
    """Extracts task ID for correlation from payment message."""
    if isinstance(message, dict):
        return message.get("task_id")
    return getattr(message, "task_id", None)
