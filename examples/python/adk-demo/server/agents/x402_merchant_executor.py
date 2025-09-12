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
from typing import List, override

from a2a.server.apps import A2AStarletteApplication
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from starlette.routing import BaseRoute

# Import the executors and wrappers
from ._adk_agent_executor import ADKAgentExecutor

from a2a_x402.executors import x402ServerExecutor
from .adk_merchant_agent import AdkMerchantAgent
from .mock_facilitator import MockFacilitator
from a2a_x402.types import PaymentPayload, PaymentRequirements, SettleResponse, VerifyResponse
from a2a_x402 import (
    FacilitatorClient,
    x402ExtensionConfig
)


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
        self, delegate: AgentExecutor, facilitator_client: FacilitatorClient
    ):
        super().__init__(delegate, x402ExtensionConfig())
        self._facilitator = facilitator_client

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