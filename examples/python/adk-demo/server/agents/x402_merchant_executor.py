from typing import List, override

from a2a.server.apps import A2AStarletteApplication
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from starlette.routing import BaseRoute
import os

# Import the executors and wrappers
from ._adk_agent_executor import ADKAgentExecutor

from a2a_x402.executors import x402ServerExecutor
from .adk_merchant_agent import AdkMerchantAgent
from .mock_facilitator import MockFacilitator
from a2a_x402.types import PaymentPayload, PaymentRequirements, SettleResponse, VerifyResponse
from a2a_x402 import (
    FacilitatorClient,
    x402ExtensionConfig,
    FacilitatorConfig
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
        self, delegate: AgentExecutor, facilitator_config: FacilitatorConfig = None
    ):
        super().__init__(delegate, x402ExtensionConfig())
        use_mock = os.getenv("USE_MOCK_FACILITATOR", "true").lower() == "true"
        if use_mock:
            print("--- Using Mock Facilitator ---")
            self._facilitator = MockFacilitator()
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
