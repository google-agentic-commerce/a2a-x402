"""Payment signing and processing functions."""

from typing import Optional
from eth_account import Account
from x402.clients.base import x402Client
from x402.common import x402_VERSION

from ..types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload
)


def process_payment_required(
    payment_required: x402PaymentRequiredResponse,
    account: Account,
    max_value: Optional[int] = None
) -> PaymentPayload:
    """Process full payment required response using x402Client logic.

    Args:
        payment_required: Complete response from merchant with accepts[] array
        account: Ethereum account for signing
        max_value: Maximum payment value willing to pay

    Returns:
        Signed PaymentPayload with selected requirement
    """
    # Use x402Client for payment requirement selection
    client = x402Client(account=account, max_value=max_value)
    selected_requirement = client.select_payment_requirements(payment_required.accepts)

    # Create payment payload (like create_payment_header but return PaymentPayload object)
    payment_payload = process_payment(selected_requirement, account, max_value)

    return payment_payload


def process_payment(
    requirements: PaymentRequirements,
    account,  # Union[Account, SyncClient]
    max_value: Optional[int] = None
) -> PaymentPayload:
    """Create PaymentPayload using x402Client - just like other x402 examples.

    Args:
        requirements: Single PaymentRequirements to sign
        account: Account for signing (eth_account.Account for EVM, pysui.SyncClient for Sui)
        max_value: Maximum payment value willing to pay (in atomic units)

    Returns:
        Signed PaymentPayload from x402Client
        
    Raises:
        ValueError: If payment amount exceeds max_value
    """
    # Validate payment amount against maximum willingness to pay
    if max_value is not None:
        required_amount = int(requirements.max_amount_required)
        if required_amount > max_value:
            raise ValueError(f"Payment amount {required_amount} exceeds maximum willing to pay {max_value}")
    
    # Use x402 directly - matching the exact flow from x402 examples
    try:
        from x402.exact import prepare_payment_header, sign_payment_header, decode_payment
        from x402.common import x402_VERSION

        # Prepare and sign the payment header directly
        unsigned_header = prepare_payment_header(account, x402_VERSION, requirements)
        signed_header_b64 = sign_payment_header(account, requirements, unsigned_header)
        
        # Decode to get the PaymentPayload structure
        decoded = decode_payment(signed_header_b64)
        
        # Return as PaymentPayload
        return PaymentPayload(**decoded)

    except ImportError as e:
        raise ImportError(f"x402 package required for payments: {e}")


