# x402 × A2A Solution Guide: Enabling Agent Commerce

A comprehensive guide to building monetized AI agents using the x402 payment protocol extension for the Agent-to-Agent (A2A) protocol.

## Table of Contents
1. [Introduction](#introduction)
2. [Core Concepts](#core-concepts)
3. [How It Works](#how-it-works)
4. [Implementation Approaches](#implementation-approaches)
5. [Getting Started with the Google ADK Demo](#getting-started-with-the-google-adk-demo)
6. [Architecture Patterns](#architecture-patterns)
7. [Building Your Own Monetized Agent](#building-your-own-monetized-agent)
8. [Resources & Next Steps](#resources--next-steps) 

## Introduction

### What is A2A?

The [Agent-to-Agent (A2A) protocol](https://a2a-protocol.org/) is an open standard that enables AI agents to communicate, collaborate, and solve problems together. It provides:

- Standardized communication between different AI agents
- Task orchestration and delegation capabilities
- Skill discovery and capability sharing
- Extension system for additional functionality

### What is x402?

[x402](https://x402.gitbook.io/x402) is an open payment protocol developed by Coinbase that revives the HTTP 402 "Payment Required" status code. It enables instant, programmatic stablecoin payments directly over HTTP—no accounts, API keys, or complex authentication required.

### The x402 × A2A Extension

The x402 extension for A2A introduces open financial rails, enabling agents to:
- **Monetize their services** through onchain payments
- **Purchase capabilities** from other agents
- **Build autonomous economic relationships**
- **Create value networks** of specialized agents

## Core Concepts

1. **Client Agent**: Acts on behalf of a user, orchestrating interactions and handling payments
2. **Merchant Agent**: Provides monetized services and processes payment requests
3. **Payment Flow**: A structured exchange of payment requirements, authorization, and settlement
4. **Facilitator**: Handles payment verification and on-chain settlement
5. **Wallet**: Manages cryptographic signing of payment authorizations

> **Note:** An agent can act as both client and merchant in different contexts. For example, an agent might purchase data from one service (acting as client) and then sell processed results to another (acting as merchant).

### Payment States

The x402 extension tracks payment lifecycle through these states:
- `payment-required`: Service requires payment
- `payment-submitted`: Client has sent payment authorization
- `payment-verified`: Payment has been validated
- `payment-completed`: Transaction settled on-chain
- `payment-failed`: Payment could not be processed
- `payment-rejected`: Client declined payment terms

## How It Works

### The Payment Flow

![x402 Payment Flow Diagram](Flow%20Diagram.png)


### Integration with A2A

The x402 extension integrates with A2A's task-based architecture:

1. **Service Request**: Client agent sends a standard A2A message
2. **Payment Required**: Merchant responds with a Task in `input-required` state containing payment terms
3. **Payment Authorization**: Client submits payment in message metadata
4. **Service Delivery**: Merchant completes the Task with results and payment receipt

## Implementation Approaches

The x402 extension provides two levels of implementation to match your needs:

### High-Level: Using Executors (Recommended)

Perfect for getting started quickly with built-in best practices.

```python
from a2a_x402 import X402ServerExecutor, X402ClientExecutor, X402ExtensionConfig

# Server-side: Wrap your agent with payment handling
payment_executor = X402ServerExecutor(
    base_executor=your_agent_executor,
    x402_config=X402ExtensionConfig()
)

# Client-side: Automatic payment handling for requests
client_executor = X402ClientExecutor(
    wallet=user_wallet,
    auto_approve=False  # Prompt user for payment confirmation
)
```

**Benefits:**
- Handles all protocol complexity automatically
- Built-in error handling and state management
- Production-ready with minimal configuration

### Low-Level: Using Core Components

For advanced use cases requiring custom payment flows.

```python
from a2a_x402 import X402Utils, PaymentRequirements
from a2a_x402.core import create_payment_requirements, verify_payment

# Build your own payment logic using core utilities
utils = X402Utils()
requirements = create_payment_requirements(
    price="1000000",  # $1.00 in USDC
    pay_to_address="0xYourAddress",
    description="Custom service"
)
```

**When to use:**
- Custom payment approval workflows
- Integration with existing payment systems
- Non-standard payment schemes

## Applications & Use Cases

### For AI Agents

- **Autonomous Service Purchasing**: Agents can discover and pay for capabilities they need
- **Self-Improvement**: Purchase new tools and skills from specialized agents
- **Task Delegation**: Pay other agents to handle specific subtasks
- **Resource Access**: Buy compute, data, or API access on-demand

## Getting Started with the Google ADK Demo

The Google ADK (Agent Development Kit) demo showcases a complete payment flow between two agents. Here's how to run it:

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Step 1: Clone and Setup

```bash
# Clone the repository
git clone https://github.com/google-agentic-commerce/a2a-x402.git
cd a2a-x402

# Install dependencies using uv
uv sync --directory=examples/python/adk-demo
```

### Step 2: Start the Merchant Server

The merchant server hosts the agent that sells products and processes payments.

```bash
# From the repository root
uv --directory=examples/python/adk-demo run adk web
```

You should see output indicating the server is running on `localhost:10000`.

### Step 3: Launch the Client Interface

In a new terminal, start the client agent with its web UI:

```bash
# Navigate to the demo directory
cd examples/python/adk-demo

# Start the client server
uv run --active server
```

This launches the ADK web interface on `localhost:8000`.

### Step 4: Test the Payment Flow

1. Open `http://localhost:8000` in your browser
2. Interact with the client agent through the chat interface
3. Try purchasing an item (e.g., "I want to buy a laptop")
4. Observe the payment flow:
   - Merchant provides price and payment requirements
   - Client prompts for payment confirmation
   - Payment is processed and settled
   - Purchase confirmation is displayed

## Architecture Patterns

### Clean Separation of Concerns

The x402 extension promotes clean architecture through separation of business logic from payment handling:

#### Merchant Side Architecture

```python
# Core business logic (AdkMerchantAgent)
def get_product_details_and_request_payment(self, product_name: str):
    # Calculate price and prepare payment requirements as defined in x402 spec
    requirements = PaymentRequirements(
        scheme="exact",
        network="base-sepolia",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e", # USDC
        pay_to=self._wallet_address,
        max_amount_required=price,
        description=f"service description",
        resource=f"link to resource",
        mime_type="application/json",
        max_timeout_seconds=1200,
        extra={"additional information, if helpful"},
        )
    )
    
    # Signal payment needed - no payment logic here!
    raise X402PaymentRequiredException(product_name, requirements)

# Payment handling wrapper (X402ServerExecutor)
# Intercepts the exception and handles all protocol logic:
# - Creates payment-required response
# - Verifies client signatures
# - Settles payments on-chain
```

#### Client Side Architecture

```python
# Clean client implementation with payment handling
class ClientAgent:
    def __init__(self, wallet: Wallet):
        self.wallet = wallet  # Injected wallet for signing
    
    async def handle_payment_required(self, task_id: str, requirements: dict):
        """Orchestrates the payment flow when service requires payment"""
        
        # 1. Present payment terms to user
        print(f"Payment required: ${requirements['amount']} for {requirements['description']}")
        
        # 2. Get user confirmation
        if not await self.get_user_confirmation():
            return await self.send_payment_rejected(task_id)
        
        # 3. Sign payment with injected wallet
        payment_payload = self.wallet.sign_payment(requirements)
        
        # 4. Submit payment to merchant
        return await self.send_message({
            "taskId": task_id,
            "metadata": {
                "x402.payment.status": "payment-submitted",
                "x402.payment.payload": payment_payload
            }
        })
```

### Pluggable Components

#### Facilitator Integration

The facilitator handles payment verification and settlement, abstracting blockchain complexity. You can use the same faciliator object you would for HTTP requests in Python:

```python

from cdp.x402 import create_facilitator_config
from x402.types import VerifyResponse, SettleResponse

facilitator_config = create_facilitator_config(CDP_API_KEY_ID, CDP_API_KEY_SECRET) 
```



#### Wallet Abstraction

The wallet interface enables flexible payment signing strategies:

```python
# Standard wallet interface
from typing import Protocol
from a2a_x402 import PaymentPayload, x402PaymentRequiredResponse

class Wallet(Protocol):
    """Interface for payment signing implementations"""
    def sign_payment(self, requirements: x402PaymentRequiredResponse) -> PaymentPayload:
        """Signs payment requirements to create authorized payload"""
        pass

# Example: Development wallet with local key
class MockLocalWallet(Wallet):
    def sign_payment(self, requirements: x402PaymentRequiredResponse) -> PaymentPayload:
        # FOR DEMO ONLY - uses hardcoded key
        private_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        account = eth_account.Account.from_key(private_key)
        
        payment_option = requirements.accepts[0]
        
        # Create message to sign (simplified for demo)
        message = f"Chain ID: {payment_option.network}\n..."
        signature = account.sign_message(encode_defunct(text=message))
        
        return PaymentPayload(
            x402Version=1,
            scheme=payment_option.scheme,
            network=payment_option.network,
            payload={
                "authorization": {
                    "from": account.address,
                    "to": payment_option.pay_to,
                    "value": payment_option.max_amount_required,
                    # ... other fields
                },
                "signature": signature.signature.hex()
            }
        )
```

## Building Your Own Monetized Agent

### Step 1: Define Your Agent's Value

```python
class MySpecializedAgent(BaseAgent):
    def my_valuable_service(self, input_data: str) -> dict:
        # Determine if payment is needed
        if self.requires_payment(input_data):
            requirements = PaymentRequirements(
                scheme="exact",
                network="base-sepolia",
                asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # USDC
                pay_to=self.wallet_address,
                max_amount_required="1000000",  # $1.00 in USDC
                description="Specialized data processing"
            )
            raise X402PaymentRequiredException(input_data, requirements)
        
        # Process the request
        return {"result": "processed_data"}
```

### Step 2: Wrap with Payment Executor

```python
# Create a concrete executor that connects to your facilitator
class X402MerchantExecutor(X402ServerExecutor):
    def __init__(self, delegate, facilitator_client):
        super().__init__(delegate, X402ExtensionConfig())
        self._facilitator = facilitator_client
    
    async def verify_payment(self, payload, requirements):
        return await self._facilitator.verify(payload, requirements)
    
    async def settle_payment(self, payload, requirements):
        return await self._facilitator.settle(payload, requirements)

# In your routes setup
base_executor = ADKAgentExecutor(runner, agent_card)
facilitator = MockFacilitator()  # or real facilitator TODO how do I replace with the real facilitator here 
agent_executor = X402MerchantExecutor(base_executor, facilitator)
```

### Step 3: Configure Your Agent Card

```python
def create_agent_card(self, url: str) -> AgentCard:
    return AgentCard(
        name="My Specialized Agent",
        description="Provides valuable data processing services",
        url=url,
        capabilities=AgentCapabilities(
            extensions=[
                get_extension_declaration(
                    description="Supports x402 payments",
                    required=True
                )
            ]
        ),
        skills=[AgentSkill(
            id="process_data",
            name="Data Processing",
            description="Advanced data transformation with payment"
        )]
    )
```

### Step 4: Test and Deploy

1. Test with facilitator on testnet
2. Integrate on mainnet
3. Deploy your agent
4. Register in agent directories for discovery

## Resources & Next Steps

### Documentation

- **[A2A Protocol Specification](https://a2a-protocol.org/latest/specification)** - Core agent communication protocol
- **[x402 Extension Spec](https://github.com/google-agentic-commerce/a2a-x402/blob/main/v0.1/spec.md)** - Complete technical specification
- **[Python Library](https://github.com/google-agentic-commerce/a2a-x402/tree/main/python/a2a_x402)** - Core x402 implementation for Python

### Examples & Code

- **[ADK Demo Source](https://github.com/google-agentic-commerce/a2a-x402/tree/main/examples/python/adk-demo)** - Complete example implementation
- **[Other Examples](https://github.com/google-agentic-commerce/a2a-x402/tree/main/examples)** - Additional language implementations

### Getting Help

- **Discord**: Join the [CDP Discord](https://discord.gg/cdp) for community support
- **GitHub Issues**: Report bugs or request features in the [repository](https://github.com/google-agentic-commerce/a2a-x402)
- **Contributing**: Read the [contribution guidelines](https://github.com/google-agentic-commerce/a2a-x402/blob/main/CONTRIBUTING.md)