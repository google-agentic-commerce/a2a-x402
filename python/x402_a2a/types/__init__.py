# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Types package for x402_a2a - re-exports x402.types and A2A SDK types, adds A2A-specific extensions."""


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
    x402Metadata
)

from .errors import (
    x402Error,
    MessageError,
    ValidationError,
    PaymentError,
    StateError,
    x402PaymentRequiredException,
    x402ErrorCode,
    map_error_to_code
)

from .config import (
    X402_EXTENSION_URI,
    x402ExtensionConfig,
    x402ServerConfig
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
    "x402Metadata",

    "x402Error",
    "MessageError", 
    "ValidationError",
    "PaymentError",
    "StateError",
    "x402PaymentRequiredException",
    "x402ErrorCode",
    "map_error_to_code",

    "X402_EXTENSION_URI",
    "x402ExtensionConfig",
    "x402ServerConfig",

    "get_extension_declaration",
    "check_extension_activation", 
    "add_extension_activation_header"
]
