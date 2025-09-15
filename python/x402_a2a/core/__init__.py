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
"""Core package exports for x402_a2a."""

from .merchant import create_payment_requirements
from .wallet import process_payment_required, process_payment
from .protocol import verify_payment, settle_payment
from .utils import (
    x402Utils,
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
from .agent import (
    create_x402_agent_card
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
    "x402Utils",
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
]
