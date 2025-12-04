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
import os
from typing import override

from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from x402_a2a.types import (
    PaymentRequirements,
    PaymentRequiredResponseV2,
    ResourceInfo,
)
from payments_py.x402.extensions.nevermined import (
    declare_nevermined_extension,
    nevermined_extension_key,
)

# Import the custom exception and the base agent interface
from .base_agent import BaseAgent
from x402_a2a.types import x402PaymentRequiredException
from payments_py.x402 import X402A2AUtils
from x402_a2a import get_extension_declaration

# This is the new, clean ADK Merchant Agent.
# It now implements the BaseAgent interface.


class AdkMerchantAgent(BaseAgent):
    """
    Defines the ADK LlmAgent for the merchant and its corresponding AgentCard.
    The business logic is implemented as tools.
    """

    def __init__(
        self, wallet_address: str = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"
    ):
        self._wallet_address = wallet_address
        self.nvm = X402A2AUtils()

    def _get_product_price(self, product_name: str) -> str:
        """Generates a deterministic price for a product."""
        price = (
            int(hashlib.sha256(product_name.lower().encode()).hexdigest(), 16)
            % 99900001
            + 100000
        )
        return str(price)

    def get_product_details_and_request_payment(self, product_name: str) -> dict:
        """
        This is the agent's tool. Instead of returning payment details, it raises
        an exception to signal to the x402 wrapper that payment is needed.

        Now uses x402 v2 extension format with declare_nevermined_extension().
        Supports multiple payment plans - users can choose which plan they want to use.
        """
        if not product_name:
            return {"error": "Product name cannot be empty."}

        # Get agent ID from environment (required)
        agent_id = os.getenv("NVM_AGENT_ID")
        if not agent_id:
            raise ValueError(
                "NVM_AGENT_ID environment variable is required. "
                "Set this to your Nevermined agent ID."
            )

        # Get plan IDs from environment variables
        credits_plan_id = os.getenv("NVM_CREDITS_PLAN_ID")
        payasyougo_plan_id = os.getenv("NVM_PAYASYOUGO_PLAN_ID")

        if not credits_plan_id:
            raise ValueError(
                "NVM_CREDITS_PLAN_ID environment variable is required. "
                "Set this to your Nevermined credits plan ID."
            )

        # Get common configuration from environment
        max_amount = os.getenv("NVM_PAYMENT_AMOUNT", "2")
        network = os.getenv("NVM_NETWORK", "base-sepolia")
        environment = os.getenv("NVM_ENVIRONMENT", "sandbox")

        # Build extensions dictionary - one extension per plan (x402 v2 preferred)
        # Each plan gets its own extension entry with a qualified key
        extensions_dict = {}
        v1_requirements_list = []

        # Create Credits Plan extension
        credits_extension = declare_nevermined_extension(
            plan_id=credits_plan_id,
            agent_id=agent_id,
            max_amount=max_amount,
            network=network,
            scheme="contract",
            environment=environment,
        )
        extensions_dict[nevermined_extension_key("credits")] = credits_extension

        credits_requirements = PaymentRequirements(
            plan_id=credits_plan_id,
            agent_id=agent_id,
            max_amount=max_amount,
            network=network,
            scheme="contract",
            extra={"plan_name": "Credits Plan"},
        )
        v1_requirements_list.append(credits_requirements)

        print(f"\n🔵 [SERVER] Creating v2 payment requirements with extensions:")
        print(f"   Agent ID: {agent_id}")
        print(f"   Network: {network}")
        print(f"   Environment: {environment}")
        print(f"   - Credits Plan:")
        print(f"     Extension key: {nevermined_extension_key('credits')}")
        print(f"     Plan ID: {credits_plan_id}")
        print(f"     Amount: {max_amount} credits")

        # Create Pay-as-you-go Plan extension (if configured)
        if payasyougo_plan_id:
            payasyougo_extension = declare_nevermined_extension(
                plan_id=payasyougo_plan_id,
                agent_id=agent_id,
                max_amount=max_amount,
                network=network,
                scheme="contract",
                environment=environment,
            )
            extensions_dict[nevermined_extension_key("payasyougo")] = (
                payasyougo_extension
            )

            payasyougo_requirements = PaymentRequirements(
                plan_id=payasyougo_plan_id,
                agent_id=agent_id,
                max_amount=max_amount,
                network=network,
                scheme="contract",
                extra={"plan_name": "Pay-as-you-go Plan"},
            )
            v1_requirements_list.append(payasyougo_requirements)

            print(f"   - Pay-as-you-go Plan:")
            print(f"     Extension key: {nevermined_extension_key('payasyougo')}")
            print(f"     Plan ID: {payasyougo_plan_id}")
            print(f"     Amount: {max_amount} credits")

        # Create v2 payment required response
        # For v2, each plan is its own extension entry (x402 v2 preferred approach)
        # accepts array is kept minimal for backwards compatibility with v1 clients
        payment_required_v2 = PaymentRequiredResponseV2(
            x402_version=2,
            resource=ResourceInfo(
                url=f"/product/{product_name}", description=f"Purchase {product_name}"
            ),
            accepts=v1_requirements_list,  # Minimal for v1 backwards compatibility
            extensions=extensions_dict,  # v2: Each plan is its own extension entry
        )

        # Signal to the x402ServerAgentExecutor that payment is required.
        # The wrapper will catch this and handle the A2A flow.
        raise x402PaymentRequiredException(
            product_name, payment_required_v2=payment_required_v2
        )

    def before_agent_callback(self, callback_context: CallbackContext):
        """
        Injects a 'virtual' tool response if payment has been verified.
        """
        payment_data = callback_context.state.get("payment_verified_data")
        if payment_data:
            # Consume the data so it's not used again in the same session.
            del callback_context.state["payment_verified_data"]

            # Create a Content object that looks like a tool call response.
            # This is a structured way to inform the LLM of the payment status.
            tool_response = types.Part(
                function_response=types.FunctionResponse(
                    name="check_payment_status",
                    response=payment_data,
                )
            )
            # Set this as the new, overriding input for this turn.
            callback_context.new_user_message = types.Content(parts=[tool_response])

    @override
    def create_agent(self) -> LlmAgent:
        """Creates the LlmAgent instance for the merchant."""
        return LlmAgent(
            model="gemini-2.5-flash",
            name="adk_merchant_agent",
            description="An agent that can sell any item by providing a price and then processing the payment using the x402 protocol.",
            instruction="""You are a helpful and friendly "Amazon" merchant agent.
- When a user asks to buy an item, use the `get_product_details_and_request_payment` tool.
- After payment is verified, the system will automatically provide you with payment confirmation. When you receive payment confirmation, you MUST confirm the purchase with the user and tell them their order is being prepared. Do not ask for payment again.
- If the system tells you the payment failed, relay the error clearly and politely.
""",
            tools=[self.get_product_details_and_request_payment],
            before_agent_callback=self.before_agent_callback,
        )

    @override
    def create_agent_card(self, url: str) -> AgentCard:
        """Creates the AgentCard for this agent."""
        skills = [
            AgentSkill(
                id="get_product_info",
                name="Get Product Price and Payment Info",
                description="Provides the price, SKU, and x402 payment requirements for any given product.",
                tags=["pricing", "product", "x402", "merchant"],
                examples=[
                    "How much for a new laptop?",
                    "I want to buy a red stapler.",
                    "Can you give me the price for a copy of 'Moby Dick'?",
                ],
            )
        ]
        return AgentCard(
            name="x402 Merchant Agent",
            description="This agent sells items using the clean x402 server architecture.",
            url=url,
            version="4.0.0",
            defaultInputModes=["text", "text/plain"],
            defaultOutputModes=["text", "text/plain"],
            capabilities=AgentCapabilities(
                streaming=False,
                extensions=[
                    get_extension_declaration(
                        description="Supports payments using the x402 protocol.",
                        required=True,
                    )
                ],
            ),
            skills=skills,
        )
