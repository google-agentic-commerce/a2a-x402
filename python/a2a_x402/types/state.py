"""Payment state definitions, metadata keys, and state management types."""

from enum import Enum


class PaymentStatus(str, Enum):
    """Protocol-defined payment states for A2A flow"""
    PAYMENT_REQUIRED = "payment-required"    # Payment requested
    PAYMENT_SUBMITTED = "payment-submitted"  # Payment signed and submitted
    PAYMENT_REJECTED = "payment-rejected"    # Payment requirements rejected by client
    PAYMENT_PENDING = "payment-pending"      # Payment being processed
    PAYMENT_COMPLETED = "payment-completed"  # Payment settled successfully
    PAYMENT_FAILED = "payment-failed"        # Payment processing failed


class X402Metadata:
    """Spec-defined metadata key constants"""
    STATUS_KEY = "x402.payment.status"
    REQUIRED_KEY = "x402.payment.required"      # Contains x402PaymentRequiredResponse
    PAYLOAD_KEY = "x402.payment.payload"        # Contains PaymentPayload
    RECEIPTS_KEY = "x402.payment.receipts"      # Contains array of x402SettleResponse objects
    ERROR_KEY = "x402.payment.error"            # Error code (when failed)