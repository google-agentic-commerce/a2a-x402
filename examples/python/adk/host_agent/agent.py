import os
import httpx

from .host_agent import HostAgent

# Get wallet private key from environment
private_key = os.getenv("WALLET_PRIVATE_KEY")
if not private_key:
    raise ValueError("WALLET_PRIVATE_KEY environment variable required")

# Get max payment value from environment (default: 1B base units = $1000 for 6-decimal tokens)
max_value = os.getenv("WALLET_MAX_VALUE", "1000000000")
max_value = int(max_value)

# Create HTTP client for remote agent communication
http_client = httpx.AsyncClient()

# Create host agent with both wallet and orchestration capabilities
root_agent = HostAgent(
    private_key=private_key,
    max_value=max_value,
    remote_agent_addresses=[
        "http://localhost:10000/agents/lowes_merchant_agent",  # Merchant agent
    ],
    http_client=http_client,
).create_agent()
