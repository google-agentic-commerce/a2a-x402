import os
from typing import Dict, List
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from google.adk.agents import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import BaseRoute, Route

# Local imports
from ._adk_agent_executor import ADKAgentExecutor
from .merchant_agent import LowesMerchantAgent

# x402 imports
from a2a_x402.executors import X402ServerExecutor
from a2a_x402.types import X402ExtensionConfig, X402ServerConfig

# Load environment variables
load_dotenv()

# Required environment variables
MERCHANT_ADDRESS = os.getenv("MERCHANT_ADDRESS")
if not MERCHANT_ADDRESS:
    raise ValueError("MERCHANT_ADDRESS environment variable required")

# Optional environment variables with defaults
NETWORK = os.getenv("NETWORK", "base-sepolia")

# Initialize merchant agent
AGENTS: Dict[str, LowesMerchantAgent] = {
    "lowes_merchant_agent": LowesMerchantAgent(
        merchant_address=MERCHANT_ADDRESS,
        network=NETWORK
    ),
}

def create_agent_routes(base_url: str, base_path: str) -> List[BaseRoute]:
    """Creates routes for all registered agents.

    Args:
        base_url: Base URL for the application (e.g. "http://localhost:10000")
        base_path: Base path for the routes (e.g. "/agents")

    Returns:
        List of routes for all registered agents
    """
    # Verify an API key is set.
    # Not required if using Vertex AI APIs.
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") != "TRUE" and not os.getenv(
        "GOOGLE_API_KEY"
    ):
        raise ValueError(
            "GOOGLE_API_KEY environment variable not set and "
            "GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
        )

    routes: List[BaseRoute] = []

    for path, agent in AGENTS.items():
        full_path = f"{base_path}/{path}"
        url = f"{base_url}{full_path}"
        routes.extend(
            _create_routes(
                full_path,
                agent.create_agent_card(url),
                agent.create_agent(),
                InMemoryArtifactService(),
                InMemorySessionService(),
                InMemoryMemoryService(),
            ),
        )

    return routes

def _create_routes(
    full_path: str,
    agent_card: AgentCard,
    agent: LlmAgent,
    artifact_service: InMemoryArtifactService,
    session_service: InMemorySessionService,
    memory_service: InMemoryMemoryService,
) -> List[Route]:
    from google.adk.runners import Runner

    runner = Runner(
        app_name=agent_card.name,
        agent=agent,
        artifact_service=artifact_service,
        session_service=session_service,
        memory_service=memory_service,
    )
    
    # Create base ADK executor
    adk_executor = ADKAgentExecutor(runner, agent_card)
    
    # Wrap with X402ServerExecutor for proper payment handling
    agent_executor = X402ServerExecutor(
        delegate=adk_executor,
        config=X402ExtensionConfig(),
        server_config=X402ServerConfig(
            price="0.05",  # Default price for demo products
            pay_to_address=MERCHANT_ADDRESS,
            network=NETWORK,
            description="AI assistant service payment"
        )
    )

    async def handle_auth(request: Request) -> PlainTextResponse:
        await agent_executor.on_auth_callback(
            request.query_params.get("state"), str(request.url)
        )
        return PlainTextResponse("Authentication successful.")

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    routes = a2a_app.routes(
        agent_card_url=f"{full_path}/.well-known/agent-card.json", rpc_url=full_path
    )
    routes.append(
        Route(
            path=f"{full_path}/authenticate",
            methods=["GET"],
            endpoint=handle_auth,
        )
    )
    return routes
