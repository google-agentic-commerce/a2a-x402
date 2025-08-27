"""A2A-specific message types for x402 protocol extension."""

from enum import Enum


class X402MessageType(str, Enum):
    """Message type identifiers for A2A x402 flow
    
    These message types are intended for use in Message.metadata to identify
    the type of x402 payment flow message. They correspond to the payment states
    but are used for message classification rather than state tracking.
    
    Usage:
        message.metadata["message_type"] = X402MessageType.PAYMENT_REQUIRED
    """
    PAYMENT_REQUIRED = "x402.payment.required"      # Initial payment request
    PAYMENT_PAYLOAD = "x402.payment.payload"        # Signed payment submission
    PAYMENT_SETTLED = "x402.payment.settled"        # Settlement completion
