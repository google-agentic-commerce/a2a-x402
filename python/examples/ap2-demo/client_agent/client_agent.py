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
from typing import Optional

import httpx
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    JSONRPCError,
    Message,
    MessageSendParams,
    Part,
    Task,
    TaskState,
    TextPart,
    DataPart,
)
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from ap2.types.mandate import IntentMandate, PaymentMandate, PaymentMandateContents
from ap2.types.payment_request import PaymentResponse
from web3 import Web3
import os
import datetime

# Local imports
from ._remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
from x402_a2a.core.utils import x402Utils
from x402_a2a.types import PaymentStatus
from x402_a2a.core.wallet import get_transfer_with_auth_typed_data

logger = logging.getLogger(__name__)

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
        remote_agent_addresses: list[str],
        http_client: httpx.AsyncClient,
        task_callback: TaskUpdateCallback | None = None,
    ):
        """Initializes the ClientAgent."""
        self.task_callback = task_callback
        self.httpx_client = http_client
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.remote_agent_addresses = remote_agent_addresses
        self.agents_info_str = ""
        self._initialized = False
        self.x402 = x402Utils()
        self._wallet_address: Optional[str] = None

    def create_agent(self) -> Agent:
        """Creates the ADK Agent instance."""
        return Agent(
            model="gemini-2.5-flash",
            name="client_agent",
            instruction=self.root_instruction,
            before_agent_callback=self.before_agent_callback,
            description="An orchestrator that delegates tasks to other agents.",
            tools=[
                self.list_remote_agents,
                self.send_message,
                self.create_intent_mandate,
                self.sign_intent_mandate,
                self.pay_for_cart,
                self.sign_payment_request,
                self.create_payment_mandate,
                self.sign_payment_mandate,
            ],
        )

    def sign_payment_request(self, tool_context: ToolContext):
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
            response = httpx.post("http://localhost:5001/sign", json=request_to_sign)
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
            netowrk_rpc_url = os.getenv(
                "RPC_URL",
                "https://sepolia.base.org",
            )
            w3 = Web3(Web3.HTTPProvider(netowrk_rpc_url))
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
                nonce="0x" + os.urandom(32).hex(),  # Pass nonce as a hex string
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

    def sign_payment_mandate(self, tool_context: ToolContext):
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

            response = httpx.post(
                "http://localhost:5001/sign", json={"payload": payload_to_sign}
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
                "user_message": "I have signed the payment mandate. You can now ask me to forward it to the merchant agent."
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

    def sign_intent_mandate(self, tool_context: ToolContext):
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

            response = httpx.post(
                "http://localhost:5001/sign", json={"payload": payload_to_sign}
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
                "user_message": "I have signed the intent mandate. You can now ask me to forward it to a merchant agent."
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
You are a master orchestrator agent. Your job is to complete user requests by delegating tasks to a network of specialized agents.

**Standard Operating Procedure (SOP):**

1.  **Discover**: Always start by using `list_remote_agents` to see which agents are available.
2.  **Analyze, Clarify, and Create Intent**: When a user wants to purchase something, your primary goal is to create the clearest, most unambiguous intent possible for the merchant.
    *   **Analyze the Request**: Think critically about the user's request. What details might be missing? For example, if they ask for "a shirt," you must ask about size, color, and style. If they ask for "coffee," you must ask about size, type, and temperature.
    *   **Ask Clarifying Questions**: If the user's request is vague or missing details, you MUST ask follow-up questions to gather the necessary information. Do not create an intent until you are confident you have a specific, actionable request.
    *   **Confirm the Intent**: After gathering details, confirm the complete order with the user. For example, say "Just to confirm, you'd like one large, black, iced coffee. Is that correct?"
    *   **Enrich the Description**: Once confirmed, create a rich `natural_language_description` for the mandate. Instead of just "a red shirt," a better description would be "one men's medium-sized, short-sleeve, crewneck t-shirt in bright red."
    *   **Create the Mandate**: Once the user has confirmed the detailed intent, use the `create_intent_mandate` tool. This will create the mandate and present it to the user for final approval to sign.
3.  **Sign Intent**: When the user approves, call the `sign_intent_mandate` tool to sign it.
4.  **Forward Signed Intent**: After the user has signed an intent mandate, send it to the most appropriate agent using `send_message` with the message `forward_signed_intent`.
5.  **Delegate**: Send other user requests to the most appropriate agent using `send_message`.
6.  **Payment Handling**:
    *   If an agent returns a cart with payment options, clearly list the payment methods to the user and inform them that they can proceed by saying "pay for the cart".
    *   When the user says "pay for the cart", you MUST use the `pay_for_cart` tool.
7.  **Sign Payment Request**: When the user is asked to sign the payment request, they will send the message 'sign payment request'. You MUST then call the `sign_payment_request` tool. This will create the payment mandate.
8.  **Sign Payment Mandate**: When the user is asked to sign the payment mandate, they will send the message 'sign payment mandate'. You MUST then call the `sign_payment_mandate` tool.
9.  **Forward Signed Payment Mandate**: After the payment mandate is signed, you MUST call `send_message` again, targeting the *same agent*, with the exact message: "forward_signed_payment_mandate".
10. **Report Outcome**: Clearly report the final success or failure message to the user.

**System Context**:

* **Available Agents**:
    {self.agents_info_str}
"""

    async def before_agent_callback(self, callback_context: CallbackContext):
        """Initializes connections to remote agents before the first turn."""
        if self._initialized:
            return

        # Fetch the wallet address first
        try:
            response = await self.httpx_client.get("http://localhost:5001/address")
            response.raise_for_status()
            self._wallet_address = response.json().get("address")
            logger.info(f"Successfully fetched wallet address: {self._wallet_address}")
        except httpx.RequestError as e:
            logger.error(f"Could not connect to mock wallet to get address: {e}")
            # Handle the error appropriately, maybe by preventing initialization
            return

        for address in self.remote_agent_addresses:
            card = await A2ACardResolver(self.httpx_client, address).get_agent_card()
            self.remote_agent_connections[card.name] = RemoteAgentConnections(
                self.httpx_client, card
            )
            self.cards[card.name] = card

        # Create a formatted string of agent info for the prompt
        agent_list = [
            {"name": c.name, "description": c.description} for c in self.cards.values()
        ]
        self.agents_info_str = json.dumps(agent_list, indent=2)
        self._initialized = True

    # --- Agent Tools ---
    def list_remote_agents(self):
        """Lists the available remote agents that this host can talk to."""
        return [
            {"name": card.name, "description": card.description}
            for card in self.cards.values()
        ]

    async def send_message(
        self, agent_name: str, message: str, tool_context: ToolContext
    ):
        """Sends a message to a named remote agent and handles the response."""
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent '{agent_name}' not found.")

        state = tool_context.state
        client = self.remote_agent_connections[agent_name]
        task_id = None
        message_metadata = {}

        parts = [Part(root=TextPart(text=message))]  # Default part
        if message == "forward_signed_intent":
            signed_intent_data = state.get("signed_intent_mandate")
            if not signed_intent_data:
                raise ValueError(
                    "State inconsistency: 'signed_intent_mandate' not found."
                )

            # The object is nested, so we need to extract the inner dictionary
            signed_intent = signed_intent_data.get("signed_intent_mandate")
            if not signed_intent:
                raise ValueError(
                    "State inconsistency: Nested 'signed_intent_mandate' not found."
                )

            logger.info(
                f"Sending signed intent mandate: {json.dumps(signed_intent, indent=2)}"
            )
            # Send the entire signed intent as a structured DataPart
            parts = [
                Part(
                    root=DataPart(
                        data=signed_intent,
                        label="Signed Intent Mandate",
                        kind="data",
                    )
                )
            ]
        if message == "forward_signed_payment_mandate":
            signed_payment_data = state.get("signed_payment_mandate")
            if not signed_payment_data:
                raise ValueError(
                    "State inconsistency: 'signed_payment_mandate' not found."
                )

            signed_payment_mandate = signed_payment_data.get("signed_payment_mandate")
            if not signed_payment_mandate:
                raise ValueError(
                    "State inconsistency: Nested 'signed_payment_mandate' not found."
                )

            logger.info(
                f"Sending signed payment mandate: {json.dumps(signed_payment_mandate, indent=2)}"
            )
            parts = [
                Part(
                    root=DataPart(
                        data=signed_payment_mandate,
                        label="Signed Payment Mandate",
                        kind="data",
                    )
                )
            ]
        if message == "send_signed_payment_payload":
            signed_payload = state.get("signed_payment_payload")
            if not signed_payload:
                raise ValueError(
                    "State inconsistency: 'signed_payment_payload' not found."
                )

            purchase_task_data = state.get("purchase_task")
            if not purchase_task_data:
                raise ValueError(
                    "State inconsistency: 'purchase_task' not found to send signed payment."
                )
            original_task = Task.model_validate(purchase_task_data)
            task_id = original_task.id

            message_metadata[self.x402.PAYLOAD_KEY] = signed_payload
            message_metadata[self.x402.STATUS_KEY] = (
                PaymentStatus.PAYMENT_SUBMITTED.value
            )

        # --- Construct the message with metadata ---
        request = MessageSendParams(
            message=Message(
                messageId=str(uuid.uuid4()),
                role="user",
                parts=parts,
                contextId=state.get("context_id"),
                taskId=task_id,
                metadata=message_metadata if message_metadata else None,
            )
        )

        # Send the message and wait for the task result
        response_task = await client.send_message(
            request.message.message_id, request, self.task_callback
        )

        # --- Handle potential server errors ---
        if isinstance(response_task, JSONRPCError):
            logger.error(
                f"Received JSONRPCError from {agent_name}: {response_task.message}"
            )
            return f"Agent '{agent_name}' returned an error: {response_task.message} (Code: {response_task.code})"

        # Update state with the latest task info
        state["context_id"] = response_task.context_id
        state["last_contacted_agent"] = agent_name

        # --- Handle Response Based on Task State ---
        if response_task.status.state == TaskState.input_required:
            # The merchant requires payment. Store the task and trigger the UI.
            state["purchase_task"] = response_task.model_dump(by_alias=True)
            requirements = self.x402.get_payment_requirements(response_task)

            if not requirements or not requirements.accepts:
                raise ValueError(
                    "Server requested payment but sent no valid payment options."
                )

            # Construct the typed data for signing
            netowrk_rpc_url = os.getenv(
                "RPC_URL",
                "https://sepolia.base.org",
            )
            w3 = Web3(Web3.HTTPProvider(netowrk_rpc_url))
            chain_id = w3.eth.chain_id

            # Create the typed data payload
            typed_data = get_transfer_with_auth_typed_data(
                from_=self._wallet_address,
                to=requirements.pay_to,
                value=int(requirements.max_amount_required),
                valid_after=int(
                    (datetime.datetime.now(datetime.timezone.utc)).timestamp()
                ),
                valid_before=int(
                    (
                        datetime.datetime.now(datetime.timezone.utc)
                        + datetime.timedelta(hours=1)
                    ).timestamp()
                ),
                nonce="0x"
                + os.urandom(
                    32
                ).hex(),  # This will be replaced by the UI with the real nonce
                chain_id=chain_id,
                contract_address=requirements.asset,
                token_name=requirements.extra["name"],
                token_version=requirements.extra["version"],
            )

            return {
                "ui_interaction": {
                    "name": "sign_payment_request",
                    "data": typed_data,
                    "purchase_task": state["purchase_task"],
                }
            }

        elif response_task.status.state in (TaskState.completed, TaskState.failed):
            # The task is finished. Report the outcome.
            final_text = []
            if response_task.artifacts:
                for artifact in response_task.artifacts:
                    for part in artifact.parts:
                        part_root = part.root
                        if isinstance(part_root, TextPart):
                            final_text.append(part_root.text)
                        # --- Handle the CartMandate Artifact ---
                        elif (
                            isinstance(part_root, DataPart)
                            and "ap2.mandates.CartMandate" in part_root.data
                        ):
                            # The merchant has returned a signed cart.
                            cart_mandate_data = part_root.data[
                                "ap2.mandates.CartMandate"
                            ]
                            logger.info(
                                "Received cart mandate:"
                                f" {json.dumps(cart_mandate_data, indent=2)}"
                            )
                            state["cart_mandate"] = cart_mandate_data

                            # Extract payment methods and total price to present to the user
                            payment_methods = []
                            total_amount = None
                            total_currency = None
                            try:
                                # Safely access nested keys for payment methods
                                method_data = (
                                    cart_mandate_data.get("contents", {})
                                    .get("payment_request", {})
                                    .get("method_data", [])
                                )
                                for method in method_data:
                                    if "supported_methods" in method:
                                        payment_methods.append(
                                            method["supported_methods"]
                                        )

                                # Safely access nested keys for total price
                                total_details = (
                                    cart_mandate_data.get("contents", {})
                                    .get("payment_request", {})
                                    .get("details", {})
                                    .get("total", {})
                                    .get("amount", {})
                                )
                                total_amount = total_details.get("value")
                                total_currency = total_details.get("currency")

                            except Exception as e:
                                logger.error(
                                    "Error parsing payment details from cart"
                                    f" mandate: {e}"
                                )
                                return "The merchant sent a cart, but I couldn't understand the payment options or total price."

                            if not payment_methods:
                                return "The merchant has created a cart for you, but no payment methods were specified."

                            methods_str = "\n - ".join(payment_methods)
                            price_str = (
                                f" for a total of {total_amount} {total_currency}"
                                if total_amount and total_currency
                                else ""
                            )
                            return (
                                "The merchant has created a cart for you. Here are the available payment methods:"
                                f"\n - {methods_str}{price_str}\n\n"
                                "You can now tell me to 'pay for the cart'."
                            )

            if final_text:
                return " ".join(final_text)

            # Fallback for tasks with no text artifacts (e.g., payment settlement)
            if (
                self.x402.get_payment_status(response_task)
                == PaymentStatus.PAYMENT_COMPLETED
            ):
                return "Payment successful! Your purchase is complete."

            return f"Task with {agent_name} is {response_task.status.state.value}."

        else:
            # Handle other states like 'working'
            return f"Task with {agent_name} is now in state: {response_task.status.state.value}"
