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
"""Payment signing and processing functions."""

from typing import Optional
from eth_account import Account
from x402.clients.base import x402Client
from x402.common import x402_VERSION
from x402.exact import prepare_payment_header, sign_payment_header, decode_payment

from ..types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload,
    ExactPaymentPayload,
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
    
    # Create payment payload
    return process_payment(selected_requirement, account, max_value)


def process_payment(
    requirements: PaymentRequirements,
    account: Account,
    max_value: Optional[int] = None
) -> PaymentPayload:
    """Create PaymentPayload using proper x402.exact signing logic.
    Same as create_payment_header but returns PaymentPayload object (not base64 encoded).
    
    Args:
        requirements: Single PaymentRequirements to sign
        account: Ethereum account for signing
        max_value: Maximum payment value willing to pay
        
    Returns:
        Signed PaymentPayload object
    """
    # TODO: Future x402 library update will provide direct PaymentPayload creation
    # For now, we use the prepare -> sign -> decode pattern
    
    # Step 1: Prepare unsigned payment header
    unsigned_payload = prepare_payment_header(
        sender_address=account.address,
        x402_version=x402_VERSION,
        payment_requirements=requirements
    )
    
    # Step 2: Sign the header (returns base64-encoded complete payload)
    # Handle nonce conversion for x402.exact compatibility
    nonce_raw = unsigned_payload["payload"]["authorization"]["nonce"]
    if isinstance(nonce_raw, bytes):
        unsigned_payload["payload"]["authorization"]["nonce"] = nonce_raw.hex()
    
    signed_base64 = sign_payment_header(
        account=account,
        payment_requirements=requirements,
        header=unsigned_payload
    )
    
    # Step 3: Decode back to proper PaymentPayload structure
    signed_payload = decode_payment(signed_base64)
    
    # Step 4: Convert to our PaymentPayload types
    auth_data = signed_payload["payload"]["authorization"]
    authorization = EIP3009Authorization(
        from_=auth_data["from"],
        to=auth_data["to"],
        value=auth_data["value"],
        valid_after=auth_data["validAfter"],
        valid_before=auth_data["validBefore"],
        nonce=auth_data["nonce"]
    )
    
    exact_payload = ExactPaymentPayload(
        signature=signed_payload["payload"]["signature"],
        authorization=authorization
    )
    
    return PaymentPayload(
        x402_version=signed_payload["x402Version"],
        scheme=signed_payload["scheme"],
        network=signed_payload["network"],
        payload=exact_payload
    )

