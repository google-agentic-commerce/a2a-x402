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
"""Configuration types for x402_a2a."""

from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel


from x402.types import TokenAmount


X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"


class PaymentVerificationMode(str, Enum):
    """Controls what verify_payment guarantees before delegate execution.

    FORMAT_ONLY:
        verify_payment checks signature and payload structure only — no
        on-chain interaction. SAFE FOR: low-value calls, idempotent work,
        or when settle_payment runs before delegate execution.
        The executor MUST settle BEFORE executing the delegate.

    SETTLEMENT_CHECK:
        verify_payment confirms the transaction is visible on-chain.
        Settlement runs AFTER execution. SAFE FOR: most use cases where
        ~1s block times are acceptable (Base mainnet, L2s).

    SETTLEMENT_FINAL:
        verify_payment waits for sufficient on-chain confirmations
        (controlled by required_confirmations). SAFE FOR: high-value
        flows, irreversible work, cross-chain scenarios.
    """

    FORMAT_ONLY = "format_only"
    SETTLEMENT_CHECK = "settlement_check"
    SETTLEMENT_FINAL = "settlement_final"


class x402ExtensionConfig(BaseModel):
    """Configuration for x402 extension."""

    extension_uri: str = X402_EXTENSION_URI
    version: str = "0.1"
    x402_version: int = 1
    required: bool = True
    verification_mode: PaymentVerificationMode = (
        PaymentVerificationMode.SETTLEMENT_CHECK
    )
    required_confirmations: int = 0


class x402ServerConfig(BaseModel):
    """Configuration for how a server expects to be paid"""

    price: Union[str, int, TokenAmount]
    pay_to_address: str
    network: str = "base"
    description: str = "Payment required..."
    mime_type: str = "application/json"
    max_timeout_seconds: int = 600
    resource: Optional[str] = None
    asset_address: Optional[str] = None
