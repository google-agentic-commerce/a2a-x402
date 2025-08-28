"""Remote agent connection."""
import json
import uuid
from typing import Any, Dict, List, Optional, Union
import httpx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    AgentSkill,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    TextPart,
    SendMessageRequest,
    JSONRPCErrorResponse,
    SendStreamingMessageRequest,
)
from google.adk.tools.tool_context import ToolContext

from a2a_x402.types import X402ExtensionConfig
from a2a_x402.extension import get_extension_declaration

class RemoteAgentConnection:
    """Remote agent connection."""

    def __init__(self, client: httpx.AsyncClient, agent_card: AgentCard):
        """Initialize remote agent connection.

        Args:
            client: HTTP client
            agent_card: Agent card
        """
        self.agent_client = A2AClient(client, agent_card)
        self.card = agent_card

    def _prepare_outbound_part(self, message: str) -> Part:
        """Prepare outbound message part.

        Args:
            message: Message text

        Returns:
            Message part
        """
        return TextPart(text=message)

    def _prepare_outbound_message(self, message: str) -> Message:
        """Prepare outbound message.

        Args:
            message: Message text

        Returns:
            Message object
        """
        return Message(
            id=str(uuid.uuid4()),
            parts=[self._prepare_outbound_part(message)]
        )

    async def send_message(
        self,
        id: str,
        request: MessageSendParams,
        task_callback: Any = None,
    ) -> Message | None:
        """Send message to remote agent.

        Args:
            id: Message ID
            request: Message request parameters
            task_callback: Optional task callback

        Returns:
            Message response or None
        """
        print(f"[remote_agent] Sending message: {request}")
        try:
            # Prefer non-streaming mode to avoid connection issues
            response = await self.agent_client.send_message(
                SendMessageRequest(id=id, params=request)
            )
            print(f"[remote_agent] Got response: {response}")

            if isinstance(response.root, JSONRPCErrorResponse):
                print("[remote_agent] Got error response")
                return response.root.error

            if isinstance(response.root.result, Message):
                print("[remote_agent] Got message response")
                return response.root.result

            # Check for task artifacts in the response
            if response.root.result:
                print(f"[remote_agent] Got result: {response.root.result}")
                if hasattr(response.root.result, 'artifacts'):
                    print(f"[remote_agent] Has artifacts: {response.root.result.artifacts}")
                    if response.root.result.artifacts and len(response.root.result.artifacts) > 0:
                        print(f"[remote_agent] First artifact: {response.root.result.artifacts[0]}")
                        if hasattr(response.root.result.artifacts[0], 'parts'):
                            print(f"[remote_agent] First artifact parts: {response.root.result.artifacts[0].parts}")
                            if len(response.root.result.artifacts[0].parts) > 0:
                                print(f"[remote_agent] First part root: {response.root.result.artifacts[0].parts[0].root}")
                                if hasattr(response.root.result.artifacts[0].parts[0].root, 'data'):
                                    return response.root.result.artifacts[0].parts[0].root.data

            if task_callback:
                task_callback(response.root.result)
            return response.root.result

        except Exception as e:
            print(f"[remote_agent] Error sending message: {e}")
            raise

    def create_agent_card(self, url: str, name: str, description: str) -> AgentCard:
        """Creates the AgentCard metadata for discovery.

        Args:
            url: Base URL for this agent
            name: Agent name
            description: Agent description

        Returns:
            Agent card
        """
        config = X402ExtensionConfig()
        extension_declaration = get_extension_declaration(config)

        skills = [
            # Wallet capability
            AgentSkill(
                id="process_payment",
                name="Process Payment",
                description="Process x402 payment requirements",
                tags=["x402", "payment", "wallet"]
            ),

            # Orchestration capabilities
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
            )
        ]

        from a2a.types import AgentCapabilities

        return AgentCard(
            name=name,
            description=description,
            url=url,
            version="1.0.0",
            skills=skills,
            capabilities=AgentCapabilities(skills=skills),
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            extensions=[extension_declaration] if extension_declaration else []
        )
