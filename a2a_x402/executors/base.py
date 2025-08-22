"""Base executor types and interfaces for x402 payment middleware."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..types import (
    X402ExtensionConfig,
    X402_EXTENSION_URI
)
from ..core.utils import X402Utils


# Generic types for A2A integration
AgentExecutor = Any
RequestContext = Any  
EventQueue = Any


class X402BaseExecutor(ABC):
    """Base executor with x402 protocol support."""
    
    def __init__(
        self,
        delegate: AgentExecutor,
        config: X402ExtensionConfig
    ):
        """Initialize base executor.
        
        Args:
            delegate: The underlying agent executor to wrap
            config: x402 extension configuration
        """
        self._delegate = delegate
        self.config = config
        self.utils = X402Utils()

    def is_active(self, context: RequestContext) -> bool:
        """Check if x402 extension is activated for this request.
        
        Args:
            context: Request context containing headers and request info
            
        Returns:
            True if x402 extension should be active
        """
        # Check if extension is requested via headers
        headers = getattr(context, 'headers', {})
        if isinstance(headers, dict):
            extensions_header = headers.get("X-A2A-Extensions", "")
            if X402_EXTENSION_URI in extensions_header:
                return True
        
        # Fallback: active if extension is required
        return self.config.required

    @abstractmethod
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ):
        """Execute the agent with x402 payment middleware.
        
        Args:
            context: Request context
            event_queue: Event queue for task updates
        """
        ...