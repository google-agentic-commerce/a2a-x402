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