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
"""Helpers for integrating Cashu payments with the x402 A2A SDK."""

from __future__ import annotations

from typing import Any, cast

from x402.common import x402_VERSION
from x402.types import Price

from ...types import (
    CashuPaymentPayload,
    PaymentPayload,
    PaymentRequirements,
    SupportedNetworks,
)


_DEFAULT_CASHU_MINTS: dict[str, str] = {
    "bitcoin-testnet": "https://nofees.testnut.cashu.space/",
    "bitcoin-mainnet": "https://mint.minibits.cash/Bitcoin",
}


def _resolve_identifiers(
    collection: list[str] | None, singular: str | None
) -> list[str]:
    """Return the first non-empty list between collection and singular."""
    if collection:
        return collection
    if singular:
        return [singular]
    return []


def create_cashu_payment_requirements(
    *,
    price: Price,
    pay_to_address: str,
    resource: str,
    network: str = "base",
    description: str = "",
    mime_type: str = "application/json",
    scheme: str = "cashu-token",
    max_timeout_seconds: int = 600,
    output_schema: Any | None = None,
    mint_url: str | None = None,
    mint_urls: list[str] | None = None,
    facilitator_url: str | None = None,
    keyset_id: str | None = None,
    keyset_ids: list[str] | None = None,
    unit: str = "sat",
    locks: Any | None = None,
    **kwargs: Any,
) -> PaymentRequirements:
    """Build a Cashu-specific `PaymentRequirements` object."""
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

    extra_kwargs = dict(kwargs)
    asset = extra_kwargs.pop("asset", None)

    return PaymentRequirements(
        scheme=scheme,
        network=cast(SupportedNetworks, network),
        asset=asset,
        pay_to=pay_to_address,
        max_amount_required=amount_str,
        resource=resource,
        description=description,
        mime_type=mime_type,
        max_timeout_seconds=max_timeout_seconds,
        output_schema=output_schema,
        extra=extra,
        **extra_kwargs,
    )


def process_cashu_payment(
    *,
    requirements: PaymentRequirements,
    cashu_payload: CashuPaymentPayload | None,
) -> PaymentPayload:
    """Create a `PaymentPayload` for Cashu flows."""
    if requirements.scheme != "cashu-token":
        raise ValueError("process_cashu_payment expects cashu-token requirements")

    if cashu_payload is None:
        raise ValueError(
            "cashu_payload must be provided when processing cashu-token payments"
        )

    extra = requirements.extra if isinstance(requirements.extra, dict) else {}
    accepted_mints = set(extra.get("mints", []))
    if accepted_mints:
        payload_mints = {token.mint for token in cashu_payload.tokens}
        missing = sorted(payload_mints - accepted_mints)
        if missing:
            raise ValueError(
                "Cashu payload contains mints not accepted by the payment requirements: "
                + ", ".join(missing)
            )

    if len(cashu_payload.encoded) != len(cashu_payload.tokens):
        raise ValueError(
            "Cashu payload encoded tokens must align with provided token entries"
        )

    return PaymentPayload(
        x402_version=x402_VERSION,
        scheme=requirements.scheme,
        network=requirements.network,
        payload=cashu_payload,
    )
