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
from x402_a2a import FacilitatorClient, x402ExtensionConfig

# --- Local Imports ---

# The base ADK executor that runs the agent
from ._adk_agent_executor import ADKAgentExecutor

# The abstract agent factory class
from .base_agent import BaseAgent

# The concrete agent factories
from .adk_merchant_agent import AdkMerchantAgent

# The concrete x402 executor wrappers
from .x402_merchant_executor import x402MerchantExecutor
from .mock_facilitator import MockFacilitator


# A dictionary mapping the URL path to the agent factory
AGENTS: Dict[str, BaseAgent] = {
    "merchant_agent": AdkMerchantAgent(),
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

    # 2. Apply the concrete x402 merchant wrapper.
    agent_executor = x402MerchantExecutor(agent_executor)

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