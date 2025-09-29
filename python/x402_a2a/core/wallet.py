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
"""Payment signing and processing helpers."""

import base64
import json
from binascii import Error as BinasciiError
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
    EIP3009Authorization,
    ExactSparkPaymentPayload,
    SparkPaymentType
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

    if selected_requirement.network == "spark":
        raise NotImplementedError(
            "Spark payments require an external settlement flow. "
            "Use create_spark_payment_payload after completing the payment."
        )

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
    if requirements.network == "spark":
        raise NotImplementedError(
            "Spark payments cannot be signed using the EIP-3009 helper. "
            "Use create_spark_payment_payload instead."
        )

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


def create_spark_payment_payload(
    payment_type: SparkPaymentType,
    *,
    transfer_id: Optional[str] = None,
    preimage: Optional[str] = None,
    txid: Optional[str] = None,
    x402_version: int = 1
) -> PaymentPayload:
    """Build a Spark payment payload following the exact scheme contract.

    Args:
        payment_type: Transport used to settle the Spark payment.
        transfer_id: Spark network transfer identifier required when
            payment_type is SPARK.
        preimage: Lightning preimage proof required when payment_type is
            LIGHTNING.
        txid: Bitcoin L1 transaction id required when payment_type is L1.
        x402_version: Protocol version carried in the payload (defaults to 1).

    Returns:
        PaymentPayload ready to embed in `X-PAYMENT` headers or A2A
        metadata.
    """

    spark_payload = ExactSparkPaymentPayload(
        payment_type=payment_type,
        transfer_id=transfer_id,
        preimage=preimage,
        txid=txid
    )

    return PaymentPayload.model_construct(
        x402_version=x402_version,
        scheme="exact",
        network="spark",
        payload=spark_payload
    )


def encode_spark_payment_header(payment_payload: PaymentPayload) -> str:
    """Encode a spark payment payload for use in the ``X-PAYMENT`` header."""

    if payment_payload.network.lower() != "spark":
        raise ValueError(
            "encode_spark_payment_header expects a Spark payment payload"
        )

    spark_payload = get_spark_payment_payload(payment_payload)

    payload_dict = {
        "x402Version": payment_payload.x402_version,
        "scheme": payment_payload.scheme,
        "network": payment_payload.network,
        "payload": _spark_payload_to_dict(spark_payload),
    }

    header_json = json.dumps(
        payload_dict,
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64.b64encode(header_json.encode("utf-8")).decode("utf-8")


def decode_spark_payment_header(header_value: str) -> PaymentPayload:
    """Decode an ``X-PAYMENT`` header back into a PaymentPayload instance."""

    try:
        decoded_bytes = base64.b64decode(header_value)
    except BinasciiError as exc:
        raise ValueError("Invalid base64 encoding in X-PAYMENT header") from exc

    try:
        payload_data = json.loads(decoded_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("Decoded X-PAYMENT header is not valid JSON") from exc

    return _parse_spark_header_payload(payload_data)


def _parse_spark_header_payload(payload_data: dict) -> PaymentPayload:
    """Internal helper to reuse parsing logic across spark utilities."""

    network = payload_data.get("network")
    if not isinstance(network, str) or network.lower() != "spark":
        raise ValueError("Decoded payload is not targeting the Spark network")

    payload_dict = payload_data.get("payload", {})
    spark_payload = ExactSparkPaymentPayload.model_validate(payload_dict)

    x402_version = payload_data.get(
        "x402Version",
        payload_data.get("x402_version", 1),
    )
    scheme = payload_data.get("scheme", "exact")

    return PaymentPayload.model_construct(
        x402_version=x402_version,
        scheme=scheme,
        network="spark",
        payload=spark_payload
    )


def _spark_payload_to_dict(spark_payload: ExactSparkPaymentPayload) -> dict:
    """Serialise the spark payload using the scheme's alias map."""

    payload_dict = spark_payload.model_dump(by_alias=True, exclude_none=True)
    payment_type = payload_dict.get("paymentType")
    if isinstance(payment_type, SparkPaymentType):
        payload_dict["paymentType"] = payment_type.value
    return payload_dict


def get_spark_payment_payload(
    payment_payload: PaymentPayload,
) -> ExactSparkPaymentPayload:
    """Return the structured Spark payload for a spark network PaymentPayload."""

    if payment_payload.network.lower() != "spark":
        raise ValueError("Payment payload is not targeting the Spark network")

    raw_payload = payment_payload.payload
    if isinstance(raw_payload, ExactSparkPaymentPayload):
        return raw_payload

    if isinstance(raw_payload, dict):
        spark_payload = ExactSparkPaymentPayload.model_validate(raw_payload)
        return spark_payload

    raise TypeError("Unsupported spark payload type")


def dump_payment_payload(payment_payload: PaymentPayload) -> dict:
    """Serialise PaymentPayload with Spark awareness for metadata transport."""

    data = payment_payload.model_dump(by_alias=True)
    if payment_payload.network.lower() != "spark":
        return data

    spark_payload = get_spark_payment_payload(payment_payload)
    data["payload"] = _spark_payload_to_dict(spark_payload)
    return data
