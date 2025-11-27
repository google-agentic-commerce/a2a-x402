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
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext

# Local imports
from ._remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback
from x402_a2a.core.utils import NvmUtils
from x402_a2a.types import PaymentStatus
from payments_py.payments import Payments

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
        payments: Payments,
        task_callback: TaskUpdateCallback | None = None,
    ):
        """Initializes the ClientAgent."""
        self.task_callback = task_callback
        self.httpx_client = http_client
        self.payments = payments
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.remote_agent_addresses = remote_agent_addresses
        self.agents_info_str = ""
        self._initialized = False
        self.nvm = NvmUtils()

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
3.  **Confirm Payment**: If the merchant requires a payment, the system will return a confirmation message. You MUST present this EXACT message to the user WITHOUT modification. This includes important details like credit amounts, balance information, plan IDs, and agent IDs.
4.  **Sign and Send**: If the user confirms they want to pay (e.g., by saying "yes"), you MUST call `send_message` again, targeting the *same agent*, with the exact message: "sign_and_send_payment". The system will handle the signing and sending of the payload.
5.  **Report Outcome**: Present the final success or failure message to the user EXACTLY as received, including any balance information. Do NOT summarize or omit any details, especially credit balance updates.

**CRITICAL RULES:**
- ALWAYS include balance information when provided in tool responses
- NEVER omit plan IDs, agent IDs, or credit amounts from payment confirmations
- Present messages exactly as returned by the tools - do not rewrite or simplify them

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
                raise ValueError(
                    "State inconsistency: 'purchase_task' not found to sign payment."
                )

            original_task = Task.model_validate(purchase_task_data)
            task_id = original_task.id

            payment_required_response = self.nvm.get_payment_requirements(original_task)
            if not payment_required_response:
                raise ValueError(
                    "Could not find payment requirements in the original task."
                )

            # Extract the first PaymentRequirements from the accepts list
            if not payment_required_response.accepts or len(payment_required_response.accepts) == 0:
                raise ValueError("No payment options provided by the server.")
            
            requirements = payment_required_response.accepts[0]
            logger.info(f"Selected payment requirement: plan_id={requirements.plan_id}, agent_id={requirements.agent_id}, max_amount={requirements.max_amount}")

            # Get X402 access token from Nevermined for the agent and plan
            try:
                # Get the subscriber address from the payments instance
                subscriber_address = self.payments.get_account_address()
                
                if not subscriber_address:
                    raise ValueError("Could not get subscriber address from NVM API key")
                
                # Request X402 access token from Nevermined API
                token_result = self.payments.x402.get_x402_access_token(
                    plan_id=requirements.plan_id,
                    agent_id=requirements.agent_id
                )
                x402_access_token = token_result["accessToken"]
                
                # Create the payment payload with the X402 access token
                from payments_py.x402 import SessionKeyPayload, PaymentPayload
                
                payment_payload = PaymentPayload(
                    nvm_version=1,
                    scheme=requirements.scheme,
                    network=requirements.network,
                    payload=SessionKeyPayload(session_key=x402_access_token)
                )
                
                # Add subscriber address to requirements for verification/settlement
                if not requirements.extra:
                    requirements.extra = {}
                requirements.extra["subscriber_address"] = subscriber_address
                
                # Update the metadata with the payment payload
                message_metadata[self.nvm.PAYLOAD_KEY] = payment_payload.model_dump(
                    by_alias=True
                )
                message_metadata[self.nvm.STATUS_KEY] = (
                    PaymentStatus.PAYMENT_SUBMITTED.value
                )
                message_metadata["payment_requirements"] = requirements.model_dump(
                    by_alias=True
                )
                
                logger.info(f"✅ Generated X402 access token for plan {requirements.plan_id}")
                logger.info(f"Subscriber address: {subscriber_address}")
                
            except Exception as e:
                logger.error(f"❌ Failed to generate X402 access token: {e}", exc_info=True)
                raise ValueError(f"Failed to generate X402 access token: {str(e)}")

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
            logger.error(
                f"Received JSONRPCError from {agent_name}: {response_task.message}"
            )
            return f"Agent '{agent_name}' returned an error: {response_task.message} (Code: {response_task.code})"

        # Update state with the latest task info
        state["context_id"] = response_task.context_id
        state["last_contacted_agent"] = agent_name

        # --- Handle Response Based on Task State ---
        if response_task.status.state == TaskState.input_required:
            # The merchant requires payment. Store the task and ask the user for confirmation.
            state["purchase_task"] = response_task.model_dump(by_alias=True)
            requirements = self.nvm.get_payment_requirements(response_task)

            if not requirements:
                raise ValueError("Server requested payment but sent no requirements.")

            if not requirements.accepts:
                raise ValueError(
                    "Server requested payment but sent no valid payment options."
                )

            # Extract details for the confirmation message.
            payment_option = requirements.accepts[0]
            amount = payment_option.max_amount
            agent_id = payment_option.agent_id
            plan_id = payment_option.plan_id

            # Get current balance for the plan
            try:
                subscriber_address = self.payments.get_account_address()
                balance_info = self.payments.plans.get_plan_balance(
                    plan_id=plan_id,
                    account_address=subscriber_address
                )
                # balance_info is a PlanBalance Pydantic model, not a dict
                current_balance = balance_info.balance
                balance_msg = f"Your current balance: {current_balance} credits."
            except Exception as e:
                logger.warning(f"Could not fetch plan balance: {e}")
                balance_msg = "Balance information unavailable."

            return f"The merchant is requesting payment for agent {agent_id} with plan {plan_id} for {amount} credits.\n{balance_msg}\nDo you want to approve this payment?"

        elif response_task.status.state in (TaskState.completed, TaskState.failed):
            # The task is finished. Report the outcome.
            logger.info(f"Task completed. Task state: {response_task.status.state}")
            logger.info(f"Task metadata: {response_task.metadata if hasattr(response_task, 'metadata') else 'No metadata'}")
            logger.info(f"Task status message metadata: {response_task.status.message.metadata if hasattr(response_task.status, 'message') and hasattr(response_task.status.message, 'metadata') else 'No status message metadata'}")
            
            final_text = []
            if response_task.artifacts:
                for artifact in response_task.artifacts:
                    for part in artifact.parts:
                        part_root = part.root
                        if isinstance(part_root, TextPart):
                            final_text.append(part_root.text)

            # Check if this was a payment completion
            # The payment status might be in status.message.metadata OR we can infer it from task metadata
            payment_status = self.nvm.get_payment_status(response_task)
            
            # Also check if this is a payment completion based on our stored state
            # If we have a purchase_task stored, and the task has x402_payment_verified, it's completed
            is_payment_flow = state.get("purchase_task") is not None
            has_payment_verified = (
                hasattr(response_task, 'metadata') and 
                response_task.metadata and 
                response_task.metadata.get('x402_payment_verified') == True
            )
            
            payment_completed = (
                payment_status == PaymentStatus.PAYMENT_COMPLETED or 
                (is_payment_flow and has_payment_verified and response_task.status.state == TaskState.completed)
            )
            
            logger.info(f"Payment status from task: {payment_status}")
            logger.info(f"Is payment flow: {is_payment_flow}, Has verified: {has_payment_verified}")
            logger.info(f"Payment completed status: {payment_completed}")

            # Add balance information if payment was completed
            balance_info = ""
            if payment_completed:
                logger.info("Fetching updated balance after payment completion...")
                try:
                    # Get the plan_id from the stored purchase task
                    purchase_task_data = state.get("purchase_task")
                    logger.info(f"Purchase task data exists: {purchase_task_data is not None}")
                    if purchase_task_data:
                        original_task = Task.model_validate(purchase_task_data)
                        payment_required_response = self.nvm.get_payment_requirements(original_task)
                        if payment_required_response and payment_required_response.accepts:
                            plan_id = payment_required_response.accepts[0].plan_id
                            subscriber_address = self.payments.get_account_address()
                            
                            logger.info(f"Fetching balance for plan {plan_id}, address {subscriber_address}")
                            balance_data = self.payments.plans.get_plan_balance(
                                plan_id=plan_id,
                                account_address=subscriber_address
                            )
                            # balance_data is a PlanBalance Pydantic model, not a dict
                            updated_balance = balance_data.balance
                            balance_info = f"\nYour updated balance: {updated_balance} credits."
                            logger.info(f"Successfully fetched balance: {updated_balance} credits")
                except Exception as e:
                    logger.warning(f"Could not fetch updated balance: {e}", exc_info=True)

            if final_text:
                result = " ".join(final_text)
                logger.info(f"Final text exists. Payment completed: {payment_completed}, Balance info: '{balance_info}'")
                if payment_completed and balance_info:
                    result += balance_info
                    logger.info(f"Appending balance info to result. Final result: {result}")
                else:
                    logger.info(f"NOT appending balance. Completed={payment_completed}, has_balance={bool(balance_info)}")
                return result

            # Fallback for tasks with no text artifacts (e.g., payment settlement)
            if payment_completed:
                return f"Payment successful! Your purchase is complete.{balance_info}"

            return f"Task with {agent_name} is {response_task.status.state.value}."

        else:
            # Handle other states like 'working'
            return f"Task with {agent_name} is now in state: {response_task.status.state.value}"
