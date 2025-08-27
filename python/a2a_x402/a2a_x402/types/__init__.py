"""Types package for a2a_x402 - re-exports x402.types and A2A SDK types, adds A2A-specific extensions."""

# Re-export core A2A protocol types
from a2a.types import (
    Task,
    Message,
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    TaskState,
    TaskStatus
)

# Re-export A2A server execution types
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue

# Re-export core x402 protocol types
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
    SupportedNetworks
)

# Re-export x402 facilitator types
from x402.facilitator import (
    FacilitatorConfig,
    FacilitatorClient
)

# Export A2A-specific types
from .messages import (
    X402MessageType
)

from .state import (
    PaymentStatus,
    X402Metadata
)

from .errors import (
    X402Error,
    MessageError,
    ValidationError,
    PaymentError,
    StateError,
    X402ErrorCode,
    map_error_to_code
)

from .config import (
    X402_EXTENSION_URI,
    X402ExtensionConfig
)

# Import extension functions (from extension.py)
from ..extension import (
    get_extension_declaration,
    check_extension_activation,
    add_extension_activation_header
)

__all__ = [
    # Core A2A protocol types
    "Task",
    "Message",
    "AgentCard",
    "AgentCapabilities",
    "AgentSkill",
    "TaskState",
    "TaskStatus",

    # A2A server execution types
    "AgentExecutor",
    "RequestContext",
    "EventQueue",

    # Core x402 protocol types
    "PaymentRequirements",
    "x402PaymentRequiredResponse",
    "PaymentPayload",
    "VerifyResponse",
    "SettleResponse",
    "ExactEvmPaymentPayload",
    "ExactSuiPaymentPayload",
    "EIP3009Authorization",
    "TokenAmount",
    "TokenAsset",
    "EIP712Domain",
    "SupportedNetworks",

    # x402 facilitator types
    "FacilitatorConfig",
    "FacilitatorClient",

    # A2A-specific types
    "X402MessageType",
    "PaymentStatus",
    "X402Metadata",

    # Error types
    "X402Error",
    "MessageError",
    "ValidationError",
    "PaymentError",
    "StateError",
    "X402ErrorCode",
    "map_error_to_code",

    # Configuration
    "X402_EXTENSION_URI",
    "X402ExtensionConfig",

    # Extension functions
    "get_extension_declaration",
    "check_extension_activation",
    "add_extension_activation_header"
]
