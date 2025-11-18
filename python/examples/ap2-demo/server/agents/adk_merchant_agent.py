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
import hashlib
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from typing import Any, override

import httpx
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from ap2.types.mandate import CartContents, CartMandate, CART_MANDATE_DATA_KEY
from ap2.types.payment_receipt import (
    PAYMENT_RECEIPT_DATA_KEY,
    PaymentCurrencyAmount,
    PaymentReceipt,
    Success,
)
from ap2.types.payment_request import PaymentRequest
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from .base_agent import BaseAgent
from .local_facilitator import LocalFacilitator
from x402_a2a import get_extension_declaration
from x402_a2a.types import (
    ExactPaymentPayload,
    EIP3009Authorization,
    PaymentPayload,
    PaymentRequirements,
)

logger = logging.getLogger(__name__)


class AdkMerchantAgent(BaseAgent):
    """
    Defines the ADK LlmAgent for the merchant and its corresponding AgentCard.
    The business logic is implemented as tools.
    """

    def __init__(
        self,
    ):
        load_dotenv()
        self._wallet_address = os.getenv("MERCHANT_WALLET_ADDRESS")
        if not self._wallet_address:
            raise ValueError("MERCHANT_WALLET_ADDRESS environment variable not set.")
        self._facilitator = LocalFacilitator()
        self._current_payment_requirements = None  # To hold requirements across turns

    def _get_product_price(self, product_name: str) -> int:
        """Generates a deterministic price for a product in the smallest unit (e.g., 10^-6 for USDC)."""
        # Simple deterministic price for demo purposes
        return random.randint(1 * 10**6, 5 * 10**6)  # Price between 1 and 5 USDC

    async def get_product_details_and_create_cart(
        self, product_name: str
    ) -> dict[str, Any]:
        """
        Creates a signed CartMandate for a given product, including payment details.
        """
        if not product_name:
            return {"error": "Product name cannot be empty."}

        price_in_smallest_unit = self._get_product_price(product_name)
        price_in_usd = f"{price_in_smallest_unit / 1000000:.2f}"

        # 1. Construct the PaymentRequirements that the facilitator will enforce
        requirements = PaymentRequirements(
            scheme="exact",
            network="base-sepolia",
            asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # USDC
            pay_to=self._wallet_address,
            approve_to=self._wallet_address,  # The merchant is its own facilitator
            max_amount_required=str(price_in_smallest_unit),
            description=f"Payment for: {product_name}",
            resource=f"https://example.com/product/{product_name}",
            mime_type="application/json",
            max_timeout_seconds=1200,
            extra={
                "name": product_name,
                "description": f"Your order for {product_name}",
            },
        )

        # 2. Construct the x402 Payment Requirement (for embedding in the cart)
        x402_payment_required = {
            "x402.payment.required": {
                "x402Version": 1,
                "accepts": [
                    {
                        "scheme": requirements.scheme,
                        "network": requirements.network,
                        "asset": requirements.asset,
                        "payTo": requirements.pay_to,
                        "maxAmountRequired": requirements.max_amount_required,
                    }
                ],
            }
        }

        # 3. Construct the AP2 Payment Request
        payment_request = PaymentRequest(
            method_data=[
                {
                    "supported_methods": "https://www.x402.org/",
                    "data": x402_payment_required,
                }
            ],
            details={
                "id": f"order_{product_name.lower().replace(' ', '_')}_{uuid.uuid4()}",
                "display_items": [
                    {
                        "label": product_name,
                        "amount": {"currency": "USDC", "value": price_in_usd},
                    }
                ],
                "total": {
                    "label": "Total",
                    "amount": {"currency": "USDC", "value": price_in_usd},
                },
            },
        )

        # 4. Construct the Cart Contents
        cart_contents = CartContents(
            id=f"cart_{product_name.lower().replace(' ', '_')}_{uuid.uuid4()}",
            user_cart_confirmation_required=True,
            payment_request=payment_request,
            cart_expiry=(
                datetime.now(timezone.utc) + timedelta(minutes=15)
            ).isoformat(),
            merchant_name="ADK Merchant",
        )

        # 5. Sign the Cart Contents
        try:
            payload_to_sign = cart_contents.model_dump_json()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{os.getenv('LOCAL_WALLET_URL', 'http://localhost:5001')}/sign", json={"payload": payload_to_sign}
                )
                response.raise_for_status()
                signature_data = response.json()
                merchant_signature = signature_data.get("signature")
        except httpx.RequestError as e:
            return {"error": f"Failed to contact signing service: {e}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred during signing: {e}"}

        # 6. Create the final Cart Mandate
        cart_mandate = CartMandate(
            contents=cart_contents,
            merchant_authorization=merchant_signature,
        )

        # 7. Return a dictionary containing both the A2A Artifact
        #    and the context to be saved by the executor.
        cart_mandate_data = {
            CART_MANDATE_DATA_KEY: cart_mandate.model_dump(by_alias=True)
        }
        return {
            "artifact": {
                "artifactId": f"cart-mandate-{uuid.uuid4()}",
                "name": "AP2 CartMandate",
                "parts": [
                    {
                        "kind": "data",
                        "data": cart_mandate_data,
                    }
                ],
                "extensions": [
                    "https://github.com/google-agentic-commerce/ap2/tree/v0.1",
                    "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2",
                ],
            },
            "context_to_save": {"payment_requirements": requirements.model_dump()},
        }

    async def process_payment(self, payment_mandate: dict[str, Any]) -> dict[str, Any]:
        """Processes the payment by verifying it with a mock facilitator."""
        try:
            # 1. Extract the payment payload from the mandate
            payment_payload_dict = (
                payment_mandate.get("payment_mandate_contents", {})
                .get("payment_response", {})
                .get("details")
            )
            if not payment_payload_dict:
                return {"error": "Payment payload not found in the mandate."}

            # 2. Reconstruct the PaymentPayload object
            auth_dict = payment_payload_dict["payload"]["authorization"]
            payment_payload = PaymentPayload(
                x402_version=payment_payload_dict.get("x402_version", 1),
                scheme=payment_payload_dict.get("scheme", "exact"),
                network=payment_payload_dict.get("network"),
                payload=ExactPaymentPayload(
                    authorization=EIP3009Authorization(
                        from_=auth_dict.get("from"),
                        to=auth_dict.get("to"),
                        value=str(auth_dict.get("value")),
                        valid_after=str(auth_dict.get("validAfter")),
                        valid_before=str(auth_dict.get("validBefore")),
                        nonce=auth_dict.get("nonce"),
                    ),
                    signature=payment_payload_dict["payload"]["signature"],
                ),
            )

            # 3. Verify and Settle the payment with the facilitator
            verify_response = await self._facilitator.verify(
                payment_payload, self._current_payment_requirements
            )
            if not verify_response.is_valid:
                error_msg = (
                    f"Payment verification failed: {verify_response.invalid_reason}"
                )
                logger.error(error_msg)
                return {"error": error_msg}

            settle_response = await self._facilitator.settle(
                payment_payload, self._current_payment_requirements
            )

            if settle_response.success:
                logger.info("Payment settled successfully!")
                mandate_id = payment_mandate.get(
                    "payment_mandate_contents", {}
                ).get("id")
                payment_id = f"payment_{uuid.uuid4()}"
                price_in_usd = (
                    f"{int(auth_dict.get("value")) / 1000000:.2f}"
                )
                payment_receipt = PaymentReceipt(
                    payment_mandate_id=mandate_id,
                    payment_id=payment_id,
                    amount=PaymentCurrencyAmount(
                        currency="USDC", value=price_in_usd
                    ),
                    payment_status=Success(
                        merchant_confirmation_id=f"merch_{uuid.uuid4()}"
                    ),
                )

                payment_receipt_data = {
                    PAYMENT_RECEIPT_DATA_KEY: payment_receipt.model_dump(
                        by_alias=True
                    )
                }

                return {
                    "artifact": {
                        "artifactId": f"payment-receipt-{uuid.uuid4()}",
                        "name": "AP2 PaymentReceipt",
                        "parts": [
                            {
                                "kind": "data",
                                "data": payment_receipt_data,
                            }
                        ],
                        "extensions": [
                            "https://github.com/google-agentic-commerce/ap2/tree/v0.1",
                            "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2",
                        ],
                    },
                }
            else:
                error_msg = f"Payment settlement failed: {settle_response.error_reason}"
                logger.error(error_msg)
                return {"error": error_msg}

        except Exception as e:
            logger.error(
                f"An error occurred during payment processing: {e}",
                exc_info=True,
            )
            return {"error": f"An unexpected error occurred: {e}"}

    def before_agent_callback(self, callback_context: CallbackContext):
        """
        This callback is executed before the agent is invoked.
        It loads the payment requirements from the session state if they exist.
        """
        if callback_context.state:
            requirements_dict = callback_context.state.get("payment_requirements")
            if requirements_dict:
                self._current_payment_requirements = PaymentRequirements(
                    **requirements_dict
                )
                logger.info("Loaded payment requirements from session state.")
            else:
                self._current_payment_requirements = None

    @override
    def create_agent(self) -> LlmAgent:
        """Creates the LlmAgent instance for the merchant."""
        return LlmAgent(
            model="gemini-2.5-flash",
            name="adk_merchant_agent",
            description="An agent that can sell any item by providing a price and then processing the payment using the x402 protocol.",
            instruction="""You are a merchant agent that follows a strict two-step process.
- STEP 1: CREATE CART. You will first receive an `IntentMandate` in a JSON format. You MUST extract the `natural_language_description` from this mandate and use it as the `product_name` argument for the `get_product_details_and_create_cart` tool. Do not use any other tool in this step.
- STEP 2: PROCESS PAYMENT. After the first step, you will receive a `PaymentMandate`. When you receive this, you MUST use the `process_payment` tool to handle it.
- After payment is successful, you MUST confirm the purchase with the user and tell them their order is being prepared.
""",
            tools=[self.get_product_details_and_create_cart, self.process_payment],
            before_agent_callback=self.before_agent_callback,
        )

    @override
    async def create_agent_card(self, url: str) -> AgentCard:
        """Creates the AgentCard for this agent."""
        from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

        capabilities = AgentCapabilities(
            streaming=False,
            extensions=[
                get_extension_declaration(
                    description="Supports payments using the x402 protocol.",
                    required=True,
                )
            ],
        )
        builder = AgentCardBuilder(
            agent=self.create_agent(),
            rpc_url=url,
            capabilities=capabilities,
            agent_version="5.0.0",
        )
        card = await builder.build()

        # Override generated values with more specific ones
        card.name = "x402 Merchant Agent"
        card.description = (
            "This agent sells items by creating a signed AP2 Cart Mandate."
        )
        card.skills = [
            AgentSkill(
                id="get_product_info",
                name="Get Product Details and Create Cart",
                description="Provides product details and creates a cart mandate for"
                " any given product.",
                tags=["cart", "product", "x402", "merchant"],
                examples=[
                    "How much for a new laptop?",
                    "I want to buy a red stapler.",
                    "Can you give me the price for a copy of 'Moby Dick'?",
                ],
            )
        ]
        card.default_input_modes = ["text", "text/plain"]
        card.default_output_modes = ["text", "text/plain"]

        return card
