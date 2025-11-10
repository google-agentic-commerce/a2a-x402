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
import httpx
from urllib.parse import urlparse
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from client_agent.client_agent import ClientAgent

# The addresses of the remote agents this agent will talk to.
REMOTE_AGENT_ADDRESSES = [
    "http://localhost:10000/agents/merchant_agent",
]

# Create an httpx client to be shared across all remote agents.
async_client = httpx.AsyncClient(timeout=30)


# Create RemoteA2aAgent instances for each remote agent.
remote_agents = []
for address in REMOTE_AGENT_ADDRESSES:
    # The server exposes the agent card at a path relative to the agent's RPC endpoint.
    agent_card_url = f"{address}/.well-known/agent-card.json"
    agent_name = address.split("/")[-1]
    remote_agents.append(
        RemoteA2aAgent(
            name=agent_name,
            agent_card=agent_card_url,
            httpx_client=async_client,
        )
    )

# Create the main orchestrator agent, passing the remote agents as tools.
client_agent_impl = ClientAgent(
    remote_agents=remote_agents,
    http_client=async_client,
)
root_agent = client_agent_impl.create_agent()
