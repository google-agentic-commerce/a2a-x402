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
import os
from typing import override

from a2a.server.agent_execution import AgentExecutor

# Import the executors and wrappers

from x402_a2a.executors import x402ServerExecutor
from .local_facilitator import LocalFacilitator
from x402_a2a.types import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from x402_a2a import FacilitatorClient, x402ExtensionConfig, FacilitatorConfig


# ==============================================================================
# 1. Concrete Implementation of the x402 Wrapper
# This class connects the abstract server logic to a specific facilitator.
# ==============================================================================
class x402MerchantExecutor(x402ServerExecutor):
    """
    A concrete implementation of the x402ServerExecutor that uses a
    facilitator to verify and settle payments for the merchant.
    """

    def __init__(
        self, delegate: AgentExecutor, facilitator_config: FacilitatorConfig = None
    ):
        super().__init__(delegate, x402ExtensionConfig())

        use_mock = os.getenv("USE_MOCK_FACILITATOR", "true").lower() == "true"
        if use_mock:
            print("--- Using Mock Facilitator ---")
            self._facilitator = LocalFacilitator()
        else:
            print("--- Using REAL Facilitator ---")
            self._facilitator = FacilitatorClient(facilitator_config)

    @override
    async def verify_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """Verifies the payment with the facilitator."""
        response = await self._facilitator.verify(payload, requirements)
        if response.is_valid:
            print("✅ Payment Verified!")
        else:
            print("⛔ Payment failed verification.")
        return response

    @override
    async def settle_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """Settles the payment with the facilitator."""

        response = await self._facilitator.settle(payload, requirements)
        if response.success:
            print("✅ Payment Settled!")
        else:
            print("⛔ Payment failed to settle.")
        return response
