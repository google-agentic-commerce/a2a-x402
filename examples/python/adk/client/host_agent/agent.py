import os
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .host_agent import HostAgent

# Get wallet private key from environment
private_key = os.getenv("WALLET_PRIVATE_KEY")
if not private_key:
    raise ValueError("WALLET_PRIVATE_KEY environment variable required")

# Get network from environment
network = os.getenv("NETWORK", "sui-testnet")

# Get max payment value from environment (default: 1B base units)
max_value = os.getenv("WALLET_MAX_VALUE", "1000000000")
max_value = int(max_value)

# Create HTTP client for remote agent communication with increased timeout
http_client = httpx.AsyncClient(timeout=60.0)

# Create host agent with both wallet and orchestration capabilities
root_agent = HostAgent(
    private_key=private_key,
    network=network,
    max_value=max_value,
    remote_agent_addresses=[
        "http://localhost:10000/agents/lowes_merchant_agent",  # Merchant agent
    ],
    http_client=http_client,
).create_agent()
