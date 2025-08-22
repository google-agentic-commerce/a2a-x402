"""Core protocol operations for x402 payment verification and settlement."""

from typing import Optional

from ..types import (
    x402SettleRequest,
    x402SettleResponse,
    VerifyResponse,
    FacilitatorClient
)


async def verify_payment(
    settle_request: x402SettleRequest,
    facilitator_client: Optional[FacilitatorClient] = None
) -> VerifyResponse:
    """Verify payment signature and requirements using facilitator.
    
    Args:
        settle_request: Payment data to verify
        facilitator_client: Optional FacilitatorClient instance
        
    Returns:
        VerifyResponse with is_valid status and invalid_reason if applicable
    """
    if facilitator_client is None:
        facilitator_client = FacilitatorClient()
        
    return await facilitator_client.verify(
        settle_request.payment_payload,
        settle_request.payment_requirements
    )


async def settle_payment(
    settle_request: x402SettleRequest,
    facilitator_client: Optional[FacilitatorClient] = None
) -> x402SettleResponse:
    """Settle payment on blockchain using facilitator.
    
    Args:
        settle_request: Verified payment data to settle
        facilitator_client: Optional FacilitatorClient instance
        
    Returns:
        x402SettleResponse with settlement result and transaction hash
    """
    if facilitator_client is None:
        facilitator_client = FacilitatorClient()
        
    # Call facilitator to settle payment
    settle_response = await facilitator_client.settle(
        settle_request.payment_payload,
        settle_request.payment_requirements
    )
    
    # Convert to A2A-specific response format
    return x402SettleResponse(
        success=settle_response.success,
        transaction=settle_response.transaction,
        network=settle_response.network or settle_request.payment_requirements.network,
        payer=settle_response.payer,
        error_reason=settle_response.error_reason
    )