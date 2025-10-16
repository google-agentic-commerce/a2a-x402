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

# Local imports
from client_agent._task_store import TaskStore
from client_agent.client_agent import ClientAgent

root_agent = ClientAgent(
    remote_agent_addresses=[
        "http://localhost:10000/agents/merchant_agent",
    ],
    http_client=httpx.AsyncClient(timeout=30),
    task_callback=TaskStore().update_task,
).create_agent()
