"""Payment signing and processing functions."""

from typing import Optional
from eth_account import Account
from x402.clients.base import x402Client
from x402.common import x402_VERSION
import time
import secrets

from ..types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload,
    x402SettleRequest,
    ExactPaymentPayload,
    EIP3009Authorization
)


def process_payment_required(
    payment_required: x402PaymentRequiredResponse,
    account: Account,
    max_value: Optional[int] = None
) -> x402SettleRequest:
    """Process full payment required response using x402Client logic.
    
    Args:
        payment_required: Complete response from merchant with accepts[] array
        account: Ethereum account for signing
        max_value: Maximum payment value willing to pay
        
    Returns:
        Complete x402SettleRequest with selected requirement + signed payload
    """
    # Use x402Client for payment requirement selection
    client = x402Client(account=account, max_value=max_value)
    selected_requirement = client.select_payment_requirements(payment_required.accepts)
    
    # Create payment payload (like create_payment_header but return PaymentPayload object)
    payment_payload = process_payment(selected_requirement, account, max_value)
    
    return x402SettleRequest(
        payment_requirements=selected_requirement,
        payment_payload=payment_payload
    )


def process_payment(
    requirements: PaymentRequirements,
    account: Account,
    max_value: Optional[int] = None
) -> PaymentPayload:
    """Create PaymentPayload - extends x402Client.create_payment_header logic.
    
    Same as create_payment_header but returns PaymentPayload object (not base64 encoded).
    
    Args:
        requirements: Single PaymentRequirements to sign
        account: Ethereum account for signing
        max_value: Maximum payment value willing to pay
        
    Returns:
        Signed PaymentPayload object
    """
    # Create authorization data
    authorization = EIP3009Authorization(
        from_=account.address,
        to=requirements.pay_to,
        value=requirements.max_amount_required,
        valid_after=str(int(time.time()) - 60),  # 60 seconds before
        valid_before=str(int(time.time()) + requirements.max_timeout_seconds),
        nonce=_generate_nonce()
    )
    
    # Sign the authorization (simplified version of x402 signing logic)
    # TODO: Implement proper EIP-712 signing using x402.exact.sign_payment_header logic
    signature = "0x" + "0" * 130  # Placeholder signature
    
    exact_payload = ExactPaymentPayload(
        signature=signature,
        authorization=authorization
    )
    
    return PaymentPayload(
        x402_version=x402_VERSION,
        scheme=requirements.scheme,
        network=requirements.network,
        payload=exact_payload
    )


def _generate_nonce() -> str:
    """Generate a random nonce for payment authorization."""
    return secrets.token_hex(32)