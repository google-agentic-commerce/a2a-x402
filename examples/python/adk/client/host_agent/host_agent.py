"""Host agent with X402ClientExecutor for automatic payment processing."""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from eth_account import Account
from a2a.types import Message, Task, RequestContext, EventQueue

# Import from the refactored a2a_x402 package
from a2a_x402 import (
    X402ExtensionConfig,
    PaymentStatus,
    X402Utils,
    get_extension_declaration
)
from a2a_x402.executors import X402ClientExecutor

from ._remote_agent_connection import RemoteAgentConnection


class BusinessClientAgent:
    """Business logic client agent that makes requests to remote services."""
    
    def __init__(self, remote_connection: RemoteAgentConnection):
        """Initialize the business client agent.
        
        Args:
            remote_connection: Connection to remote A2A agents
        """
        self.remote_connection = remote_connection
        self.utils = X402Utils()
    
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Execute business logic - make requests to remote services."""
        
        # Extract messages from context
        messages = getattr(context, 'messages', [])
        if not messages:
            return
        
        # Process each message
        for message in messages:
            # Send message to remote market intelligence agent
            task = await self.remote_connection.send_message_to_agent(
                agent_path="market-intelligence",
                message=message,
                context_id=getattr(context, 'context_id', None)
            )
            
            if task:
                # Store task in context for payment processing
                setattr(context, 'current_task', task)
                await event_queue.enqueue_event(task)


class PaymentEnabledHostAgent:
    """Host agent with automatic x402 payment capabilities."""
    
    def __init__(self):
        """Initialize the host agent with payment capabilities."""
        self._load_environment()
        self._setup_payment_config()
        self._setup_remote_connection()
        self._setup_executors()
    
    def _load_environment(self):
        """Load environment variables from .env file if it exists."""
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        if key not in os.environ:
                            os.environ[key] = value
    
    def _setup_payment_config(self):
        """Setup payment configuration from environment."""
        # Validate required environment variables
        self.private_key = os.getenv('WALLET_PRIVATE_KEY')
        if not self.private_key:
            raise ValueError("WALLET_PRIVATE_KEY environment variable is required")
        
        # Create account from private key
        self.account = Account.from_key(self.private_key)
        
        # Get maximum payment amount
        max_value_str = os.getenv('WALLET_MAX_VALUE', '10000000')  # Default 10 USDC
        try:
            self.max_value = int(max_value_str)
        except ValueError:
            raise ValueError(f"Invalid WALLET_MAX_VALUE: {max_value_str}")
        
        # Create x402 configuration
        self.config = X402ExtensionConfig()
        
        print(f"🔐 Payment wallet initialized:")
        print(f"   Address: {self.account.address}")
        print(f"   Max payment: {self.max_value} atomic units")
    
    def _setup_remote_connection(self):
        """Setup connection to remote agents."""
        server_url = os.getenv('REMOTE_AGENT_URL', 'http://localhost:10000')
        self.remote_connection = RemoteAgentConnection(server_url)
    
    def _setup_executors(self):
        """Setup business agent and payment executor."""
        # Create business logic agent
        self.business_agent = BusinessClientAgent(self.remote_connection)
        
        # Wrap with X402ClientExecutor for automatic payment processing
        self.executor = X402ClientExecutor(
            delegate=self.business_agent,
            config=self.config,
            account=self.account,
            max_value=self.max_value,
            auto_pay=True  # Automatically process payments
        )
    
    async def execute(self, messages: List[Message]) -> List[Message]:
        """Execute messages through the payment-enabled executor."""
        responses = []
        
        for message in messages:
            try:
                # Create minimal context for executor
                context = RequestContext()
                setattr(context, 'messages', [message])
                setattr(context, 'context_id', f"host-{id(message)}")
                
                # Add x402 extension headers
                setattr(context, 'headers', {
                    "X-A2A-Extensions": "https://github.com/google-a2a/a2a-x402/v0.1"
                })
                
                # Create event queue to collect responses
                event_queue = EventQueue()
                collected_events = []
                
                # Mock event queue to collect events
                async def mock_enqueue(event):
                    collected_events.append(event)
                
                event_queue.enqueue_event = mock_enqueue
                
                # Execute through payment executor
                await self.executor.execute(context, event_queue)
                
                # Convert collected events to response messages
                for event in collected_events:
                    if isinstance(event, Task):
                        responses.extend(self._task_to_messages(event))
                    elif isinstance(event, Message):
                        responses.append(event)
                
            except Exception as e:
                # Create error response
                error_message = Message(
                    messageId=f"error-{message.messageId}",
                    role="agent",
                    parts=[{"kind": "text", "text": f"Error processing request: {str(e)}"}]
                )
                responses.append(error_message)
        
        return responses
    
    def _task_to_messages(self, task: Task) -> List[Message]:
        """Convert task to response messages."""
        messages = []
        
        # Check if task has a status message
        if hasattr(task, 'status') and task.status and hasattr(task.status, 'message') and task.status.message:
            status_message = task.status.message
            
            # Check payment status
            payment_status = self.utils.get_payment_status(task)
            
            if payment_status == PaymentStatus.PAYMENT_REQUIRED:
                # Payment required - inform user
                payment_message = Message(
                    messageId=f"payment-required-{task.id}",
                    role="agent",
                    parts=[{"kind": "text", "text": "💳 Payment processing in progress... Please wait while I handle the payment automatically."}]
                )
                messages.append(payment_message)
                
            elif payment_status == PaymentStatus.PAYMENT_COMPLETED:
                # Payment completed - show service result
                completion_message = Message(
                    messageId=f"service-delivered-{task.id}",
                    role="agent", 
                    parts=[{"kind": "text", "text": "✅ Payment successful! Here's your requested service:"}]
                )
                messages.append(completion_message)
                messages.append(status_message)
                
            elif payment_status == PaymentStatus.PAYMENT_FAILED:
                # Payment failed
                failure_message = Message(
                    messageId=f"payment-failed-{task.id}",
                    role="agent",
                    parts=[{"kind": "text", "text": "❌ Payment failed. Please check your wallet balance and try again."}]
                )
                messages.append(failure_message)
                
            else:
                # No payment required or other status
                messages.append(status_message)
        
        # Include any artifacts as additional messages
        if hasattr(task, 'artifacts') and task.artifacts:
            for artifact in task.artifacts:
                artifact_message = Message(
                    messageId=f"artifact-{task.id}-{len(messages)}",
                    role="agent",
                    parts=[{"kind": "text", "text": f"📎 {artifact}"}]
                )
                messages.append(artifact_message)
        
        return messages
    
    async def close(self):
        """Cleanup resources."""
        if hasattr(self, 'remote_connection'):
            await self.remote_connection.close()
    
    def get_extensions(self) -> List[Dict[str, Any]]:
        """Get extension declarations for the agent card."""
        return [get_extension_declaration()]