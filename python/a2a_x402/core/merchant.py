"""Payment requirements creation functions."""

from typing import Optional, Any
from ..types import PaymentRequirements, SupportedNetworks


def create_payment_requirements(
    price: str,
    resource: str,
    merchant_address: str,
    network: str = "base",
    description: str = "",
    mime_type: str = "application/json",
    scheme: str = "exact",
    max_timeout_seconds: int = 600,
    asset: Optional[str] = None,
    output_schema: Optional[Any] = None,
    **kwargs
) -> PaymentRequirements:
    """Creates PaymentRequirements object for A2A payment requests.
    
    Args:
        price: Payment amount in atomic units (e.g., "1000000" for USDC)
        resource: Resource identifier (e.g., "/generate-image")
        merchant_address: Recipient wallet address
        network: Blockchain network (default: "base")
        description: Human-readable description
        mime_type: Expected response content type
        scheme: Payment scheme (default: "exact")
        max_timeout_seconds: Payment validity timeout
        asset: Token contract address (auto-derived if None)
        output_schema: Response schema
        **kwargs: Additional fields passed to PaymentRequirements
        
    Returns:
        PaymentRequirements object ready for x402PaymentRequiredResponse
    """
    # Auto-derive asset address based on network if not provided
    if asset is None:
        # Default asset addresses for supported networks
        asset_map = {
            # EVM networks - USDC addresses
            "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913",
            "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            "avalanche": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
            "avalanche-fuji": "0x5425890298aed601595a70AB815c96711a31Bc65",
            # Sui networks - USDC on Sui
            "sui": "0xa1ec7fc00a6f40db9693ad1415d0c193ad3906494428cf252621037bd7117e29::usdc::USDC",
            "sui-testnet": "0xa1ec7fc00a6f40db9693ad1415d0c193ad3906494428cf252621037bd7117e29::usdc::USDC",
        }
        asset = asset_map.get(network, "0x833589fCD6eDb6E08f4c7C32D4f71b54bda02913")
    
    return PaymentRequirements(
        scheme=scheme,
        network=network,
        asset=asset,
        pay_to=merchant_address,
        max_amount_required=price,
        resource=resource,
        description=description,
        mime_type=mime_type,
        max_timeout_seconds=max_timeout_seconds,
        output_schema=output_schema,
        **kwargs
    )