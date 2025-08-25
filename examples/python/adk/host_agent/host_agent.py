"""Host agent implementation."""

import os
import uuid
from typing import Dict, Any, List
from dotenv import load_dotenv
import httpx
from eth_account import Account

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

from a2a_x402.types import X402ExtensionConfig, X402A2AMessage, PaymentRequired
from a2a_x402.core import process_payment
from ._remote_agent_connection import RemoteAgentConnection

class HostAgent:
    """Host agent implementation."""

    def __init__(
        self,
        private_key: str,
        remote_agent_addresses: List[str],
        http_client: httpx.Client,
        max_value: int = None,
        name: str = "host_agent",
        description: str = "A host agent that can communicate with remote agents and process x402 payments",
    ):
        """Initialize host agent.

        Args:
            private_key: Ethereum private key for signing payments
            remote_agent_addresses: List of remote agent addresses
            http_client: HTTP client
            max_value: Optional maximum payment value
            name: Agent name
            description: Agent description
        """
        # Wallet capabilities
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

    def create_agent_card(self, url: str) -> AgentCard:
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
                id="send_message",
                name="Send Message to Agent",
                description="Send a message to a remote merchant agent",
                tags=["communication", "merchant", "x402"],
                examples=[
                    "Ask merchant about a product",
                    "Send message to Lowes",
                    "Talk to merchant agent"
                ]
            ),
            AgentSkill(
                id="process_payment",
                name="Process x402 Payment",
                description="Process and sign an x402 payment request",
                tags=["payment", "x402", "ethereum"],
                examples=[
                    "Pay for the item",
                    "Process payment request",
                    "Sign x402 payment"
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
            instruction="This agent orchestrates the decomposition of the user request into"
                " tasks that can be performed by the child agents. It also handles the creation of"
                " the payment object and the signing of the payment object.",
            tools=[
                self.list_remote_agents,
                self.send_message,
                self.process_payment
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

    async def send_message(self, agent_name: str, message: str, tool_context: Any):
        """Send message to remote agent.
        
        Args:
            agent_name: The name of the agent to send the task to.
            message: The message to send to the agent for the task.
            tool_context: The tool context this method runs in.

        Returns:
            Response from agent
        """
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        
        state = tool_context.state
        state["agent"] = agent_name
        client = self.remote_agent_connections[agent_name]

        # Prepare the A2A message Part based on the LLM's instruction
        part = TextPart(text=message)
        messageId = state.get("message_id", None)
        taskId = state.get("task_id")
        if message == 'send_signed_payment_object':
            taskId = None
        if not messageId:
            messageId = str(uuid.uuid4())
        request = MessageSendParams(
            id=messageId,
            message=Message(
                role="user",
                parts=[part],
                messageId=messageId,
                contextId=state.get("context_id"),
                taskId=taskId,
            ),
            configuration=MessageSendConfiguration(
                acceptedOutputModes=["text", "text/plain", "image/png"],
            ),
        )

        return await client.send_message(
            messageId,
            request=request
        )

    async def process_payment(
        self,
        payment_requirements: str,
        tool_context: Any = None
    ) -> Dict[str, Any]:
        """Process a payment request by signing the authorization.
        
        Args:
            payment_requirements: JSON string containing payment requirements
            tool_context: Optional tool context
            
        Returns:
            Dictionary containing:
            - status: 'success' or 'error'
            - message: Description of what happened
            - data: Payment data if successful
        """
        try:
            print(f"[host_agent] Processing payment requirements: {payment_requirements}")
            
            # Parse the requirements message
            if isinstance(payment_requirements, str):
                requirements_message = X402A2AMessage[PaymentRequired].model_validate_json(payment_requirements)
            else:
                requirements_message = X402A2AMessage[PaymentRequired].model_validate(payment_requirements)
            
            print(f"[host_agent] Parsed requirements message: {requirements_message}")
            
            # Process the payment
            result = await process_payment(requirements_message, self.account, self.max_value, self.config.scheme)
            print(f"[host_agent] Got payment result: {result}")
            
            # Skip LLM summarization since this is structured data
            if tool_context:
                tool_context.actions.skip_summarization = True
            
            # Return simplified result
            return {
                "status": "success",
                "message": "Payment processed successfully",
                "data": result.model_dump()
            }
        except Exception as e:
            print(f"[host_agent] Error processing payment: {e}")
            return {
                "status": "error",
                "message": str(e),
                "data": None
            }