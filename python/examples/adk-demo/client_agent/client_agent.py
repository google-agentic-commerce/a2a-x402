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
from payments_py.x402 import (
    X402A2AUtils,
    X402PaymentStatus,
    SessionKeyPayload,
    PaymentPayload,
)
from payments_py.x402.types_v2 import PaymentPayloadV2
from payments_py.x402.extensions.nevermined import extract_all_nevermined_plans
from x402_a2a.types import PaymentRequirements
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
        self.nvm = X402A2AUtils()

    def _fetch_plan_name(self, plan_id: str, fallback: str = "Plan") -> str:
        """
        Fetch plan name from Nevermined API.

        The API returns plan data in the following structure:
        {
            "metadata": {
                "main": {
                    "name": "Plan Name"
                }
            }
        }

        Args:
            plan_id: The plan ID to fetch
            fallback: Default name if fetch fails or name not found

        Returns:
            Plan name from API, or fallback if unavailable
        """
        try:
            plan_details = self.payments.plans.get_plan(plan_id=plan_id)

            if isinstance(plan_details, dict) and "metadata" in plan_details:
                metadata = plan_details["metadata"]
                if (
                    isinstance(metadata, dict)
                    and "main" in metadata
                    and isinstance(metadata["main"], dict)
                ):
                    plan_name = metadata["main"].get("name")
                    if plan_name:
                        return plan_name

        except Exception as e:
            logger.warning(f"Could not fetch plan details for {plan_id}: {e}")

        return fallback

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
4.  **Sign and Send**: 
    - If the user selects a specific plan by number (e.g., "2"), you MUST call `send_message` again, targeting the *same agent*, with the exact message format: "sign_and_send_payment: 2" (where 2 is the plan number).
    - If the user confirms payment without selecting a specific plan (e.g., "yes"), you MUST call `send_message` again, targeting the *same agent*, with the exact message: "sign_and_send_payment".
    - The system will handle the signing and sending of the payload.
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

        # Handle payment signing - message can be "sign_and_send_payment" or "sign_and_send_payment: N"
        if message == "sign_and_send_payment" or message.startswith(
            "sign_and_send_payment:"
        ):
            # This is the second step: user has confirmed payment.
            logger.info(
                f"🔄 Entering 'sign_and_send_payment' block - message='{message}'"
            )

            # Extract plan number if present in message (e.g., "sign_and_send_payment: 2")
            import re

            plan_number_match = re.search(r"sign_and_send_payment:\s*(\d+)", message)
            if plan_number_match:
                plan_num = int(plan_number_match.group(1)) - 1
                state["selected_plan_index"] = plan_num
                logger.info(
                    f"📋 Extracted plan number from message: {plan_num + 1} (index: {plan_num})"
                )

            logger.info(
                f"🔍 State at start of sign_and_send_payment: "
                f"selected_extension_key={state.get('selected_extension_key')}, "
                f"selected_plan_index={state.get('selected_plan_index')}, "
                f"has_purchase_task={'purchase_task' in state}, "
                f"has_payment_required_extensions={'payment_required_extensions' in state}"
            )
            purchase_task_data = state.get("purchase_task")
            if not purchase_task_data:
                raise ValueError(
                    "State inconsistency: 'purchase_task' not found to sign payment."
                )

            original_task = Task.model_validate(purchase_task_data)
            task_id = original_task.id
            logger.info(f"📋 Retrieved purchase_task with id: {task_id}")

            payment_required_response = self.nvm.get_payment_requirements(original_task)
            if not payment_required_response:
                raise ValueError(
                    "Could not find payment requirements in the original task."
                )
            logger.info(
                f"✅ Retrieved payment_required_response: v2={hasattr(payment_required_response, 'x402_version') and payment_required_response.x402_version == 2}"
            )

            # Check if this is v2 with extensions (preferred)
            is_v2 = (
                hasattr(payment_required_response, "x402_version")
                and payment_required_response.x402_version == 2
                and hasattr(payment_required_response, "extensions")
                and payment_required_response.extensions
            )

            selected_extension_key = None
            requirements = None
            payment_required_extensions = None

            if is_v2:
                # v2: Extract plans from extensions
                payment_required_dict = (
                    payment_required_response.model_dump(by_alias=True)
                    if hasattr(payment_required_response, "model_dump")
                    else payment_required_response
                )
                payment_required_extensions = payment_required_dict.get(
                    "extensions", {}
                )
                nvm_plans = state.get("available_payment_plans")

                if not nvm_plans:
                    # Re-extract if not in state
                    nvm_plans = extract_all_nevermined_plans(payment_required_dict)
                    # Store in state for consistency
                    state["available_payment_plans"] = nvm_plans

                if not nvm_plans:
                    raise ValueError("No Nevermined plans found in extensions.")

                # Log plan order for debugging - CRITICAL: order must match what user saw!
                logger.info(
                    f"📋 Available plans (order matters!): "
                    + ", ".join(
                        [
                            f"Index {i}: {plan.get('extension_key', 'unknown')} (plan_id: {plan.get('plan_id', 'unknown')[:20]}...)"
                            for i, plan in enumerate(nvm_plans)
                        ]
                    )
                )

                # Handle plan selection - use extension key directly (more reliable than index)
                selected_extension_key = state.get("selected_extension_key")
                selected_plan_index = state.get("selected_plan_index")
                message_lower = message.lower().strip()

                logger.info(
                    f"🔍 Payment signing: message='{message}', stored selected_extension_key={selected_extension_key}, "
                    f"stored selected_plan_index={selected_plan_index}, available_plans={len(nvm_plans)}"
                )

                # SAFEGUARD: If selected_extension_key is missing but selected_plan_index exists, recover it
                if (
                    not selected_extension_key
                    and selected_plan_index is not None
                    and 0 <= selected_plan_index < len(nvm_plans)
                ):
                    selected_plan = nvm_plans[selected_plan_index]
                    selected_extension_key = selected_plan["extension_key"]
                    state["selected_extension_key"] = selected_extension_key
                    logger.warning(
                        f"⚠️ Recovered selected_extension_key from selected_plan_index: {selected_extension_key}"
                    )

                # Check if user provided a plan selection
                import re

                numbers = re.findall(r"\d+", message_lower)

                if numbers and len(nvm_plans) > 1:
                    # User explicitly selected a plan number - get the extension key
                    plan_num = int(numbers[0]) - 1
                    if 0 <= plan_num < len(nvm_plans):
                        selected_plan = nvm_plans[plan_num]
                        selected_extension_key = selected_plan["extension_key"]
                        state["selected_extension_key"] = selected_extension_key
                        logger.info(
                            f"✅ User selected plan {plan_num + 1} ({selected_extension_key}) from message: {message}"
                        )
                    else:
                        # Invalid number - use first plan
                        selected_plan = nvm_plans[0]
                        selected_extension_key = selected_plan["extension_key"]
                        state["selected_extension_key"] = selected_extension_key
                        logger.warning(
                            f"Invalid plan number {plan_num + 1}, defaulting to first plan ({selected_extension_key})"
                        )
                elif (
                    message_lower in ["first", "one", "default"] or len(nvm_plans) == 1
                ):
                    # User explicitly chose first plan
                    selected_plan = nvm_plans[0]
                    selected_extension_key = selected_plan["extension_key"]
                    state["selected_extension_key"] = selected_extension_key
                    logger.info(
                        f"User selected first plan (explicit): {selected_extension_key}"
                    )
                elif message_lower in ["yes", "y", "sign_and_send_payment"]:
                    # User confirmed payment or we're in payment signing flow - use previously selected extension key if available
                    if not selected_extension_key:
                        # Fallback to first plan if no selection stored
                        selected_plan = nvm_plans[0]
                        selected_extension_key = selected_plan["extension_key"]
                        state["selected_extension_key"] = selected_extension_key
                        logger.warning(
                            f"⚠️ User confirmed payment, no previous selection found in state - using first plan ({selected_extension_key})"
                        )
                    else:
                        logger.info(
                            f"✅ Using previously selected extension key from state: {selected_extension_key}"
                        )
                        # Find the plan by extension key to get other details
                        selected_plan = next(
                            (
                                p
                                for p in nvm_plans
                                if p.get("extension_key") == selected_extension_key
                            ),
                            nvm_plans[0],  # Fallback to first if not found
                        )
                else:
                    # No explicit selection - use stored extension key or default to first
                    if not selected_extension_key:
                        selected_plan = nvm_plans[0]
                        selected_extension_key = selected_plan["extension_key"]
                        state["selected_extension_key"] = selected_extension_key
                        logger.warning(
                            f"⚠️ No plan selection found in state, defaulting to first plan ({selected_extension_key})"
                        )
                    else:
                        logger.info(
                            f"✅ Using stored extension key from state: {selected_extension_key}"
                        )
                        # Find the plan by extension key
                        selected_plan = next(
                            (
                                p
                                for p in nvm_plans
                                if p.get("extension_key") == selected_extension_key
                            ),
                            nvm_plans[0],  # Fallback to first if not found
                        )

                # Also store the extensions dict in state if not already stored
                if payment_required_extensions:
                    state["payment_required_extensions"] = payment_required_extensions

                logger.info(
                    f"✅ Selected plan: extension_key={selected_extension_key}, plan_id={selected_plan['plan_id']}, agent_id={selected_plan['agent_id']}"
                )

                # Create PaymentRequirements from selected plan
                requirements = PaymentRequirements(
                    plan_id=selected_plan["plan_id"],
                    agent_id=selected_plan["agent_id"],
                    max_amount=selected_plan["max_amount"],
                    network=selected_plan["network"],
                    scheme=selected_plan["scheme"],
                    extra={},
                )

                logger.info(
                    f"Selected plan from extension '{selected_extension_key}': plan_id={requirements.plan_id}, agent_id={requirements.agent_id}, max_amount={requirements.max_amount}"
                )
            else:
                # v1: Extract from accepts array (backwards compatibility)
                if (
                    not payment_required_response.accepts
                    or len(payment_required_response.accepts) == 0
                ):
                    raise ValueError("No payment options provided by the server.")

                # Parse all requirements as PaymentRequirements objects
                all_requirements = []
                for req in payment_required_response.accepts:
                    if isinstance(req, dict):
                        req_obj = PaymentRequirements.model_validate(req)
                    else:
                        req_obj = req
                    all_requirements.append(req_obj)

                # Handle plan selection
                available_plans = state.get("available_payment_plans")
                selected_plan_index = state.get("selected_plan_index")

                if available_plans and len(available_plans) > 1:
                    message_lower = message.lower().strip()
                    import re

                    numbers = re.findall(r"\d+", message_lower)

                    if numbers:
                        plan_num = int(numbers[0]) - 1
                        if 0 <= plan_num < len(all_requirements):
                            selected_plan_index = plan_num
                        else:
                            selected_plan_index = 0
                    elif message_lower in ["first", "one", "default", "yes", "y"]:
                        selected_plan_index = 0
                    else:
                        if selected_plan_index is None:
                            selected_plan_index = 0

                    state["selected_plan_index"] = selected_plan_index

                # Select the plan
                if selected_plan_index is not None and 0 <= selected_plan_index < len(
                    all_requirements
                ):
                    requirements = all_requirements[selected_plan_index]
                else:
                    requirements = all_requirements[0]

                logger.info(
                    f"Selected payment requirement: plan_id={requirements.plan_id}, agent_id={requirements.agent_id}, max_amount={requirements.max_amount}"
                )

            # Get X402 access token from Nevermined for the agent and plan
            try:
                # Get the subscriber address from the payments instance
                subscriber_address = self.payments.get_account_address()

                if not subscriber_address:
                    raise ValueError(
                        "Could not get subscriber address from NVM API key"
                    )

                # Request X402 access token from Nevermined API
                token_result = self.payments.x402.get_x402_access_token(
                    plan_id=requirements.plan_id, agent_id=requirements.agent_id
                )
                x402_access_token = token_result["accessToken"]

                if is_v2:
                    # V2: Create PaymentPayloadV2 with only the selected extension
                    # Copy only the selected extension, not all extensions
                    selected_extensions = {}

                    # Get payment_required_extensions from state if not already available
                    if not payment_required_extensions:
                        payment_required_extensions = state.get(
                            "payment_required_extensions"
                        )

                    # Use extension key directly from state (more reliable than variable)
                    stored_extension_key = (
                        state.get("selected_extension_key") or selected_extension_key
                    )

                    logger.info(
                        f"🔍 Constructing payment payload: "
                        f"stored_extension_key={stored_extension_key}, "
                        f"selected_extension_key={selected_extension_key}, "
                        f"payment_required_extensions keys={list(payment_required_extensions.keys()) if payment_required_extensions else 'None'}"
                    )

                    if stored_extension_key and payment_required_extensions:
                        if stored_extension_key in payment_required_extensions:
                            selected_extensions[stored_extension_key] = (
                                payment_required_extensions[stored_extension_key]
                            )
                            logger.info(
                                f"✅ Creating V2 payment payload with selected extension: {stored_extension_key}"
                            )
                        else:
                            logger.error(
                                f"❌ Selected extension key '{stored_extension_key}' not found in extensions! "
                                f"Available keys: {list(payment_required_extensions.keys())}"
                            )
                            logger.warning(f"⚠️ Falling back to copying all extensions")
                            selected_extensions = payment_required_extensions
                    else:
                        # Fallback: copy all extensions from payment_required_response
                        if not stored_extension_key:
                            logger.error(
                                f"❌ No extension key found in state or variable! Cannot determine which extension to use."
                            )
                        if not payment_required_extensions:
                            logger.error(f"❌ payment_required_extensions is None!")
                        payment_required_dict = (
                            payment_required_response.model_dump(by_alias=True)
                            if hasattr(payment_required_response, "model_dump")
                            else payment_required_response
                        )
                        selected_extensions = payment_required_dict.get(
                            "extensions", {}
                        )
                        logger.warning(
                            f"⚠️ Fallback: Creating V2 payment payload with all extensions: {list(selected_extensions.keys())}"
                        )

                    payment_payload = PaymentPayloadV2(
                        x402_version=2,
                        scheme=requirements.scheme,
                        network=requirements.network,
                        payload=SessionKeyPayload(session_key=x402_access_token),
                        extensions=selected_extensions,  # Only selected extension (or all if single plan)
                    )
                else:
                    # V1: Create standard PaymentPayload
                    logger.info("Creating V1 payment payload (no extensions)")

                    payment_payload = PaymentPayload(
                        nvm_version=1,
                        scheme=requirements.scheme,
                        network=requirements.network,
                        payload=SessionKeyPayload(session_key=x402_access_token),
                    )

                # Add subscriber address to requirements for verification/settlement
                if not requirements.extra:
                    requirements.extra = {}
                requirements.extra["subscriber_address"] = subscriber_address
                requirements_data = requirements.model_dump(by_alias=True)

                # Update the metadata with the payment payload
                message_metadata[self.nvm.PAYLOAD_KEY] = payment_payload.model_dump(
                    by_alias=True
                )
                # Use .value to ensure we're storing the string value, not the enum
                message_metadata[self.nvm.STATUS_KEY] = (
                    X402PaymentStatus.PAYMENT_SUBMITTED.value
                )
                message_metadata["payment_requirements"] = requirements_data

                logger.info(
                    f"✅ Generated X402 access token for plan {requirements.plan_id}"
                )
                logger.info(f"Subscriber address: {subscriber_address}")
                logger.info(
                    f"📤 Setting payment status to: {X402PaymentStatus.PAYMENT_SUBMITTED.value}"
                )
                logger.info(
                    f"📤 Payment payload in metadata: {self.nvm.PAYLOAD_KEY in message_metadata}"
                )
                logger.info(
                    f"📤 Extensions in payload: {list(payment_payload.extensions.keys()) if hasattr(payment_payload, 'extensions') and payment_payload.extensions else 'None'}"
                )

            except Exception as e:
                logger.error(
                    f"❌ Failed to generate X402 access token: {e}", exc_info=True
                )
                raise ValueError(f"Failed to generate X402 access token: {str(e)}")

            # The message text to the merchant is a simple confirmation.
            message = "send_signed_payment_payload"

        # --- Construct the message with metadata ---
        logger.info(
            f"📨 Constructing message: text='{message}', "
            f"has_metadata={bool(message_metadata)}, "
            f"metadata_keys={list(message_metadata.keys()) if message_metadata else []}, "
            f"has_payment_status={self.nvm.STATUS_KEY in message_metadata if message_metadata else False}, "
            f"has_payment_payload={self.nvm.PAYLOAD_KEY in message_metadata if message_metadata else False}"
        )
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
        # Check if user is confirming payment with a plan selection
        message_lower_check = message.lower().strip()
        import re

        numbers_check = re.findall(r"\d+", message_lower_check)
        is_plan_selection = (
            response_task.status.state == TaskState.input_required
            and numbers_check
            and state.get("purchase_task") is not None
        )

        if response_task.status.state == TaskState.input_required:
            # The merchant requires payment. Store the task and ask the user for confirmation.
            state["purchase_task"] = response_task.model_dump(by_alias=True)
            requirements = self.nvm.get_payment_requirements(response_task)

            if not requirements:
                raise ValueError("Server requested payment but sent no requirements.")

            # Check if this is v2 with extensions (preferred approach)
            is_v2 = (
                hasattr(requirements, "x402_version")
                and requirements.x402_version == 2
                and hasattr(requirements, "extensions")
                and requirements.extensions
            )

            if is_v2:
                # v2: Extract plans from extensions (preferred)
                payment_required_dict = (
                    requirements.model_dump(by_alias=True)
                    if hasattr(requirements, "model_dump")
                    else requirements
                )
                nvm_plans = extract_all_nevermined_plans(payment_required_dict)

                if nvm_plans:
                    # Multiple plans from extensions
                    if len(nvm_plans) > 1:
                        # Check if user already selected a plan number in this message
                        message_lower = message.lower().strip()
                        import re

                        numbers = re.findall(r"\d+", message_lower)

                        # Parse plan selection if user provided a number
                        if numbers:
                            plan_num = int(numbers[0]) - 1
                            if 0 <= plan_num < len(nvm_plans):
                                # User selected a plan - store the extension key directly (more reliable than index)
                                selected_plan = nvm_plans[plan_num]
                                selected_extension_key = selected_plan["extension_key"]
                                state["selected_extension_key"] = selected_extension_key
                                state["selected_plan_index"] = (
                                    plan_num  # Keep for backwards compatibility
                                )
                                state["available_payment_plans"] = nvm_plans
                                state["payment_required_extensions"] = (
                                    payment_required_dict.get("extensions", {})
                                )
                                logger.info(
                                    f"✅ User selected plan {plan_num + 1} ({selected_extension_key}) from message: {message}. Proceeding to payment."
                                )
                                # Don't return here - fall through to payment processing section below
                            else:
                                # Invalid plan number - show options
                                logger.warning(
                                    f"Invalid plan number {plan_num + 1}, showing options"
                                )
                                # Fall through to show options
                        else:
                            # No plan number in message - show options
                            plan_options_text = []
                            subscriber_address = self.payments.get_account_address()

                            for idx, plan_info in enumerate(nvm_plans):
                                # Fetch plan name from Nevermined API
                                plan_name = self._fetch_plan_name(
                                    plan_id=plan_info["plan_id"],
                                    fallback=f"Plan {idx + 1}",
                                )

                                # Try to get balance for this plan
                                balance_msg = ""
                                try:
                                    balance_info = self.payments.plans.get_plan_balance(
                                        plan_id=plan_info["plan_id"],
                                        account_address=subscriber_address,
                                    )
                                    balance_msg = (
                                        f" (Balance: {balance_info.balance} credits)"
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Could not fetch balance for plan {plan_info['plan_id']}: {e}"
                                    )

                                plan_options_text.append(
                                    f"{idx + 1}. {plan_name}: {plan_info['max_amount']} credits{balance_msg}"
                                )

                            # Store plan info (including extension keys) for later selection
                            state["available_payment_plans"] = nvm_plans
                            state["payment_required_extensions"] = (
                                payment_required_dict.get("extensions", {})
                            )

                            return (
                                f"The merchant is requesting payment. Multiple payment plans are available:\n\n"
                                + "\n".join(plan_options_text)
                                + f"\n\nPlease choose a plan (1-{len(nvm_plans)}) or say 'yes' to use the first plan.\n"
                                + "Do you want to proceed with payment?"
                            )

                        # If we get here, user selected a plan number - proceed to payment processing
                        # Store the purchase_task if not already stored
                        if "purchase_task" not in state:
                            state["purchase_task"] = response_task.model_dump(
                                by_alias=True
                            )

                        # Verify state is stored correctly before recursive call
                        stored_extension_key = state.get("selected_extension_key")
                        stored_index = state.get("selected_plan_index")
                        logger.info(
                            f"🔄 About to recursively call send_message with 'sign_and_send_payment' - "
                            f"selected_extension_key={stored_extension_key}, selected_plan_index={stored_index}, "
                            f"has_purchase_task={'purchase_task' in state}"
                        )

                        # User has selected a plan, so proceed directly to payment processing
                        # by recursively calling send_message with "sign_and_send_payment"
                        return await self.send_message(
                            agent_name, "sign_and_send_payment", tool_context
                        )

                    # Single plan from extension
                    plan_info = nvm_plans[0]
                    amount = plan_info["max_amount"]
                    agent_id = plan_info["agent_id"]
                    plan_id = plan_info["plan_id"]

                    # Fetch plan name from Nevermined API
                    plan_name = self._fetch_plan_name(plan_id=plan_id, fallback="Plan")

                    # Get current balance
                    try:
                        subscriber_address = self.payments.get_account_address()
                        balance_info = self.payments.plans.get_plan_balance(
                            plan_id=plan_id, account_address=subscriber_address
                        )
                        current_balance = balance_info.balance
                        balance_msg = (
                            f"Your current balance: {current_balance} credits."
                        )
                    except Exception as e:
                        logger.warning(f"Could not fetch plan balance: {e}")
                        balance_msg = "Balance information unavailable."

                    # Store for payment
                    state["available_payment_plans"] = nvm_plans
                    state["payment_required_extensions"] = payment_required_dict.get(
                        "extensions", {}
                    )

                    return f"The merchant is requesting payment for agent {agent_id} with {plan_name} (plan {plan_id}) for {amount} credits.\n{balance_msg}\nDo you want to approve this payment?"

            # Fallback to v1 accepts array (backwards compatibility)
            if not requirements.accepts:
                raise ValueError(
                    "Server requested payment but sent no valid payment options."
                )

            # Parse all payment options from accepts array
            all_payment_options = []
            for opt in requirements.accepts:
                if isinstance(opt, dict):
                    opt_obj = PaymentRequirements.model_validate(opt)
                else:
                    opt_obj = opt
                all_payment_options.append(opt_obj)

            # If multiple plans available, show options to user
            if len(all_payment_options) > 1:
                plan_options_text = []
                subscriber_address = self.payments.get_account_address()

                for idx, opt in enumerate(all_payment_options):
                    # Fetch plan name from Nevermined API
                    plan_name = self._fetch_plan_name(
                        plan_id=opt.plan_id, fallback=f"Plan {idx + 1}"
                    )

                    # Try to get balance for this plan
                    balance_msg = ""
                    try:
                        balance_info = self.payments.plans.get_plan_balance(
                            plan_id=opt.plan_id, account_address=subscriber_address
                        )
                        balance_msg = f" (Balance: {balance_info.balance} credits)"
                    except Exception as e:
                        logger.warning(
                            f"Could not fetch balance for plan {opt.plan_id}: {e}"
                        )

                    plan_options_text.append(
                        f"{idx + 1}. {plan_name}: {opt.max_amount} credits{balance_msg}"
                    )

                # Store all options in state for later selection
                state["available_payment_plans"] = [
                    opt.model_dump(by_alias=True) if hasattr(opt, "model_dump") else opt
                    for opt in all_payment_options
                ]

                return (
                    f"The merchant is requesting payment. Multiple payment plans are available:\n\n"
                    + "\n".join(plan_options_text)
                    + f"\n\nPlease choose a plan (1-{len(all_payment_options)}) or say 'yes' to use the first plan.\n"
                    + "Do you want to proceed with payment?"
                )

            # Single plan - use it directly
            payment_option = all_payment_options[0]
            amount = payment_option.max_amount
            agent_id = payment_option.agent_id
            plan_id = payment_option.plan_id

            # Get current balance for the plan
            try:
                subscriber_address = self.payments.get_account_address()
                balance_info = self.payments.plans.get_plan_balance(
                    plan_id=plan_id, account_address=subscriber_address
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
            logger.info(
                f"Task metadata: {response_task.metadata if hasattr(response_task, 'metadata') else 'No metadata'}"
            )
            logger.info(
                f"Task status message metadata: {response_task.status.message.metadata if hasattr(response_task.status, 'message') and hasattr(response_task.status.message, 'metadata') else 'No status message metadata'}"
            )

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
                hasattr(response_task, "metadata")
                and response_task.metadata
                and response_task.metadata.get("x402_payment_verified") == True
            )

            payment_completed = (
                payment_status == X402PaymentStatus.PAYMENT_COMPLETED
                or (
                    is_payment_flow
                    and has_payment_verified
                    and response_task.status.state == TaskState.completed
                )
            )

            logger.info(f"Payment status from task: {payment_status}")
            logger.info(
                f"Is payment flow: {is_payment_flow}, Has verified: {has_payment_verified}"
            )
            logger.info(f"Payment completed status: {payment_completed}")

            # Add balance information and transaction info if payment was completed
            balance_info = ""
            transaction_info = ""
            if payment_completed:
                logger.info("Fetching updated balance after payment completion...")
                try:
                    # Get the plan_id from the stored purchase task
                    purchase_task_data = state.get("purchase_task")
                    logger.info(
                        f"Purchase task data exists: {purchase_task_data is not None}"
                    )
                    if purchase_task_data:
                        original_task = Task.model_validate(purchase_task_data)
                        payment_required_response = self.nvm.get_payment_requirements(
                            original_task
                        )
                        if (
                            payment_required_response
                            and payment_required_response.accepts
                        ):
                            # Parse dict into PaymentRequirements model
                            payment_opt = payment_required_response.accepts[0]
                            if isinstance(payment_opt, dict):
                                payment_opt = PaymentRequirements.model_validate(
                                    payment_opt
                                )

                            plan_id = payment_opt.plan_id
                            subscriber_address = self.payments.get_account_address()

                            logger.info(
                                f"Fetching balance for plan {plan_id}, address {subscriber_address}"
                            )
                            balance_data = self.payments.plans.get_plan_balance(
                                plan_id=plan_id, account_address=subscriber_address
                            )
                            # balance_data is a PlanBalance Pydantic model, not a dict
                            updated_balance = balance_data.balance
                            balance_info = (
                                f"\nYour updated balance: {updated_balance} credits."
                            )
                            logger.info(
                                f"Successfully fetched balance: {updated_balance} credits"
                            )
                except Exception as e:
                    logger.warning(
                        f"Could not fetch updated balance: {e}", exc_info=True
                    )

                # Extract transaction hash from settlement receipt
                try:
                    logger.info(f"Looking for transaction in task...")
                    logger.info(
                        f"Task metadata: {response_task.metadata if hasattr(response_task, 'metadata') else 'No task metadata'}"
                    )
                    logger.info(
                        f"Has status.message: {hasattr(response_task.status, 'message')}"
                    )

                    # Try task.metadata first (might be stored here)
                    receipts = None
                    if hasattr(response_task, "metadata") and response_task.metadata:
                        receipts = response_task.metadata.get(self.nvm.RECEIPTS_KEY)
                        logger.info(f"Receipts from task.metadata: {receipts}")

                    # Try task.status.message.metadata if not found
                    if (
                        not receipts
                        and hasattr(response_task.status, "message")
                        and response_task.status.message
                    ):
                        logger.info(
                            f"Has message.metadata: {hasattr(response_task.status.message, 'metadata')}"
                        )
                        logger.info(
                            f"Message metadata: {response_task.status.message.metadata if hasattr(response_task.status.message, 'metadata') else 'No message metadata'}"
                        )

                        if (
                            hasattr(response_task.status.message, "metadata")
                            and response_task.status.message.metadata
                        ):

                            receipts = response_task.status.message.metadata.get(
                                self.nvm.RECEIPTS_KEY
                            )
                            logger.info(
                                f"Receipts from status.message.metadata: {receipts}"
                            )

                            if not receipts:
                                logger.info(
                                    f"Available keys in message.metadata: {list(response_task.status.message.metadata.keys())}"
                                )

                    # Process receipts if found
                    if receipts:
                        tx_hash = receipts.get("transaction")
                        network = receipts.get("network", "base-sepolia")

                        if tx_hash:
                            # Create BaseScan link
                            if "sepolia" in network.lower():
                                basescan_url = (
                                    f"https://sepolia.basescan.org/tx/{tx_hash}"
                                )
                            else:
                                basescan_url = f"https://basescan.org/tx/{tx_hash}"

                            transaction_info = f"\n\n🔗 Transaction: {basescan_url}"
                            logger.info(f"✅ Transaction hash found: {tx_hash}")
                    else:
                        logger.info(f"⚠️ No transaction receipts found in task")

                except Exception as e:
                    logger.warning(
                        f"Could not extract transaction info: {e}", exc_info=True
                    )

            if final_text:
                result = " ".join(final_text)
                logger.info(
                    f"Final text exists. Payment completed: {payment_completed}, Balance info: '{balance_info}', Transaction info: '{transaction_info}'"
                )
                if payment_completed:
                    if balance_info:
                        result += balance_info
                    if transaction_info:
                        result += transaction_info
                    logger.info(
                        f"Appending payment info to result. Final result: {result}"
                    )
                else:
                    logger.info(
                        f"NOT appending payment info. Completed={payment_completed}"
                    )
                return result

            # Fallback for tasks with no text artifacts (e.g., payment settlement)
            if payment_completed:
                return f"Payment successful! Your purchase is complete.{balance_info}{transaction_info}"

            return f"Task with {agent_name} is {response_task.status.state.value}."

        else:
            # Handle other states like 'working'
            return f"Task with {agent_name} is now in state: {response_task.status.state.value}"
