"""Remote agent connection utilities for A2A communication."""

import os
import httpx
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from a2a.types import Message, Task


class RemoteAgentConnection:
    """Manages connections to remote A2A agents with x402 payment support."""
    
    def __init__(self, base_url: str = None):
        """Initialize connection to remote agents.
        
        Args:
            base_url: Base URL of the remote agent server (default: localhost:10000)
        """
        self.base_url = base_url or "http://localhost:10000"
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # x402 extension headers
        self.default_headers = {
            "X-A2A-Extensions": "https://github.com/google-a2a/a2a-x402/v0.1",
            "Content-Type": "application/json"
        }
    
    async def discover_agents(self) -> List[Dict[str, Any]]:
        """Discover available agents on the remote server."""
        try:
            response = await self.client.get(
                urljoin(self.base_url, "/agents"),
                headers=self.default_headers
            )
            response.raise_for_status()
            return response.json().get("agents", [])
        except Exception as e:
            print(f"Failed to discover agents: {e}")
            return []
    
    async def send_message_to_agent(
        self, 
        agent_path: str, 
        message: Message,
        context_id: Optional[str] = None
    ) -> Optional[Task]:
        """Send a message to a specific remote agent.
        
        Args:
            agent_path: Path to the remote agent (e.g., "market-intelligence")
            message: Message to send
            context_id: Optional context ID for conversation tracking
            
        Returns:
            Task response from the remote agent, or None if failed
        """
        try:
            # Prepare request payload
            payload = {
                "contextId": context_id or f"client-{os.getpid()}",
                "message": message.model_dump(by_alias=True)
            }
            
            # Send message to agent
            response = await self.client.post(
                urljoin(self.base_url, f"/agents/{agent_path}/message"),
                json=payload,
                headers=self.default_headers
            )
            response.raise_for_status()
            
            # Parse response as Task
            task_data = response.json()
            return Task.model_validate(task_data)
            
        except Exception as e:
            print(f"Failed to send message to agent {agent_path}: {e}")
            return None
    
    async def submit_payment(
        self,
        agent_path: str,
        task_id: str,
        payment_payload: Dict[str, Any],
        context_id: Optional[str] = None
    ) -> Optional[Task]:
        """Submit payment authorization to a remote agent.
        
        Args:
            agent_path: Path to the remote agent
            task_id: ID of the task requiring payment
            payment_payload: Signed payment payload
            context_id: Optional context ID
            
        Returns:
            Updated task after payment submission
        """
        try:
            # Create payment submission message
            payment_message = Message(
                messageId=f"payment-{task_id}",
                role="user",
                parts=[{"kind": "text", "text": "Payment authorization provided"}],
                metadata={
                    "x402.payment.status": "payment-submitted",
                    "x402.payment.payload": payment_payload
                }
            )
            
            # Send payment message with task correlation
            payload = {
                "contextId": context_id or f"client-{os.getpid()}",
                "taskId": task_id,  # Critical for correlation
                "message": payment_message.model_dump(by_alias=True)
            }
            
            response = await self.client.post(
                urljoin(self.base_url, f"/agents/{agent_path}/payment"),
                json=payload,
                headers=self.default_headers
            )
            response.raise_for_status()
            
            # Parse response as Task
            task_data = response.json()
            return Task.model_validate(task_data)
            
        except Exception as e:
            print(f"Failed to submit payment for task {task_id}: {e}")
            return None
    
    async def close(self):
        """Close the HTTP client connection."""
        await self.client.aclose()