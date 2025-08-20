"""Configuration types for a2a_x402."""

from pydantic import BaseModel

# Extension URI constant from spec section 2
X402_EXTENSION_URI = "https://google-a2a.github.io/A2A/extensions/payments/x402/v0.1"


class X402ExtensionConfig(BaseModel):
    """Configuration for x402 extension."""
    extension_uri: str = X402_EXTENSION_URI
    version: str = "0.1"
    x402_version: int = 1
    required: bool = True