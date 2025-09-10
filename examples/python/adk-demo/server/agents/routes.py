import os
from typing import Dict, List

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
from a2a_x402 import FacilitatorClient, X402ExtensionConfig

# --- Local Imports ---

# The base ADK executor that runs the agent
from ._adk_agent_executor import ADKAgentExecutor

# The abstract agent factory class
from .base_agent import BaseAgent

# The concrete agent factories
from .adk_merchant_agent import AdkMerchantAgent
from .eigenda_agent import EigenDAAgent

# The concrete x402 executor wrappers
from .x402_merchant_executor import X402MerchantExecutor
from .mock_facilitator import MockFacilitator
from .real_facilitator import RealFacilitator


# A dictionary mapping the URL path to the agent factory
AGENTS: Dict[str, BaseAgent] = {
    # "merchant_agent": AdkMerchantAgent(),  # Commented out - focusing on EigenDA
    "eigenda_agent": EigenDAAgent(),
}


def create_agent_routes(base_url: str, base_path: str) -> List[BaseRoute]:
    """
    Creates and configures the routes for all registered agents.
    """
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") != "TRUE" and not os.getenv(
        "GOOGLE_API_KEY"
    ):
        raise ValueError("GOOGLE_API_KEY environment variable not set.")

    routes: List[BaseRoute] = []

    for path, agent_factory in AGENTS.items():
        full_path = f"{base_path}/{path}"
        url = f"{base_url}{full_path}"
        routes.extend(
            _create_routes(
                path,  # Pass the agent's path for wrapper selection
                full_path,
                agent_factory.create_agent_card(url),
                agent_factory.create_agent(),
                InMemoryArtifactService(),
                InMemorySessionService(),
                InMemoryMemoryService(),
            ),
        )

    return routes


def _create_routes(
    agent_path: str,
    full_path: str,
    agent_card: AgentCard,
    agent: LlmAgent,
    artifact_service: InMemoryArtifactService,
    session_service: InMemorySessionService,
    memory_service: InMemoryMemoryService,
) -> List[Route]:
    """
    Creates the routes for a single agent, applying the correct x402 wrapper.
    """
    from google.adk.runners import Runner

    runner = Runner(
        app_name=agent_card.name,
        agent=agent,
        artifact_service=artifact_service,
        session_service=session_service,
        memory_service=memory_service,
    )
    
    # 1. Create the base executor that runs the ADK agent.
    agent_executor = ADKAgentExecutor(runner, agent_card)

    # 2. Select the facilitator based on an environment variable.
    use_mock = os.getenv("USE_MOCK_FACILITATOR", "true").lower() == "true"
    if use_mock:
        print("--- Using Mock Facilitator ---")
        facilitator = MockFacilitator()
    else:
        print("--- Using REAL Facilitator ---")
        # Check if merchant private key is configured
        if not os.getenv("MERCHANT_PRIVATE_KEY"):
            raise ValueError(
                "MERCHANT_PRIVATE_KEY must be set in .env when USE_MOCK_FACILITATOR=false. "
                "This key is needed to execute on-chain transfers."
            )
        facilitator = RealFacilitator()

    # 3. Apply the concrete x402 merchant wrapper.
    agent_executor = X402MerchantExecutor(agent_executor, facilitator)

    # 3. Create the request handler with the final, fully wrapped executor.
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    # 4. Create the A2A application and its routes.
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    agent_json_address = full_path + "/.well-known/agent-card.json"
    print(f"{agent_json_address}")
    return a2a_app.routes(
        agent_card_url=agent_json_address, rpc_url=full_path
    )
