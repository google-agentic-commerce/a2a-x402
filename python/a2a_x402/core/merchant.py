"""Payment requirements creation functions."""

from typing import Optional, Any, Union, cast
from x402.common import process_price_to_atomic_amount
from x402.types import Price
from ..types import (
    PaymentRequirements, 
    SupportedNetworks
)


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


