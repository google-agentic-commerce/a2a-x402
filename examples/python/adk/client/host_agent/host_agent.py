"""Host agent implementation."""

import os
import uuid
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import httpx

from google.adk import Agent
from google.adk.tools.tool_context import ToolContext

from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    AgentSkill,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    TextPart,
)

from a2a_x402.types import X402ExtensionConfig, PaymentRequirements, PaymentPayload, x402PaymentRequiredResponse
from a2a_x402.core import process_payment
from a2a_x402.core.utils import create_payment_submission_message, X402Utils
from a2a_x402.core.wallet import process_payment_required
from ._remote_agent_connection import RemoteAgentConnection

class HostAgent:
    """Host agent implementation."""

    def __init__(
        self,
        private_key: str,
        network: str,
        remote_agent_addresses: List[str],
        http_client: httpx.Client,
        max_value: int = None,
        name: str = "host_agent",
        description: str = "A host agent that can communicate with remote agents and process x402 payments",
    ):
        """Initialize host agent.

        Args:
            private_key: Private key for signing payments (format depends on network)
            network: Network to use (e.g., 'sui-testnet', 'base-sepolia')
            remote_agent_addresses: List of remote agent addresses
            http_client: HTTP client
            max_value: Optional maximum payment value
            name: Agent name
            description: Agent description
        """
        # Wallet capabilities
        self.network = network
        if network.lower() in ['sui', 'sui-testnet']:
            # For Sui networks, create a pysui SyncClient
            try:
                from pysui import SuiConfig, SyncClient

                # Determine the RPC endpoint based on network
                if network.lower() == 'sui':
                    rpc_url = "https://fullnode.mainnet.sui.io:443"
                else:  # sui-testnet
                    rpc_url = os.getenv("SUI_TESTNET_RPC_URL", "https://fullnode.testnet.sui.io:443")

                # Create configuration with the RPC URL
                config = SuiConfig.user_config(
                    rpc_url=rpc_url,
                    prv_keys=[private_key]
                )

                # Create a SyncClient
                self.account = SyncClient(config=config)

            except ImportError:
                raise ImportError("pysui package is required for Sui networks. Install with: uv add pysui")
            except Exception as e:
                raise Exception(f"Error initializing Sui client: {str(e)}")
        else:
            # For EVM networks, use eth_account
            from eth_account import Account
            self.account = Account.from_key(private_key)

        self.max_value = max_value
        self.name = name
        self.description = description
        self.config = X402ExtensionConfig()

        # Orchestration capabilities
        self.http_client = http_client
        self.remote_agent_addresses = remote_agent_addresses
        self.remote_agent_connections: Dict[str, RemoteAgentConnection] = {}
        self.cards: Dict[str, AgentCard] = {}
        self._initialized = False

    def create_agent_card(self, url: str):
        """Creates the AgentCard metadata for discovery.

        Args:
            url: Base URL for this agent

        Returns:
            Agent card
        """
        # Use the RemoteAgentConnections implementation which uses create_x402_agent_card
        remote_conn = RemoteAgentConnection(None, None)  # Temporary instance just for card creation
        return remote_conn.create_agent_card(url, self.name, self.description)

    def get_skills(self) -> List[AgentSkill]:
        """Get agent skills.

        Returns:
            List of skills
        """
        return [
            AgentSkill(
                id="list_remote_agents",
                name="List Remote Agents",
                description="Lists available remote merchant agents",
                tags=["discovery", "merchant", "x402"],
                examples=[
                    "List available merchants",
                    "Show me who I can talk to",
                    "Find merchants that accept x402"
                ]
            ),
            AgentSkill(
                id="ask_merchant",
                name="Ask Merchant",
                description="Ask a merchant about products, prices, or availability",
                tags=["communication", "merchant", "inquiry"],
                examples=[
                    "What products does Lowes have?",
                    "Ask Lowes about drill prices",
                    "Check if merchant has smart bulbs"
                ]
            ),
            AgentSkill(
                id="purchase_item",
                name="Purchase Item",
                description="Purchase an item from a merchant using x402 payments",
                tags=["payment", "x402", "purchase", "sui"],
                examples=[
                    "Buy a drill from Lowes",
                    "Purchase the smart bulb",
                    "Get me a DeWalt drill"
                ]
            )
        ]

    async def _initialize(self):
        """Initialize connections to remote agents."""
        if self._initialized:
            return

        print("[host_agent] Starting initialization")
        print(f"[host_agent] Remote agent addresses: {self.remote_agent_addresses}")

        for address in self.remote_agent_addresses:
            print(f"[host_agent] Connecting to {address}")
            try:
                # Get agent card using resolver
                card_resolver = A2ACardResolver(self.http_client, address)
                agent_card = await card_resolver.get_agent_card()
                print(f"[host_agent] Connected to {address}, got agent card: {agent_card}")

                # Create remote connection with card
                remote_connection = RemoteAgentConnection(
                    client=self.http_client,
                    agent_card=agent_card
                )
                self.remote_agent_connections[agent_card.name] = remote_connection
                print(f"[host_agent] Added connection for {agent_card.name}")

            except Exception as e:
                print(f"[host_agent] Failed to connect to {address}: {e}")

        print(f"[host_agent] Initialization complete. Connected agents: {list(self.remote_agent_connections.keys())}")
        self._initialized = True

    async def before_agent_callback(self, callback_context: Any):
        """Called before agent processes a request."""
        await self._initialize()

    def create_agent(self) -> Agent:
        """Create the LLM agent instance.

        Returns:
            Configured LLM agent
        """
        return Agent(
            model="gemini-1.5-flash-latest",
            name=self.name,
            description=self.description,
            instruction="""You are a host agent that can purchase items from merchant agents using x402 payments.

Your workflow:
1. Use list_remote_agents to see available merchants
2. Use ask_merchant to inquire about products, prices, and availability
3. Use purchase_item to buy a specific item from a merchant (this handles the entire payment flow)
4. ALWAYS provide clear feedback to the user about purchase results

For purchases:
- When the user wants to buy something, use purchase_item with the merchant name and product name
- The purchase_item tool handles the entire flow: requesting the item, processing payment, and completing the purchase
- After purchase_item completes, tell the user whether the purchase succeeded or failed
- Include transaction details and blockchain explorer links when available

Always be helpful and ensure users know the final result of their actions.""",
            tools=[
                self.list_remote_agents,
                self.ask_merchant,
                self.purchase_item
            ],
            before_agent_callback=self.before_agent_callback
        )

    def list_remote_agents(self, tool_context: Any) -> Dict[str, Any]:
        """List available remote agents.

        Args:
            tool_context: Tool context

        Returns:
            Dictionary with agent information
        """
        print("[host_agent] Listing remote agents")
        print(f"[host_agent] Initialized: {self._initialized}")

        if not self._initialized:
            print("[host_agent] Not initialized, initializing now...")
            self.initialize()

        print(f"[host_agent] Remote connections: {list(self.remote_agent_connections.keys())}")

        agents = []
        for name, conn in self.remote_agent_connections.items():
            print(f"[host_agent] Adding agent {name} to list")
            agents.append({
                "name": name,
                "description": conn.card.description,
                "url": conn.card.url
            })

        print(f"[host_agent] Found {len(agents)} agents")
        return {"agents": agents}

    async def ask_merchant(self, agent_name: str, question: str, tool_context: Any = None) -> Dict[str, Any]:
        """Ask a merchant agent a question (without purchasing).

        Args:
            agent_name: The name of the merchant to ask.
            question: The question to ask.
            tool_context: The tool context.

        Returns:
            Response from the merchant
        """
        if agent_name not in self.remote_agent_connections:
            return {"status": "error", "message": f"Agent {agent_name} not found"}

        client = self.remote_agent_connections[agent_name]
        messageId = str(uuid.uuid4())
        
        request = MessageSendParams(
            id=messageId,
            message=Message(
                role="user",
                parts=[TextPart(text=question)],
                messageId=messageId,
            ),
            configuration=MessageSendConfiguration(
                acceptedOutputModes=["text", "text/plain", "image/png"],
            ),
        )

        try:
            result = await client.send_message(messageId, request=request)
            
            # Extract the response text from artifacts
            if hasattr(result, 'artifacts') and result.artifacts:
                for artifact in result.artifacts:
                    if hasattr(artifact, 'parts'):
                        for part in artifact.parts:
                            if hasattr(part.root, 'text'):
                                return {"status": "success", "response": part.root.text}
                            elif hasattr(part.root, 'data'):
                                return {"status": "success", "response": part.root.data}
            
            return {"status": "success", "response": str(result)}
        except Exception as e:
            return {"status": "error", "message": f"Failed to ask merchant: {str(e)}"}

    async def purchase_item(
        self,
        merchant_name: str,
        product_name: str,
        tool_context: Any = None
    ) -> Dict[str, Any]:
        """Purchase an item from a merchant. Handles the entire payment flow.

        Args:
            merchant_name: Name of the merchant.
            product_name: Name of the product to purchase.
            tool_context: Optional tool context.

        Returns:
            Dictionary with purchase status and details
        """
        try:
            if merchant_name not in self.remote_agent_connections:
                return {"status": "error", "message": f"Merchant {merchant_name} not found"}

            client = self.remote_agent_connections[merchant_name]
            
            # Step 1: Request to purchase the item (creates a task)
            print(f"[host_agent] Requesting to purchase {product_name} from {merchant_name}")
            messageId = str(uuid.uuid4())
            
            request = MessageSendParams(
                id=messageId,
                message=Message(
                    role="user",
                    parts=[TextPart(text=f"I would like to purchase {product_name}")],
                    messageId=messageId,
                    # No taskId - this creates a new task
                ),
                configuration=MessageSendConfiguration(
                    acceptedOutputModes=["text", "text/plain", "image/png"],
                ),
            )

            task = await client.send_message(messageId, request=request)
            
            if not hasattr(task, 'id'):
                return {"status": "error", "message": "Failed to create purchase task"}
            
            task_id = task.id
            print(f"[host_agent] Purchase task created: {task_id}")
            
            # Step 2: Check if we got payment requirements
            payment_requirements = None
            if hasattr(task, 'artifacts') and task.artifacts:
                for artifact in task.artifacts:
                    if hasattr(artifact, 'parts'):
                        for part in artifact.parts:
                            if hasattr(part.root, 'data') and isinstance(part.root.data, dict):
                                if 'payment_requirements' in part.root.data:
                                    payment_requirements = part.root.data['payment_requirements']
                                    print(f"[host_agent] Got payment requirements for task {task_id}")
                                    break
            
            if not payment_requirements:
                # Maybe the merchant just confirmed - check the response
                return {
                    "status": "error",
                    "message": "Merchant did not provide payment requirements. They may need more specific product information.",
                    "task_id": task_id
                }
            
            # Step 3: Process the payment
            print(f"[host_agent] Processing payment for task {task_id}")
            
            # Parse payment requirements
            payment_required = x402PaymentRequiredResponse(
                x402_version=1,
                accepts=[PaymentRequirements.model_validate(payment_requirements)],
                error="Payment required"
            )
            
            # Create payment payload
            payment_payload = process_payment_required(payment_required, self.account, self.max_value)
            
            # Step 4: Submit payment (continues the same task)
            print(f"[host_agent] Submitting payment for task {task_id}")
            
            submission_message = create_payment_submission_message(
                task_id=task_id,
                payment_payload=payment_payload,
                text="Payment authorization submitted for settlement."
            )
            
            # Send payment submission with the same task_id
            paymentMessageId = str(uuid.uuid4())
            payment_request = MessageSendParams(
                id=paymentMessageId,
                message=Message(
                    role="user",
                    parts=submission_message.parts,  # Use the parts from the submission message
                    messageId=paymentMessageId,
                    taskId=task_id,  # Continue the same task - CRITICAL for correlation
                    metadata=submission_message.metadata,  # Contains x402.payment.status and payload
                ),
                configuration=MessageSendConfiguration(
                    acceptedOutputModes=["text", "text/plain", "image/png"],
                ),
            )
            
            settlement_result = await client.send_message(paymentMessageId, request=payment_request)
            
            # Step 5: Extract settlement response
            settlement_message = "Purchase completed successfully!"
            if hasattr(settlement_result, 'artifacts') and settlement_result.artifacts:
                for artifact in settlement_result.artifacts:
                    if hasattr(artifact, 'parts'):
                        for part in artifact.parts:
                            if hasattr(part.root, 'text'):
                                settlement_message = part.root.text
                                break
                            elif hasattr(part.root, 'data'):
                                settlement_message = str(part.root.data)
                                break
            
            return {
                "status": "success",
                "message": settlement_message,
                "task_id": task_id,
                "payment": payment_payload.model_dump(),
                "product": product_name,
                "merchant": merchant_name
            }

        except Exception as e:
            return {"status": "error", "message": f"Purchase failed: {str(e)}"}
