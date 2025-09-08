import httpx

# Local imports
from client_agent._task_store import TaskStore
from client_agent.client_agent import ClientAgent
from client_agent.wallet import MockLocalWallet

root_agent = ClientAgent(
    remote_agent_addresses=[
        "http://localhost:10000/agents/merchant_agent",
    ],
    http_client=httpx.AsyncClient(timeout=30),
    wallet=MockLocalWallet(),
    task_callback=TaskStore().update_task,
).create_agent()
