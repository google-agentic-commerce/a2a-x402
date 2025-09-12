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
import time
import uuid

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
)
import eth_account
from eth_account.messages import encode_defunct
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# Local imports
from ._remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
from .wallet import Wallet
from a2a_x402.core.utils import x402Utils
from a2a_x402.types import PaymentPayload, x402PaymentRequiredResponse, PaymentStatus

logger = logging.getLogger(__name__)


class ClientAgent:
    """
    The orchestrator agent. It discovers other agents and delegates tasks
    to them, managing the conversation flow based on task states.
    """

    def __init__(
        self,
        remote_agent_addresses: list[str],
        http_client: httpx.AsyncClient,
        wallet: Wallet,
        task_callback: TaskUpdateCallback | None = None,
    ):
        """Initializes the ClientAgent."""
        self.task_callback = task_callback
        self.httpx_client = http_client
        self.wallet = wallet
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.remote_agent_addresses = remote_agent_addresses
        self.agents_info_str = ""
        self._initialized = False
        self.x402 = x402Utils()

    def create_agent(self) -> Agent:
        """Creates the ADK Agent instance."""
        return Agent(
            model="gemini-2.5-flash",
            name="client_agent",
            instruction=self.root_instruction,
            before_agent_callback=self.before_agent_callback,
            description="An orchestrator that delegates tasks to other agents.",
            tools=[self.list_remote_agents, self.send_message],
        )

    # --- Agent Setup and Instructions ---

    def root_instruction(self, context: ReadonlyContext) -> str:
        """Provides the master instruction set for the orchestrator LLM."""
        return f"""
You are a master orchestrator agent. Your job is to complete user requests by delegating tasks to a network of specialized agents.

**Standard Operating Procedure (SOP):**

1.  **Discover**: Always start by using `list_remote_agents` to see which agents are available.
2.  **Delegate**: Send the user's request to the most appropriate agent using `send_message`. For example, if the user wants to buy something, send the request to a merchant agent.
3.  **Confirm Payment**: If the merchant requires a payment, the system will return a confirmation message. You MUST present this message to the user.
4.  **Sign and Send**: If the user confirms they want to pay (e.g., by saying "yes"), you MUST call `send_message` again, targeting the *same agent*, with the exact message: "sign_and_send_payment". The system will handle the signing and sending of the payload.
5.  **Report Outcome**: Clearly report the final success or failure message to the user.

**System Context:**

* **Available Agents**:
    {self.agents_info_str}
"""

    async def before_agent_callback(self, callback_context: CallbackContext):
        """Initializes connections to remote agents before the first turn."""
        if self._initialized:
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

        if message == "sign_and_send_payment":
            # This is the second step: user has confirmed payment.
            purchase_task_data = state.get("purchase_task")
            if not purchase_task_data:
                raise ValueError("State inconsistency: 'purchase_task' not found to sign payment.")
            
            original_task = Task.model_validate(purchase_task_data)
            task_id = original_task.id
            
            requirements = self.x402.get_payment_requirements(original_task)
            if not requirements:
                raise ValueError("Could not find payment requirements in the original task.")

            # Sign the payment and prepare the payload for the merchant.
            signed_payload = self.wallet.sign_payment(requirements)
            message_metadata[self.x402.PAYLOAD_KEY] = signed_payload.model_dump(by_alias=True)
            message_metadata[self.x402.STATUS_KEY] = PaymentStatus.PAYMENT_SUBMITTED.value
            
            # The message text to the merchant is a simple confirmation.
            message = "send_signed_payment_payload"
        
        # --- Construct the message with metadata ---
        request = MessageSendParams(
            message=Message(
                messageId=str(uuid.uuid4()),
                role="user",
                parts=[Part(root=TextPart(text=message))],
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
            logger.error(f"Received JSONRPCError from {agent_name}: {response_task.message}")
            return f"Agent '{agent_name}' returned an error: {response_task.message} (Code: {response_task.code})"

        # Update state with the latest task info
        state["context_id"] = response_task.context_id
        state["last_contacted_agent"] = agent_name

        # --- Handle Response Based on Task State ---
        if response_task.status.state == TaskState.input_required:
            # The merchant requires payment. Store the task and ask the user for confirmation.
            state["purchase_task"] = response_task.model_dump(by_alias=True)
            requirements = self.x402.get_payment_requirements(response_task)
            
            if not requirements:
                raise ValueError("Server requested payment but sent no requirements.")

            # Extract details for the confirmation message.
            product_name = requirements.accepts[0].extra.get("name", "the item")
            price = requirements.accepts[0].max_amount_required
            
            return f"The merchant is requesting payment for '{product_name}' for {price} units. Do you want to approve this payment?"

        elif response_task.status.state in (TaskState.completed, TaskState.failed):
            # The task is finished. Report the outcome.
            final_text = []
            if response_task.artifacts:
                for artifact in response_task.artifacts:
                    for part in artifact.parts:
                        part_root = part.root
                        if isinstance(part_root, TextPart):
                            final_text.append(part_root.text)
            
            if final_text:
                return " ".join(final_text)
            
            # Fallback for tasks with no text artifacts (e.g., payment settlement)
            if self.x402.get_payment_status(response_task) == PaymentStatus.PAYMENT_COMPLETED:
                return "Payment successful! Your purchase is complete."

            return f"Task with {agent_name} is {response_task.status.state.value}."
        
        else:
            # Handle other states like 'working'
            return f"Task with {agent_name} is now in state: {response_task.status.state.value}"
