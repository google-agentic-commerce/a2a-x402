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
"""x402_a2a - x402 Payment Protocol Extension for A2A."""

# Core x402 Protocol Types (from x402.types)
from x402.types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload,
    SettleResponse,
    ExactPaymentPayload,
    EIP3009Authorization,
    TokenAmount,
    TokenAsset,
    EIP712Domain,
    SupportedNetworks,
    VerifyResponse,
)

from x402.facilitator import FacilitatorConfig, FacilitatorClient

# A2A Extension Types & Functions
from .types import (
    # Extension Constants
    X402_EXTENSION_URI,
    # A2A-Specific Types
    PaymentStatus,
    x402Metadata,
    # Configuration
    x402ExtensionConfig,
    # Error Types
    x402Error,
    MessageError,
    ValidationError,
    PaymentError,
    StateError,
    x402PaymentRequiredException,
    x402ErrorCode,
    # Extension utilities
    get_extension_declaration,
    check_extension_activation,
    add_extension_activation_header,
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
    x402Utils,
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
    create_x402_agent_card,
)

# Optional Middleware
from .executors import x402BaseExecutor, x402ServerExecutor

__all__ = [
    "X402_EXTENSION_URI",
    "create_payment_requirements",
    "settle_payment",
    "process_payment_required",
    "process_payment",
    "verify_payment",
    "x402Utils",
    "PaymentStatus",
    "x402MessageType",
    "x402Metadata",
    "x402ExtensionConfig",
    "x402PaymentRequiredException",
    "require_payment",
    "require_payment_choice",
    "paid_service",
    "smart_paid_service",
    "create_tiered_payment_options",
    "x402ErrorCode",
    "x402Error",
    "MessageError",
    "ValidationError",
    "PaymentError",
    "StateError",
    "get_extension_declaration",
    "check_extension_activation",
    "add_extension_activation_header",
    "create_payment_submission_message",
    "extract_task_id",
    "map_error_to_code",
    "x402BaseExecutor",
    "x402ServerExecutor",
]
