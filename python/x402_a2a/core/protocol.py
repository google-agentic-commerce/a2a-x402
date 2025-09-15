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
"""Core protocol operations for x402 payment verification and settlement."""

from typing import Optional

from ..types import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
    FacilitatorClient
)


async def verify_payment(
    payment_payload: PaymentPayload,
    payment_requirements: PaymentRequirements,
    facilitator_client: Optional[FacilitatorClient] = None
) -> VerifyResponse:
    """Verify payment signature and requirements using facilitator.
    
    Args:
        payment_payload: Signed payment authorization
        payment_requirements: Payment requirements to verify against
        facilitator_client: Optional FacilitatorClient instance
        
    Returns:
        VerifyResponse with is_valid status and invalid_reason if applicable
    """
    if facilitator_client is None:
        facilitator_client = FacilitatorClient()
        
    return await facilitator_client.verify(
        payment_payload,
        payment_requirements
    )


async def settle_payment(
    payment_payload: PaymentPayload,
    payment_requirements: PaymentRequirements,
    facilitator_client: Optional[FacilitatorClient] = None
) -> SettleResponse:
    """Settle payment on blockchain using facilitator.
    
    Args:
        payment_payload: Signed payment authorization
        payment_requirements: Payment requirements for settlement
        facilitator_client: Optional FacilitatorClient instance
        
    Returns:
        SettleResponse with settlement result and transaction hash
    """
    if facilitator_client is None:
        facilitator_client = FacilitatorClient()
        
    # Call facilitator to settle payment
    settle_response = await facilitator_client.settle(
        payment_payload,
        payment_requirements
    )
    
    # Convert to A2A-specific response format
    return SettleResponse(
        success=settle_response.success,
        transaction=settle_response.transaction,
        network=settle_response.network or payment_requirements.network,
        payer=settle_response.payer,
        error_reason=settle_response.error_reason
    )
