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

from a2a_x402.executors import X402ServerExecutor
from .adk_merchant_agent import AdkMerchantAgent
from .mock_facilitator import MockFacilitator
from x402.types import PaymentPayload, PaymentRequirements, SettleResponse, VerifyResponse
from a2a_x402 import (
    FacilitatorClient,
    X402ExtensionConfig,
    PaymentStatus,
    X402Utils,
    get_extension_declaration
)


# ==============================================================================
# 1. Concrete Implementation of the X402 Wrapper
# This class connects the abstract server logic to a specific facilitator.
# ==============================================================================
class X402MerchantExecutor(X402ServerExecutor):
    """
    A concrete implementation of the X402ServerExecutor that uses a
    facilitator to verify and settle payments for the merchant.
    """

    def __init__(
        self, delegate: AgentExecutor, facilitator_client: FacilitatorClient
    ):
        super().__init__(delegate, X402ExtensionConfig())
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
