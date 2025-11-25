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
import httpx
from payments_py.payments import Payments
from payments_py.common.types import PaymentOptions

# Local imports
from client_agent._task_store import TaskStore
from client_agent.client_agent import ClientAgent

# Initialize Payments instance for client (subscriber)
nvm_api_key_client = os.getenv("NVM_API_KEY_CLIENT")
if not nvm_api_key_client:
    raise ValueError(
        "NVM_API_KEY_CLIENT environment variable is required. "
        "This should be the subscriber's API key with permissions to generate access tokens. "
        "Get your API key from https://nevermined.io/dashboard"
    )

environment = os.getenv("NVM_ENVIRONMENT", "sandbox")
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key=nvm_api_key_client,
        environment=environment
    )
)

print(f"✅ Client Agent initialized for '{environment}' environment")
print(f"   Using subscriber API key for access token generation")

root_agent = ClientAgent(
    remote_agent_addresses=[
        "http://localhost:10000/agents/merchant_agent",
    ],
    http_client=httpx.AsyncClient(timeout=30),
    payments=payments,
    task_callback=TaskStore().update_task,
).create_agent()
