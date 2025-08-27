"""Configuration types for a2a_x402."""

from typing import Optional, Union
from pydantic import BaseModel, Field


from x402.types import TokenAmount


X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"


class X402ExtensionConfig(BaseModel):
    """Configuration for x402 extension."""
    extension_uri: str = X402_EXTENSION_URI
    version: str = "0.1"
    x402_version: int = 1
    required: bool = True


class X402ServerConfig(BaseModel):
    """Configuration for X402ServerExecutor payment requirements.
    
    This config defines how the server expects to be paid when the x402
    extension is active. Similar to x402's middleware configuration.
    """

    price: Union[str, int, TokenAmount] = Field(
        description="Payment price. Can be Money (e.g., '$0.10', 0.10) or TokenAmount"
    )
    pay_to_address: str = Field(
        description="Ethereum address to receive the payment"
    )

    network: str = Field(
        default="base",
        description="Blockchain network (e.g., 'base', 'base-sepolia')"
    )
    description: str = Field(
        default="Payment required for this service",
        description="Human-readable description of what is being purchased"
    )
    mime_type: str = Field(
        default="application/json",
        description="MIME type of the resource"
    )
    max_timeout_seconds: int = Field(
        default=600,
        description="Maximum time allowed for payment"
    )
    resource: Optional[str] = Field(
        default=None,
        description="Resource identifier (e.g., '/generate-image')"
    )

    asset_address: Optional[str] = Field(
        default=None,
        description="Token contract address (auto-derived for USDC if None)"
    )