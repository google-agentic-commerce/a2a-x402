"""A2A-specific message types for x402 protocol extension."""

from enum import Enum


class X402MessageType(str, Enum):
    """Message type identifiers for A2A x402 flow"""
    PAYMENT_REQUIRED = "x402.payment.required"      # Initial payment request
    PAYMENT_PAYLOAD = "x402.payment.payload"        # Signed payment submission
    PAYMENT_SETTLED = "x402.payment.settled"        # Settlement completion
