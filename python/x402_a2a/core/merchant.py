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
"""Payment requirements creation functions."""

from typing import Optional, Any, cast
from x402.common import process_price_to_atomic_amount
from x402.types import Price
from ..types import (
    PaymentRequirements, 
    SupportedNetworks
)


_DEFAULT_CASHU_MINTS: dict[str, str] = {
    "bitcoin-testnet": "https://nofees.testnut.cashu.space/",
    "bitcoin-mainnet": "https://mint.minibits.cash/Bitcoin",
}


def _resolve_identifiers(collection: Optional[list[str]], singular: Optional[str]) -> list[str]:
    """Return the first non-empty list between collection and singular."""
    if collection:
        return collection
    if singular:
        return [singular]
    return []


def create_payment_requirements(
    price: Price,
    pay_to_address: str,
    resource: str,
    network: str = "base",
    description: str = "",
    mime_type: str = "application/json",
    scheme: str = "exact",
    max_timeout_seconds: int = 600,
    output_schema: Optional[Any] = None,
    mint_url: Optional[str] = None,
    mint_urls: Optional[list[str]] = None,
    facilitator_url: Optional[str] = None,
    keyset_id: Optional[str] = None,
    keyset_ids: Optional[list[str]] = None,
    unit: str = "sat",
    locks: Optional[Any] = None,
    **kwargs
) -> PaymentRequirements:
    """Creates PaymentRequirements for A2A payment requests.
    
    Args:
        price: Payment price. Can be:
            - Money: USD amount as string/int (e.g., "$3.10", 0.10, "0.001") - defaults to USDC
            - TokenAmount: Custom token amount with asset information
        pay_to_address: Ethereum address to receive the payment
        resource: Resource identifier (e.g., "/generate-image")
        network: Blockchain network (default: "base")
        description: Human-readable description
        mime_type: Expected response content type
        scheme: Payment scheme (default: "exact")
        max_timeout_seconds: Payment validity timeout
        output_schema: Response schema
        **kwargs: Additional fields passed to PaymentRequirements
        
    Returns:
        PaymentRequirements object ready for x402PaymentRequiredResponse
    """

    if scheme == "cashu-token":
        resolved_mints = _resolve_identifiers(mint_urls, mint_url)

        if not resolved_mints:
            default_mint = _DEFAULT_CASHU_MINTS.get(network)
            if default_mint:
                resolved_mints = [default_mint]

        if not resolved_mints:
            raise ValueError(
                f"A 'mint_url' must be provided for 'cashu-token' when network '{network}' has no default mint."
            )

        if isinstance(price, (int, float)):
            if isinstance(price, float) and price != int(price):
                raise ValueError("cashu-token price must be a whole number of satoshis")
            amount_str = str(int(price))
        elif isinstance(price, str):
            amount_str = price.strip()
            if not amount_str.isdigit():
                raise ValueError("cashu-token price string must be an integer")
        elif isinstance(price, dict):
            raise ValueError("cashu-token scheme expects a numeric price, not TokenAmount")
        else:
            raise ValueError("Unsupported price type for cashu-token scheme")

        extra: dict[str, Any] = {"mints": resolved_mints, "unit": unit}
        if facilitator_url:
            extra["facilitatorUrl"] = facilitator_url
        resolved_keysets = _resolve_identifiers(keyset_ids, keyset_id)
        if resolved_keysets:
            extra["keysetIds"] = resolved_keysets
        if locks is not None:
            extra["nut10"] = locks

        return PaymentRequirements(
            scheme=scheme,
            network=cast(SupportedNetworks, network),
            asset=kwargs.get("asset"),
            pay_to=pay_to_address,
            max_amount_required=amount_str,
            resource=resource,
            description=description,
            mime_type=mime_type,
            max_timeout_seconds=max_timeout_seconds,
            output_schema=output_schema,
            extra=extra,
            **kwargs
        )

    max_amount_required, asset_address, eip712_domain = process_price_to_atomic_amount(price, network)

    return PaymentRequirements(
        scheme=scheme,
        network=cast(SupportedNetworks, network),
        asset=asset_address,
        pay_to=pay_to_address,
        max_amount_required=max_amount_required,
        resource=resource,
        description=description,
        mime_type=mime_type,
        max_timeout_seconds=max_timeout_seconds,
        output_schema=output_schema,
        extra=eip712_domain,
        **kwargs
    )
