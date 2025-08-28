"""A2A routing configuration with x402 payment middleware."""

import os
from typing import List
from starlette.routing import BaseRoute

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

# Import from the refactored a2a_x402 package
from a2a_x402 import X402ExtensionConfig
from a2a_x402.executors import X402ServerExecutor
from x402.facilitator import FacilitatorClient

from .merchant_agent import MerchantAgent, create_merchant_agent_card
from ._adk_agent_executor import AdkAgentExecutor


def create_router() -> List[BaseRoute]:
    """Create A2A routes with payment-enabled merchant agents."""
    
    # Create merchant agent (ADK executor)
    merchant_agent = MerchantAgent()
    
    # Wrap ADK executor for A2A compatibility  
    adk_wrapper = AdkAgentExecutor(merchant_agent)
    
    # Create x402 configuration
    x402_config = X402ExtensionConfig()
    
    # Create facilitator client (optional - will use default if not provided)
    facilitator_client = None
    facilitator_url = os.getenv('FACILITATOR_URL')
    if facilitator_url:
        facilitator_client = FacilitatorClient({"url": facilitator_url})
    
    # Wrap with X402ServerExecutor for automatic payment handling
    payment_enabled_agent = X402ServerExecutor(
        delegate=adk_wrapper,
        config=x402_config,
        facilitator_client=facilitator_client
    )
    
    # Create agent card
    agent_card = create_merchant_agent_card()
    
    # Create request handler and task store
    request_handler = DefaultRequestHandler(
        agent_executor=payment_enabled_agent,
        task_store=InMemoryTaskStore()
    )
    
    # Create A2A Starlette application
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    
    # Return routes for the merchant agent
    return a2a_app.routes(
        agent_card_url="/market-intelligence/.well-known/agent.json",
        rpc_url="/market-intelligence"
    )