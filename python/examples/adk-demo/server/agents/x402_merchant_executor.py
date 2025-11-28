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
from payments_py.x402.extensions.nevermined import (
    validate_nevermined_extension,
    NEVERMINED
)


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
        from payments_py.x402 import NeverminedFacilitator
        
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
                from payments_py.x402 import PaymentRequirements
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
        print(f"\n🔵 [SERVER] Verifying payment...")
        print(f"   Payload version: {payload.x402_version}")
        print(f"   Payload scheme: {payload.scheme}")
        print(f"   Payload network: {payload.network}")
        
        # Validate v2 extensions if present
        if hasattr(payload, 'extensions') and payload.extensions:
            print(f"   🆕 V2 Extensions present: {list(payload.extensions.keys())}")
            
            # Validate Nevermined extension if present
            if NEVERMINED in payload.extensions:
                nvm_ext = payload.extensions[NEVERMINED]
                validation_result = validate_nevermined_extension(nvm_ext)
                
                if not validation_result["valid"]:
                    error_msgs = ", ".join(validation_result.get("errors", []))
                    print(f"   ⛔ Invalid Nevermined extension: {error_msgs}")
                    # Return invalid response instead of proceeding
                    return VerifyResponse(
                        is_valid=False,
                        invalid_reason=f"Invalid extension: {error_msgs}"
                    )
                else:
                    print(f"   ✅ Nevermined extension validated successfully")
        
        # Log requirements info
        if requirements:
            print(f"   Requirements:")
            print(f"     - Plan ID: {requirements.plan_id}")
            print(f"     - Agent ID: {requirements.agent_id}")
            print(f"     - Max Amount: {requirements.max_amount}")
        
        response = await self._facilitator.verify(payload, requirements)
        if response.is_valid:
            print("   ✅ Payment Verified on Blockchain!")
        else:
            print(f"   ⛔ Payment verification failed: {response.invalid_reason}")
        return response

    @override
    async def settle_payment(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """
        Settles the payment with the Nevermined facilitator.
        This burns credits on-chain and returns the transaction hash.
        """
        print(f"\n🔵 [SERVER] Settling payment...")
        
        response = await self._facilitator.settle(payload, requirements)
        if response.success:
            print(f"   ✅ Payment Settled on Blockchain!")
            print(f"   Transaction: {response.transaction}")
            print(f"   Network: {response.network}")
        else:
            print(f"   ⛔ Payment settlement failed: {response.error_reason}")
        return response
