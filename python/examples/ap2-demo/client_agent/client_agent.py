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
import json
import logging
import uuid
from typing import Any, Optional

import httpx
from a2a.types import (
    DataPart,
)
from google.adk import Agent
from google.adk.agents import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import AgentTool
from google.adk.tools.tool_context import ToolContext
from ap2.types.mandate import IntentMandate, PaymentMandate, PaymentMandateContents
from ap2.types.payment_request import PaymentResponse
from web3 import Web3
import os
import datetime
from dotenv import load_dotenv

from x402_a2a.core.utils import x402Utils
from x402_a2a.core.wallet import get_transfer_with_auth_typed_data

logger = logging.getLogger(__name__)

load_dotenv()

# ABI for the functions we need from the USDC contract (name, version, nonces)
USDC_ABI = json.loads(
    """
[
    {
      "inputs": [],
      "name": "name",
      "outputs": [
        {
          "name": "",
          "type": "string"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "version",
      "outputs": [
        {
          "name": "",
          "type": "string"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "name": "owner",
          "type": "address"
        }
      ],
      "name": "nonces",
      "outputs": [
        {
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    }
]
"""
)


class ClientAgent:
    """
    The orchestrator agent. It discovers other agents and delegates tasks
    to them, managing the conversation flow based on task states.
    """

    def __init__(
        self,
        remote_agents: list[BaseAgent],
        http_client: httpx.AsyncClient,
    ):
        """Initializes the ClientAgent."""
        self.httpx_client = http_client
        self.remote_agents = remote_agents
        agent_list = [
            {"name": agent.name, "description": agent.description}
            for agent in self.remote_agents
        ]
        self.agents_info_str = json.dumps(agent_list, indent=2)
        self.x402 = x402Utils()
        self._wallet_address: Optional[str] = None

    def create_agent(self) -> Agent:
        """Creates the ADK Agent instance."""
        all_tools: list[Any] = [
            self.create_intent_mandate,
            self.sign_intent_mandate,
            self.save_cart_and_inform_user,
            self.pay_for_cart,
            self.sign_payment_request,
            self.create_payment_mandate,
            self.sign_payment_mandate,
        ]
        # Wrap each remote agent in an AgentTool to make it a callable tool
        all_tools.extend([AgentTool(agent=agent) for agent in self.remote_agents])

        return Agent(
            model="gemini-2.5-flash",
            name="client_agent",
            instruction=self.root_instruction,
            before_agent_callback=self.before_agent_callback,
            description="An orchestrator that delegates tasks to other agents.",
            tools=all_tools,
        )

    def save_cart_and_inform_user(
        self, cart_mandate_str: str, tool_context: ToolContext
    ):
        """
        Parses a cart mandate JSON string, saves it to the session state,
        and informs the user about the available payment methods.
        """

        try:
            cart_mandate = json.loads(cart_mandate_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode cart_mandate_str: {cart_mandate_str}")
            return "I received a cart from the merchant, but it was in a format I could not understand."

        # The RemoteA2aAgent returns a DataPart, which serializes to `{'data': ...}`.
        # We need to unwrap the actual mandate from inside the 'data' key.
        unwrapped_mandate = cart_mandate.get("data", cart_mandate)
        cart_data = unwrapped_mandate.get(
            "ap2.mandates.CartMandate", unwrapped_mandate
        )
        tool_context.state["cart_mandate"] = cart_data

        # Extract payment methods and total price to present to the user
        payment_methods = []
        total_amount = None
        total_currency = None
        try:
            method_data = (
                cart_data.get("contents", {})
                .get("payment_request", {})
                .get("method_data", [])
            )
            for method in method_data:
                if "supported_methods" in method:
                    payment_methods.append(method["supported_methods"])

            total_details = (
                cart_data.get("contents", {})
                .get("payment_request", {})
                .get("details", {})
                .get("total", {})
                .get("amount", {})
            )
            total_amount = total_details.get("value")
            total_currency = total_details.get("currency")

        except Exception as e:
            logger.error(f"Error parsing payment details from cart mandate: {e}")
            return "The merchant sent a cart, but I couldn't understand the payment options or total price."

        if not payment_methods:
            return "The merchant has created a cart for you, but no payment methods were specified."

        methods_str = "\n - ".join(payment_methods)
        price_str = (
            f" for a total of {total_amount} {total_currency}"
            if total_amount and total_currency
            else ""
        )
        user_message = (
            "The merchant has created a cart for you. Here are the available payment methods:"
            f"\n - {methods_str}{price_str}\n\n"
            "You can now tell me to 'pay for the cart'."
        )

        return user_message


    async def before_agent_callback(self, callback_context: CallbackContext):
        """Initializes connections to remote agents before the first turn."""
        if self._wallet_address:  # Check if already initialized
            return

        # Fetch the wallet address first
        try:
            response = await self.httpx_client.get(
                f"{os.getenv('LOCAL_WALLET_URL', 'http://localhost:5001')}/address"
            )
            response.raise_for_status()
            self._wallet_address = response.json().get("address")
        except httpx.RequestError as e:
            logger.error(f"Could not connect to mock wallet to get address: {e}")
            # Handle the error appropriately, maybe by preventing initialization
            return

    async def sign_payment_request(self, tool_context: ToolContext):
        """Signs the payment request stored in the state using the mock wallet."""
        logger.info("Attempting to sign payment request.")
        request_to_sign = tool_context.state.get("payment_request_to_sign")
        if not request_to_sign:
            logger.warning("No payment request found in state to sign.")
            return {
                "user_message": "I could not find a payment request to sign. Please create one first."
            }

        try:
            # The wallet's /sign endpoint expects the raw EIP-712 typed data object
            response = await self.httpx_client.post(
                f"{os.getenv('LOCAL_WALLET_URL', 'http://localhost:5001')}/sign",
                json=request_to_sign,
            )
            logger.info(f"Received response from wallet: {response.status_code}")
            response.raise_for_status()

            signature_data = response.json()

            purchase_details = tool_context.state.get("purchase_details")
            if not purchase_details:
                raise ValueError("State inconsistency: 'purchase_details' not found.")

            final_payload = {
                "x402_version": purchase_details.get("x402_version", 1),
                "scheme": purchase_details.get("scheme"),
                "network": purchase_details.get("network"),
                "payload": {
                    "signature": signature_data["signature"],
                    "authorization": request_to_sign["message"],
                },
            }

            tool_context.state["signed_payment_payload"] = final_payload
            tool_context.state["payment_request_to_sign"] = None
            logger.info("Successfully signed and stored the payment payload.")

            return self.create_payment_mandate(tool_context)
        except httpx.RequestError as e:
            logger.error(
                f"HTTP error while signing payment request: {e}", exc_info=True
            )
            return {
                "user_message": "Sorry, I was unable to connect to the signing wallet. Please try again later."
            }
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during signing: {e}", exc_info=True
            )
            return {
                "user_message": "An unexpected error occurred while signing the payment request."
            }

    def create_payment_mandate(self, tool_context: ToolContext):
        """Creates a payment mandate from the signed payment payload."""
        logger.info("Attempting to create a payment mandate.")
        signed_payload = tool_context.state.get("signed_payment_payload")
        if not signed_payload:
            raise ValueError("State inconsistency: 'signed_payment_payload' not found.")

        purchase_details = tool_context.state.get("purchase_details")
        if not purchase_details:
            raise ValueError(
                "State inconsistency: 'purchase_details' not found to create payment mandate."
            )

        payment_response = PaymentResponse(
            request_id=purchase_details["request_id"],
            method_name="https://www.x402.org/",
            details=signed_payload,
        )

        payment_mandate_contents = PaymentMandateContents(
            payment_mandate_id=str(uuid.uuid4()),
            payment_details_id=purchase_details["payment_details_id"],
            payment_details_total=purchase_details["payment_details_total"],
            payment_response=payment_response,
            merchant_agent=purchase_details["merchant_agent"],
        )

        payment_mandate = PaymentMandate(
            payment_mandate_contents=payment_mandate_contents
        )

        tool_context.state["payment_mandate_to_sign"] = payment_mandate.model_dump(
            by_alias=True
        )
        tool_context.state["purchase_details"] = None  # clean up

        return {
            "user_message": "I have created the Payment Mandate. Please approve by sending the message 'sign payment mandate'."
        }

    def pay_for_cart(self, tool_context: ToolContext):
        """Initiates payment for the cart stored in the state."""
        logger.info("Attempting to pay for the cart.")
        cart_mandate = tool_context.state.get("cart_mandate")
        if not cart_mandate:
            logger.warning("No cart mandate found in state to pay for.")
            return {
                "user_message": "I could not find a cart to pay for. Please get a cart from a merchant first."
            }
        if not self._wallet_address:
            return {
                "user_message": "I have not been configured with a wallet address to pay from. Please check the application setup."
            }

        try:
            # Extract payment requirements from the cart mandate
            method_data = (
                cart_mandate.get("contents", {})
                .get("payment_request", {})
                .get("method_data", [])
            )
            x402_data = None
            for method in method_data:
                if method.get("supported_methods") == "https://www.x402.org/":
                    x402_data = method.get("data", {}).get("x402.payment.required")
                    break

            if not x402_data:
                raise ValueError(
                    "No x402 payment requirements found in the cart mandate."
                )

            requirements = x402_data

            if not requirements.get("accepts") or not requirements["accepts"]:
                raise ValueError("No payment options found in the x402 requirements.")

            selected_requirement = requirements["accepts"][0]

            # --- Get EIP-712 domain info and nonce from the contract ---
            network_rpc_url = os.getenv(
                "RPC_URL",
                "https://sepolia.base.org",
            )
            w3 = Web3(Web3.HTTPProvider(network_rpc_url))
            usdc_contract = w3.eth.contract(
                address=selected_requirement["asset"], abi=USDC_ABI
            )
            token_name = usdc_contract.functions.name().call()
            token_version = usdc_contract.functions.version().call()

            # Ensure numeric and chain ID values are integers for signing
            chain_id = int(w3.eth.chain_id)
            value = int(selected_requirement["maxAmountRequired"])
            valid_after = int(
                (datetime.datetime.now(datetime.timezone.utc)).timestamp()
            )
            valid_before = int(
                (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(hours=1)
                ).timestamp()
            )

            typed_data = get_transfer_with_auth_typed_data(
                from_=self._wallet_address,
                to=selected_requirement["payTo"],
                value=value,
                valid_after=valid_after,
                valid_before=valid_before,
                nonce="0x" + os.urandom(32).hex(),  # type: ignore[arg-type]
                chain_id=chain_id,
                contract_address=selected_requirement["asset"],
                token_name=token_name,
                token_version=token_version,
            )

            # Storing the purchase details for creating the payment mandate later
            tool_context.state["purchase_details"] = {
                "payment_details_id": cart_mandate.get("contents", {})
                .get("payment_request", {})
                .get("details", {})
                .get("id"),
                "payment_details_total": cart_mandate.get("contents", {})
                .get("payment_request", {})
                .get("details", {})
                .get("total"),
                "merchant_agent": cart_mandate.get("contents", {}).get("merchant_name"),
                "request_id": cart_mandate.get("contents", {})
                .get("payment_request", {})
                .get("details", {})
                .get("id"),
                "x402_version": x402_data.get("x402Version"),
                "scheme": selected_requirement.get("scheme"),
                "network": selected_requirement.get("network"),
            }
            tool_context.state["payment_request_to_sign"] = typed_data

            return {
                "user_message": "I have created the x402 payment request (this is the payment payload). Please approve by sending the message 'sign payment request'."
            }
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during payment preparation: {e}",
                exc_info=True,
            )
            return {
                "user_message": "An unexpected error occurred while preparing the payment."
            }

    async def sign_payment_mandate(self, tool_context: ToolContext):
        """Signs the payment mandate stored in the state using the mock wallet."""
        logger.info("Attempting to sign payment mandate.")
        mandate_to_sign = tool_context.state.get("payment_mandate_to_sign")
        if not mandate_to_sign:
            logger.warning("No payment mandate found in state to sign.")
            return {
                "user_message": "I could not find a payment mandate to sign. Please create one first."
            }

        try:
            # The wallet expects a JSON string payload
            payload_to_sign = json.dumps(mandate_to_sign)

            response = await self.httpx_client.post(
                f"{os.getenv('LOCAL_WALLET_URL', 'http://localhost:5001')}/sign",
                json={"payload": payload_to_sign},
            )
            logger.info(f"Received response from wallet: {response.status_code}")
            response.raise_for_status()

            signature_data = response.json()

            signed_mandate_payload = mandate_to_sign.copy()
            # The signature for a payment mandate is the user_authorization field
            signed_mandate_payload["user_authorization"] = signature_data["signature"]

            tool_context.state["signed_payment_mandate"] = {
                "signed_payment_mandate": signed_mandate_payload
            }

            tool_context.state["payment_mandate_to_sign"] = None
            logger.info("Successfully signed and stored the payment mandate.")

            return {
                "user_message": "I have signed the payment mandate. Please forward it to the merchant agent.",
                "signed_payment_mandate": signed_mandate_payload,
            }
        except httpx.RequestError as e:
            logger.error(
                f"HTTP error while signing payment mandate: {e}", exc_info=True
            )
            return {
                "user_message": "Sorry, I was unable to connect to the signing wallet. Please try again later."
            }
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during signing: {e}", exc_info=True
            )
            return {
                "user_message": "An unexpected error occurred while signing the payment mandate."
            }

    def create_intent_mandate(
        self,
        natural_language_description: str,
        tool_context: ToolContext,
        merchants: Optional[list[str]] = None,
        skus: Optional[list[str]] = None,
        requires_refundability: bool = False,
    ):
        """Creates a user intent mandate to start a purchase flow."""
        mandate = IntentMandate(
            natural_language_description=natural_language_description,
            merchants=merchants,
            skus=skus,
            requires_refundability=requires_refundability,
            intent_expiry=(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(hours=1)
            ).isoformat(),
        )
        tool_context.state["intent_mandate_to_sign"] = mandate.model_dump(by_alias=True)
        return {
            "user_message": f"I have created the Intent Mandate: '{mandate.natural_language_description}'. Please approve by sending the message 'sign intent mandate'."
        }

    async def sign_intent_mandate(self, tool_context: ToolContext):
        """Signs the intent mandate stored in the state using the mock wallet."""
        logger.info("Attempting to sign intent mandate.")
        mandate_to_sign = tool_context.state.get("intent_mandate_to_sign")
        if not mandate_to_sign:
            logger.warning("No intent mandate found in state to sign.")
            return {
                "user_message": "I could not find an intent mandate to sign. Please create one first by telling me what you want to buy."
            }

        try:
            payload_to_sign = json.dumps(mandate_to_sign)

            response = await self.httpx_client.post(
                f"{os.getenv('LOCAL_WALLET_URL', 'http://localhost:5001')}/sign",
                json={"payload": payload_to_sign},
            )
            logger.info(f"Received response from wallet: {response.status_code}")
            response.raise_for_status()

            signature_data = response.json()

            signed_mandate_payload = mandate_to_sign.copy()
            signed_mandate_payload["signature"] = {
                "signature": signature_data["signature"],
                "signer_address": signature_data["address"],
            }

            tool_context.state["signed_intent_mandate"] = {
                "signed_intent_mandate": signed_mandate_payload
            }

            tool_context.state["intent_mandate_to_sign"] = None
            logger.info("Successfully signed and stored the intent mandate.")

            return {
                "user_message": "I have signed the intent mandate. Please forward it to the merchant agent.",
                "signed_intent_mandate": signed_mandate_payload,
            }
        except httpx.RequestError as e:
            logger.error(f"HTTP error while signing intent mandate: {e}", exc_info=True)
            return {
                "user_message": "Sorry, I was unable to connect to the signing wallet. Please try again later."
            }
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during signing: {e}", exc_info=True
            )
            return {
                "user_message": "An unexpected error occurred while signing the intent mandate."
            }

    # --- Agent Setup and Instructions ---

    def root_instruction(self, context: ReadonlyContext) -> str:
        """Provides the master instruction set for the orchestrator LLM."""
        return f"""
You are a master orchestrator agent. Your job is to complete user requests by delegating tasks to a network of specialized agents that are available to you as tools.

**Standard Operating Procedure (SOP):**

1.  **Analyze, Clarify, and Create Intent**: When a user wants to purchase something, your primary goal is to create the clearest, most unambiguous intent possible for the merchant.
    *   **Analyze the Request**: Think critically about the user's request. What details might be missing? For example, if they ask for "a shirt," you must ask about size, color, and style. If they ask for "coffee," you must ask about size, type, and temperature.
    *   **Ask Clarifying Questions**: If the user's request is vague or missing details, you MUST ask follow-up questions to gather the necessary information. Do not create an intent until you are confident you have a specific, actionable request.
    *   **Confirm the Intent**: After gathering details, confirm the complete order with the user. For example, say "Just to confirm, you'd like one large, black, iced coffee. Is that correct?"
    *   **Enrich the Description**: Once confirmed, create a rich `natural_language_description` for the mandate. Instead of just "a red shirt," a better description would be "one men's medium-sized, short-sleeve, crewneck t-shirt in bright red."
    *   **Create the Mandate**: Once the user has confirmed the detailed intent, use the `create_intent_mandate` tool. This will create the mandate and present it to the user for final approval to sign.
2.  **Sign Intent**: When the user approves, call the `sign_intent_mandate` tool to sign it.
3.  **Delegate to Merchant**: After signing the intent, the `sign_intent_mandate` tool will return a `signed_intent_mandate` object. You MUST take this entire object, convert it into a JSON string, and then call the `merchant_agent` tool with the JSON string as the `message` argument.
4.  **Save Cart and Inform User**: When the `merchant_agent` tool returns a `CartMandate` object, you MUST convert the entire object into a JSON string. Then you MUST call the `save_cart_and_inform_user` tool with this JSON string as the `cart_mandate_str` argument. After calling this tool, you MUST present the message it returns directly to the user.
5.  **Payment Handling**: When the user says "pay for the cart", you MUST use the `pay_for_cart` tool.
6.  **Sign Payment Request**: When the user is asked to sign the payment request, they will send the message 'sign payment request'. You MUST then call the `sign_payment_request` tool. This will create the payment mandate.
7.  **Sign Payment Mandate**: When the user is asked to sign the payment mandate, they will send the message 'sign payment mandate'. You MUST then call the `sign_payment_mandate` tool.
8.  **Forward Signed Payment Mandate**: After signing the payment mandate, the `sign_payment_mandate` tool will return a `signed_payment_mandate` object. You MUST take this entire object, convert it into a JSON string, and then call the `merchant_agent` tool with the JSON string as the `message` argument.
9.  **Report Outcome**: Clearly report the final success or failure message to the user.

**System Context**:

* **Available Agents (as Tools)**:
    {self.agents_info_str}
"""
