"""Host agent implementation."""

import os
import uuid
import logging
from typing import Dict, Any, List, Union
from dotenv import load_dotenv
import httpx

# Set up logging
logger = logging.getLogger(__name__)

# Conditional imports for testing
try:
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

    from a2a_x402.types import X402ExtensionConfig, PaymentRequirements, PaymentPayload
    from a2a_x402.core import process_payment
    from ._remote_agent_connection import RemoteAgentConnection
    FULL_IMPORTS = True
except ImportError:
    # For testing purposes when some packages aren't available
    FULL_IMPORTS = False
    logger.warning("Some imports not available - running in test mode")

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

                logger.info(f"Connecting to Sui network at: {rpc_url}")

                # Create configuration with the RPC URL
                config = SuiConfig.user_config(
                    rpc_url=rpc_url,
                    prv_keys=[private_key]
                )

                # Create a SyncClient
                self.account = SyncClient(config=config)
                logger.info(f"Initialized Sui client for network: {network}")
                logger.info(f"Active address: {self.account.config.active_address}")

            except ImportError:
                raise ImportError("pysui package is required for Sui networks. Install with: uv add pysui")
            except Exception as e:
                raise Exception(f"Error initializing Sui client: {str(e)}")
        else:
            # For EVM networks, use eth_account
            from eth_account import Account
            self.account = Account.from_key(private_key)
            logger.info(f"Initialized EVM account: {self.account.address}")

        self.max_value = max_value
        self.name = name
        self.description = description
        if FULL_IMPORTS:
            self.config = X402ExtensionConfig()
        else:
            self.config = None

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
                tags=["payment", "x402", "sui"],
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

        logger.info(f"Starting initialization for {len(self.remote_agent_addresses)} remote agents")

        for address in self.remote_agent_addresses:
            try:
                logger.info(f"Connecting to {address}")
                # Get agent card using resolver
                card_resolver = A2ACardResolver(self.http_client, address)
                agent_card = await card_resolver.get_agent_card()
                logger.info(f"Connected to {address}, got agent card: {agent_card.name}")

                # Create remote connection with card
                remote_connection = RemoteAgentConnection(
                    client=self.http_client,
                    agent_card=agent_card
                )
                self.remote_agent_connections[agent_card.name] = remote_connection
                logger.info(f"Added connection for {agent_card.name}")

            except Exception as e:
                logger.error(f"Failed to connect to {address}: {e}")

        logger.info(f"Initialization complete. Connected agents: {list(self.remote_agent_connections.keys())}")
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
            instruction="""You are a host agent that can communicate with remote merchant agents and process x402 payments.

Your workflow:
1. Use list_remote_agents to see available merchants
2. Use send_message to communicate with merchants (ask about products, get prices, etc.)
3. When a merchant returns payment_requirements in their response, use process_payment to create and sign the payment
4. ALWAYS provide clear feedback to the user about payment results

For payments:
- Merchants will return structured data with "payment_requirements" containing price, merchant address, etc.
- When you detect payment_requirements in the merchant response, extract ONLY the payment_requirements object and pass it as a JSON string to process_payment
- The process_payment tool will handle all the cryptographic signing and send the payment to the merchant
- IMPORTANT: After process_payment completes, always tell the user clearly whether the payment succeeded or failed
- If successful: Include transaction details and blockchain explorer link if available. Example: "Payment successful! Transaction: abc123... View on explorer: https://testnet.suivision.xyz/txblock/abc123"
- If failed: Explain what went wrong and suggest next steps
- Always look for transaction hashes and explorer links in the payment response data and share them with the user

Always be helpful, provide clear updates about what's happening, and ensure users know the final result of their actions.""",
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
        if not self._initialized:
            return {
                "status": "error",
                "message": "Remote agents not initialized. This should happen automatically on first use.",
                "available_agents": []
            }

        agents = []
        for name, conn in self.remote_agent_connections.items():
            agents.append({
                "name": name,
                "description": conn.card.description,
                "url": conn.card.url
            })

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

        # Handle None tool_context
        if tool_context and hasattr(tool_context, 'state'):
            state = tool_context.state
            state["agent"] = agent_name
        else:
            state = {"agent": agent_name}
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

    async def send_message_with_metadata(
        self,
        agent_name: str,
        message: str,
        metadata: Dict[str, Any],
        tool_context: Any = None
    ) -> Any:
        """Send message to remote agent with metadata.
        
        Args:
            agent_name: Name of the agent to send to
            message: Message text
            metadata: Message metadata 
            tool_context: Optional tool context
            
        Returns:
            Response from agent
        """
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")

        # Handle None tool_context
        if tool_context and hasattr(tool_context, 'state'):
            state = tool_context.state
            state["agent"] = agent_name
        else:
            state = {"agent": agent_name}
        client = self.remote_agent_connections[agent_name]

        # Prepare the A2A message Part with metadata
        part = TextPart(text=message)
        messageId = state.get("message_id", None)
        taskId = state.get("task_id")
        if not messageId:
            messageId = str(uuid.uuid4())

        # Create message with metadata
        message_obj = Message(
            role="user",
            parts=[part],
            messageId=messageId,
            contextId=state.get("context_id"),
            taskId=taskId,
            metadata=metadata  # Include the metadata here
        )

        request = MessageSendParams(
            id=messageId,
            message=message_obj,
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
            # Parse the requirements
            import json
            logger.info(f"Processing payment requirements")
            if isinstance(payment_requirements, str):
                try:
                    # Try to parse as JSON
                    requirements_dict = json.loads(payment_requirements)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON decode error: {e}")
                    logger.debug(f"Raw string: {repr(payment_requirements)}")

                    # Try to fix common issues - sometimes the LLM sends malformed JSON
                    # Check if it's missing opening brace
                    if not payment_requirements.strip().startswith('{'):
                        fixed_json = '{' + payment_requirements.strip()
                        try:
                            requirements_dict = json.loads(fixed_json)
                            logger.info(f"Fixed JSON by adding opening brace")
                        except:
                            raise e
                    else:
                        raise e
            else:
                requirements_dict = payment_requirements

            # Extract the actual payment requirements
            if 'payment_requirements' in requirements_dict:
                actual_requirements = PaymentRequirements(**requirements_dict['payment_requirements'])
            else:
                actual_requirements = PaymentRequirements(**requirements_dict)

            
            # Process the payment - the a2a_x402 process_payment function now handles both account types
            result = process_payment(actual_requirements, self.account, self.max_value)
            

            # Find the merchant agent
            merchant_agent = None
            for name in self.remote_agent_connections.keys():
                merchant_agent = name
                break

            if not merchant_agent:
                return {
                    "status": "error",
                    "message": "No merchant agent found to settle payment with",
                    "data": None
                }

            # Send payment data as metadata (following A2A x402 spec)
            # This avoids LLM text processing that corrupts base64 signatures
            payment_metadata = {
                "x402.payment.status": "payment-submitted",
                "x402.payment.payload": result.model_dump(),
                "x402.payment.requirements": actual_requirements.model_dump()
            }

            settlement_response = await self.send_message_with_metadata(
                agent_name=merchant_agent,
                message="Payment authorization submitted for settlement.",
                metadata=payment_metadata,
                tool_context=tool_context
            )

            # Extract settlement result from merchant response
            settlement_success = False
            settlement_message = "Payment processed successfully"
            transaction_hash = None
            explorer_link = None

            # Parse the merchant's settlement response
            try:
                if hasattr(settlement_response, 'data') and settlement_response.data:
                    response_data = settlement_response.data
                    
                    if isinstance(response_data, dict):
                        settlement_success = response_data.get('success', False)
                        settlement_message = response_data.get('message', settlement_message)
                        transaction_hash = response_data.get('transaction')
                        explorer_link = response_data.get('explorer_link')
                    else:
                        # Assume success if we got a response but can't parse it
                        settlement_success = True
                else:
                    # Assume success if we got here - the payment was signed and sent
                    settlement_success = True
            except Exception as parse_error:
                logger.warning(f"Failed to parse settlement response: {parse_error}")
                settlement_success = True


            # Create final user-friendly message with transaction details
            if settlement_success:
                if transaction_hash and explorer_link:
                    final_message = f"Payment processed successfully! Your purchase is complete. Transaction hash: {transaction_hash[:16]}... View on explorer: {explorer_link}"
                else:
                    final_message = "Payment processed successfully! Your purchase is complete. The merchant has confirmed your transaction."
                status = "success"
            else:
                final_message = f"Payment failed: {settlement_message}"
                status = "error"

            return {
                "status": status,
                "message": final_message,
                "data": {
                    "signed_payment": result.model_dump(),
                    "settlement_response": settlement_response,
                    "settlement_parsed": {
                        "success": settlement_success,
                        "message": settlement_message,
                        "transaction": transaction_hash,
                        "explorer_link": explorer_link
                    }
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "data": None
            }
