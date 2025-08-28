"""Core package exports for a2a_x402."""

from .merchant import create_payment_requirements
from .wallet import process_payment_required, process_payment
from .protocol import verify_payment, settle_payment
from .utils import (
    X402Utils,
    create_payment_submission_message,
    extract_task_id
)
from .helpers import (
    require_payment,
    require_payment_choice,
    paid_service,
    smart_paid_service,
    create_tiered_payment_options,
    check_payment_context
)

__all__ = [
    # Core merchant/wallet functions
    "create_payment_requirements",
    "process_payment_required",
    "process_payment",
    
    # Protocol functions
    "verify_payment",
    "settle_payment",
    
    # Utilities
    "X402Utils",
    "create_payment_submission_message",
    "extract_task_id",
    
    # Helper functions (new exception-based approach)
    "require_payment",
    "require_payment_choice", 
    "paid_service",
    "smart_paid_service",
    "create_tiered_payment_options",
    "check_payment_context"
]