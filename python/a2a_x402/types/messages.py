"""A2A-specific message types for x402 protocol extension."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel


class X402MessageType(str, Enum):
    """Message type identifiers for A2A x402 flow"""
    PAYMENT_REQUIRED = "x402.payment.required"      # Initial payment request
    PAYMENT_PAYLOAD = "x402.payment.payload"        # Signed payment submission
    PAYMENT_SETTLED = "x402.payment.settled"        # Settlement completion


class x402SettleResponse(BaseModel):
    """A2A settlement response - spec section 5.5."""
    success: bool                                    # Required by spec
    error_reason: Optional[str] = Field(default=None, alias="errorReason")  # Optional
    transaction: Optional[str] = None                # Optional, only if success=true
    network: str                                     # Required by spec  
    payer: Optional[str] = None                      # Optional
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )