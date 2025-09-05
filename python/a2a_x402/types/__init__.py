"""Types package for a2a_x402 - re-exports x402.types and A2A SDK types, adds A2A-specific extensions."""


from a2a.types import (
    Task,
    Message,
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    TaskState,
    TaskStatus
)
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
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
from x402.facilitator import (
    FacilitatorConfig,
    FacilitatorClient
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
    X402PaymentRequiredException,
    X402ErrorCode,
    map_error_to_code
)

from .config import (
    X402_EXTENSION_URI,
    X402ExtensionConfig,
    X402ServerConfig
)
from ..extension import (
    get_extension_declaration,
    check_extension_activation,
    add_extension_activation_header
)

__all__ = [

    "Task",
    "Message", 
    "AgentCard",
    "AgentCapabilities",
    "AgentSkill",
    "TaskState",
    "TaskStatus",

    "AgentExecutor",
    "RequestContext", 
    "EventQueue",

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

    "FacilitatorConfig",
    "FacilitatorClient",

    "PaymentStatus",
    "X402Metadata",

    "X402Error",
    "MessageError", 
    "ValidationError",
    "PaymentError",
    "StateError",
    "X402PaymentRequiredException",
    "X402ErrorCode",
    "map_error_to_code",

    "X402_EXTENSION_URI",
    "X402ExtensionConfig",
    "X402ServerConfig",

    "get_extension_declaration",
    "check_extension_activation", 
    "add_extension_activation_header"
]