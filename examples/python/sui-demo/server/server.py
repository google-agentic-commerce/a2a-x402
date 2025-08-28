#!/usr/bin/env python3
"""
A2A server with X402 payment integration.
"""

import os
import uvicorn
from typing import List
from starlette.applications import Starlette
from starlette.routing import BaseRoute, Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

# X402 imports
from a2a_x402.executors import X402ServerExecutor
from a2a_x402.types import X402ExtensionConfig, X402ServerConfig
from x402.facilitator import FacilitatorClient

from merchant_base import (
    MerchantExecutor, MerchantAgent, create_merchant_card,
    MerchantX402Executor
)
from merchants import MERCHANTS

# Load environment
load_dotenv()

# Get configuration from environment
MERCHANT_ADDRESS = os.getenv("MERCHANT_ADDRESS")
NETWORK = os.getenv("NETWORK", "sui-testnet")
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://x402-facilitator-sui.vercel.app")
DEFAULT_PRICE = os.getenv("DEFAULT_PRICE", "0.05")


def _create_routes(
    route_path: str,
    resource_url: str,
    agent_card,
    base_agent_executor,
    merchant_name: str
) -> List[Route]:
    """Create routes with X402 payment integration."""

    facilitator_client = None
    if FACILITATOR_URL:
        from a2a_x402.types import FacilitatorConfig
        facilitator_config = FacilitatorConfig(url=FACILITATOR_URL)
        facilitator_client = FacilitatorClient(facilitator_config)

    x402_executor = MerchantX402Executor(
        base_merchant_executor=base_agent_executor,
        config=X402ExtensionConfig(),
        server_config=X402ServerConfig(
            price=DEFAULT_PRICE,
            pay_to_address=MERCHANT_ADDRESS,
            network=NETWORK,
            description=f"Purchase from {merchant_name}",
            resource=resource_url
        ),
        facilitator_client=facilitator_client
    )

    request_handler = DefaultRequestHandler(
        agent_executor=x402_executor,
        task_store=InMemoryTaskStore()
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )

    routes = a2a_app.routes(
        agent_card_url=f"{route_path}/.well-known/agent-card.json",
        rpc_url=route_path
    )

    return routes


def create_merchant_routes(base_url: str, base_path: str) -> List[BaseRoute]:
    """Dynamically create A2A routes for all configured merchants."""

    routes: List[BaseRoute] = []

    # Dynamically create routes for each merchant in the configuration
    for merchant_id, config in MERCHANTS.items():
        merchant_path = f"{base_path}/{merchant_id}"
        merchant_url = f"{base_url}{merchant_path}"

        # Create agent, executor, and card for this merchant
        agent = MerchantAgent(config)
        executor = MerchantExecutor(agent)
        card = create_merchant_card(merchant_id, config, merchant_url)

        # Add routes for this merchant
        routes.extend(_create_routes(
            merchant_path,
            merchant_url,
            card,
            executor,
            config.name
        ))

    return routes


def main():
    """Start the working A2A server."""
    host = "0.0.0.0"
    port = int(os.getenv("MERCHANT_PORT", "8001"))
    base_url = f"http://{host}:{port}"
    base_path = "/agents"

    routes = create_merchant_routes(base_url, base_path)

    app = Starlette(routes=routes)

    print(f"🏪 Starting A2A server with X402 payments on {base_url}")
    print(f"💰 Merchant Address: {MERCHANT_ADDRESS}")
    print(f"🌐 Network: {NETWORK}")
    print(f"💵 Price per purchase: {DEFAULT_PRICE} SUI")
    print()

    # Dynamically print available merchants
    for merchant_id, config in MERCHANTS.items():
        merchant_url = f"{base_url}/agents/{merchant_id}"
        print(f"🏪 {config.name}: {merchant_url}")
        print(f"🃏 Agent card: {merchant_url}/.well-known/agent-card.json")

    print()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
