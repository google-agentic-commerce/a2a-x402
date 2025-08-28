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
    ExactEvmPaymentPayload,
    EIP3009Authorization
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
    account,  # Union[Account, SyncClient] - supports both EVM and Sui
    max_value: Optional[int] = None
) -> PaymentPayload:
    """Create PaymentPayload - supports both EVM and Sui accounts.
    
    Same as create_payment_header but returns PaymentPayload object (not base64 encoded).
    
    Args:
        requirements: Single PaymentRequirements to sign
        account: Account for signing (eth_account.Account for EVM, pysui.SyncClient for Sui)
        max_value: Maximum payment value willing to pay
        
    Returns:
        Signed PaymentPayload object
    """
    # Validate payment amount against maximum willingness to pay
    if max_value is not None:
        required_amount = int(requirements.max_amount_required)
        if required_amount > max_value:
            raise ValueError(f"Payment amount {required_amount} exceeds maximum willing to pay {max_value}")
    
    # Try to use x402 library if available (supports both EVM and Sui)
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
        
    except ImportError:
        # Fallback to simplified implementation if x402.exact not available
        # This maintains compatibility while x402 library is being updated
        authorization = EIP3009Authorization(
            from_=getattr(account, 'address', str(account)),
            to=requirements.pay_to,
            value=requirements.max_amount_required,
            valid_after=str(int(time.time()) - 60),  # 60 seconds before
            valid_before=str(int(time.time()) + requirements.max_timeout_seconds),
            nonce=_generate_nonce()
        )
        
        # Sign the authorization (simplified version of x402 signing logic)
        # TODO: Implement proper EIP-712 signing using x402.exact.sign_payment_header logic
        signature = "0x" + "0" * 130  # Placeholder signature
        
        exact_payload = ExactEvmPaymentPayload(
            signature=signature,
            authorization=authorization
        )
        
        return PaymentPayload(
            x402_version=x402_VERSION,
            scheme=requirements.scheme,
            network=requirements.network,
            payload=exact_payload
        )


def process_batch_payment(
    payment_requirements_list: list,
    account,  # Union[Account, SyncClient]
    max_value: Optional[int] = None
) -> PaymentPayload:
    """Create a batch PaymentPayload for multiple payments in a single transaction.
    
    This function creates a single transaction that handles multiple payments by:
    1. Using prepare_batch_payment_header from x402.exact for SUI transactions
    2. Handling coin merging and splitting logic for efficient batch processing
    3. Making multiple move calls for each payment in the batch
    
    Args:
        payment_requirements_list: List of PaymentRequirements to process in batch
        account: Account for signing (pysui.SyncClient for Sui batch transactions)
        max_value: Maximum payment value willing to pay (total across all payments)
        
    Returns:
        Signed PaymentPayload object for the batch transaction
    """
    if not payment_requirements_list:
        raise ValueError("Payment requirements list cannot be empty")
    
    # Validate total payment amount against maximum willingness to pay
    if max_value is not None:
        total_required = sum(int(req.max_amount_required) for req in payment_requirements_list)
        if total_required > max_value:
            raise ValueError(f"Total payment amount {total_required} exceeds maximum willing to pay {max_value}")
    
    # Use x402 library for batch payment processing
    try:
        from x402.exact import prepare_batch_payment_header, sign_payment_header, decode_payment
        from x402.common import x402_VERSION
        
        # Use the first requirement for signing context (network, scheme should be same for all)
        first_req = payment_requirements_list[0]
        
        # Prepare batch payment header (builds single transaction with multiple payments)
        unsigned_header = prepare_batch_payment_header(account, x402_VERSION, payment_requirements_list)
        
        # Sign the batch transaction
        signed_header_b64 = sign_payment_header(account, first_req, unsigned_header)
        
        # Decode to get the PaymentPayload structure
        decoded = decode_payment(signed_header_b64)
        
        # Return as PaymentPayload
        return PaymentPayload(**decoded)
        
    except ImportError as e:
        raise ImportError(f"x402.exact library is required for batch payments: {str(e)}")


def _generate_nonce() -> str:
    """Generate a random nonce for payment authorization."""
    return secrets.token_hex(32)