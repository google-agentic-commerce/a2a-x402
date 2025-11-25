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
from x402_a2a.types import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from x402_a2a import x402ExtensionConfig


# ==============================================================================
# 1. Concrete Implementation of the x402 Wrapper
# This class connects the abstract server logic to Nevermined facilitator.
# ==============================================================================
class x402MerchantExecutor(x402ServerExecutor):
    """
    A concrete implementation of the x402ServerExecutor that uses the
    Nevermined facilitator to verify and settle payments on the blockchain.
    
    This executor always uses real blockchain transactions for payment
    verification and settlement via the Nevermined network.
    """

    def __init__(self, delegate: AgentExecutor):
        super().__init__(delegate, x402ExtensionConfig())

        print("--- Initializing Nevermined Facilitator ---")
        from x402_a2a.nvm import NeverminedFacilitator
        
        # Server uses merchant/service provider API key
        nvm_api_key = os.getenv("NVM_API_KEY_SERVER")
        if not nvm_api_key:
            raise ValueError(
                "NVM_API_KEY_SERVER environment variable is required. "
                "This should be the merchant's API key with permissions to verify and settle payments. "
                "Get your API key from https://nevermined.io/dashboard"
            )
        
        environment = os.getenv("NVM_ENVIRONMENT", "sandbox")
        self._facilitator = NeverminedFacilitator(
            nvm_api_key=nvm_api_key,
            environment=environment
        )
        print(f"✅ Nevermined Facilitator initialized for '{environment}' environment")
        print(f"   Using merchant API key for payment verification/settlement")

    @override
    def _extract_payment_requirements_from_context(
        self, task, context
    ):
        """
        Override to also check message metadata for payment requirements.
        This is needed for the Nevermined flow where requirements are sent with the payment.
        """
        # First try to get from message metadata (Nevermined flow)
        if context.message and hasattr(context.message, "metadata") and context.message.metadata:
            requirements_dict = context.message.metadata.get("payment_requirements")
            if requirements_dict:
                from x402_a2a.nvm import PaymentRequirements
                return PaymentRequirements.model_validate(requirements_dict)
        
        # Fall back to the default behavior (stored requirements)
        return super()._extract_payment_requirements_from_context(task, context)

    @override
    async def verify_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """
        Verifies the payment with the Nevermined facilitator.
        This checks if the subscriber has sufficient permissions/credits on-chain.
        """
        response = await self._facilitator.verify(payload, requirements)
        if response.is_valid:
            print("✅ Payment Verified on Blockchain!")
        else:
            print("⛔ Payment verification failed.")
        return response

    @override
    async def settle_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """
        Settles the payment with the Nevermined facilitator.
        This burns credits on-chain and returns the transaction hash.
        """
        response = await self._facilitator.settle(payload, requirements)
        if response.success:
            print(f"✅ Payment Settled on Blockchain! Tx: {response.transaction}")
        else:
            print(f"⛔ Payment settlement failed: {response.error_reason}")
        return response
