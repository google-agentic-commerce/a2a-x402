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
    """Configuration for how a server expects to be paid"""
    price: Union[str, int, TokenAmount]
    pay_to_address: str
    network: str = "base"
    description: str = "Payment required..."
    mime_type: str = "application/json"
    max_timeout_seconds: int = 600
    resource: Optional[str] = None
    asset_address: Optional[str] = None

