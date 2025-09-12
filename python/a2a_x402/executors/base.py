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
"""Base executor types and interfaces for x402 payment middleware."""

from abc import ABC, abstractmethod
from typing import Optional

from ..types import (
    AgentExecutor,
    RequestContext,
    EventQueue,
    x402ExtensionConfig,
    X402_EXTENSION_URI
)
from ..core.utils import x402Utils

class x402BaseExecutor(ABC):
    """Base executor with x402 protocol support."""
    
    def __init__(
        self,
        delegate: AgentExecutor,
        config: x402ExtensionConfig
    ):
        """Initialize base executor.
        
        Args:
            delegate: The underlying agent executor to wrap
            config: x402 extension configuration
        """
        self._delegate = delegate
        self.config = config
        self.utils = x402Utils()

    def is_active(self, context: RequestContext) -> bool:
        """Check if x402 extension is activated for this request.
        
        Args:
            context: Request context containing headers and request info
            
        Returns:
            True if x402 extension should be active
        """

        headers = getattr(context, 'headers', {})
        if isinstance(headers, dict):
            extensions_header = headers.get("X-A2A-Extensions", "")
            if X402_EXTENSION_URI in extensions_header:
                return True

        return False

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
