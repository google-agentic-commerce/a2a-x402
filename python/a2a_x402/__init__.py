"""a2a_x402 - x402 Payment Protocol Extension for A2A."""

# Core x402 Protocol Types (from x402.types)
from x402.types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload,
    VerifyResponse,
    SettleResponse,
    ExactPaymentPayload,
    EIP3009Authorization,
    TokenAmount,
    TokenAsset,
    EIP712Domain,
    SupportedNetworks,
    VerifyResponse
)

from x402.facilitator import (
    FacilitatorConfig,
    FacilitatorClient
)

# A2A Extension Types & Functions
from .types import (
    # Extension Constants
    X402_EXTENSION_URI,
    
    # A2A-Specific Types
    PaymentStatus,
    X402Metadata,
    
    # Configuration
    X402ExtensionConfig,
    
    # Error Types
    X402Error,
    MessageError,
    ValidationError,
    PaymentError,
    StateError,
    X402PaymentRequiredException,
    X402ErrorCode,
    
    # Extension utilities
    get_extension_declaration,
    check_extension_activation,
    add_extension_activation_header
)

# Core Functions
from .core import (
    # Traditional core functions
    create_payment_requirements,
    process_payment_required,
    process_payment,
    verify_payment,
    settle_payment,
    
    # State Management
    X402Utils,
    create_payment_submission_message,
    extract_task_id,
    
    # Helper functions (new exception-based approach)
    require_payment,
    require_payment_choice,
    paid_service,
    smart_paid_service,
    create_tiered_payment_options,
    check_payment_context,
    
    # Agent utilities
    create_x402_agent_card
)

# Optional Middleware
from .executors import (
    X402BaseExecutor,
    X402ServerExecutor,
    X402ClientExecutor
)

__version__ = "1.0.0"

__all__ = [
    # Core x402 Protocol Types
    "PaymentRequirements",
    "x402PaymentRequiredResponse",
    "PaymentPayload", 
    "VerifyResponse",
    "SettleResponse",
    "ExactPaymentPayload",
    "EIP3009Authorization",
    "TokenAmount",
    "TokenAsset", 
    "EIP712Domain",
    "SupportedNetworks",
    "VerifyResponse",
    
    # Facilitator
    "FacilitatorConfig",
    "FacilitatorClient",
    
    # Extension Constants
    "X402_EXTENSION_URI",
    
    # A2A-Specific Types
    "PaymentStatus",
    "X402Metadata",
    
    # Configuration
    "X402ExtensionConfig",
    
    # Error Types
    "X402Error",
    "MessageError",
    "ValidationError", 
    "PaymentError",
    "StateError",
    "X402PaymentRequiredException",
    "X402ErrorCode",
    
    # Extension utilities
    "get_extension_declaration",
    "check_extension_activation",
    "add_extension_activation_header",
    
    # Core Functions
    "create_payment_requirements",
    "process_payment_required", 
    "process_payment",
    "verify_payment",
    "settle_payment",
    
    # State Management
    "X402Utils",
    "create_payment_submission_message",
    "extract_task_id",
    
    # Helper functions (new exception-based approach)
    "require_payment",
    "require_payment_choice",
    "paid_service", 
    "smart_paid_service",
    "create_tiered_payment_options",
    "check_payment_context",
    
    # Agent utilities
    "create_x402_agent_card",
    
    # Optional Middleware
    "X402BaseExecutor",
    "X402ServerExecutor",
    "X402ClientExecutor"
]
