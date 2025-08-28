"""ADK Agent Executor wrapper for A2A integration."""

from typing import List, Optional

from a2a.types import Message
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.agent_execution import AgentExecutor


class AdkAgentExecutor(AgentExecutor):
    """Wrapper to make business agents compatible with A2A RequestContext and EventQueue."""
    
    def __init__(self, business_agent):
        """Initialize with a business agent.
        
        Args:
            business_agent: The business agent to wrap
        """
        self.business_agent = business_agent
    
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Execute the business agent in A2A context.
        
        Args:
            context: A2A request context containing messages and metadata
            event_queue: Event queue for publishing task updates
        """
        # Extract message from context
        message = context.message
        if not message:
            # No message to process
            return
        
        # Execute business agent with the message
        response_messages = await self.business_agent.execute([message])
        
        # Enqueue response messages as events
        for response_message in response_messages:
            await event_queue.enqueue_event(response_message)
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """Cancel execution (not implemented)."""
        pass