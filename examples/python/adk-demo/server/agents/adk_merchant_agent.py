import hashlib
from typing import override

from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from x402.types import PaymentRequirements

# Import the custom exception and the base agent interface
from .base_agent import BaseAgent
from a2a_x402.types import X402PaymentRequiredException
from a2a_x402 import (
    X402ExtensionConfig,
    PaymentStatus,
    X402Utils,
    get_extension_declaration
)

# This is the new, clean ADK Merchant Agent.
# It now implements the BaseAgent interface.

class AdkMerchantAgent(BaseAgent):
    """
    Defines the ADK LlmAgent for the merchant and its corresponding AgentCard.
    The business logic is implemented as tools.
    """

    def __init__(self, wallet_address: str = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"):
        self._wallet_address = wallet_address
        self.x402 = X402Utils()

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
        an exception to signal to the X402 wrapper that payment is needed.
        """
        if not product_name:
            return {"error": "Product name cannot be empty."}

        price = self._get_product_price(product_name)
        requirements = PaymentRequirements(
            scheme="exact",
            network="base-sepolia",
            asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            pay_to=self._wallet_address,
            max_amount_required=price,
            description=f"Payment for: {product_name}",
            resource=f"https://example.com/product/{product_name}",
            mime_type="application/json",
            max_timeout_seconds=1200,
            extra={"sku": f"{product_name}_sku", "name":  product_name, "version": '1'},

        )

        # Signal to the X402ServerAgentExecutor that payment is required.
        # The wrapper will catch this and handle the A2A flow.
        raise X402PaymentRequiredException(product_name, requirements)

    def before_agent_callback(self, callback_context: CallbackContext):
        """
        Injects a 'virtual' tool response if payment has been verified.
        """
        payment_data = callback_context.state.get('payment_verified_data')
        if payment_data:
            # Consume the data so it's not used again in the same session.
            del callback_context.state['payment_verified_data']
            
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
- If you receive a successful result from the `check_payment_status` tool, you MUST confirm the purchase with the user and tell them their order is being prepared. Do not ask for payment again.
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