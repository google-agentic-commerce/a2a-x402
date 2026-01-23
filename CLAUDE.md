# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository implements the **A2A x402 Extension** using Nevermined (https://nevermined.ai/docs), which brings cryptocurrency payments to the Agent-to-Agent (A2A) protocol using Nevermined blockchain integration. The extension enables agents to monetize their services through on-chain payments, implementing the HTTP 402 "Payment Required" pattern for decentralized agent commerce.

### Key Components

- **`python/x402_a2a/`**: Core library implementing the x402 payment protocol extension for A2A
  - `core/`: Protocol implementation (payment creation, signing, verification, settlement)
  - `executors/`: Optional middleware for client/server integration
  - `types/`: Protocol data structures, errors, and configuration

- **`python/examples/adk-demo/`**: Production-ready demonstration using Google's ADK and Nevermined
  - `server/`: Merchant agent that requires payment for services
  - `client_agent/`: Client agent that pays for services
  - `utils/`: Helper scripts for payment plan creation and agent configuration

- **`spec/v0.1/`**: Official x402 extension specification
- **`schemes/`**: Experimental payment schemes from partners

## Architecture

The library follows a **"functional core, imperative shell"** architecture:

1. **Core Protocol** (`core/`): Pure functions for payment lifecycle (create, sign, verify, settle)
2. **Executors** (`executors/`): Middleware that automates payment flow integration into agents
3. **Exception-Based Payment Requirements**: Uses `x402PaymentRequiredException` for dynamic payment requests rather than static configuration

Payment flow: `payment-required` → `payment-submitted` → `payment-completed`

## Development Commands

### Setting Up the Environment

```bash
# Install dependencies for the core library
uv sync --directory=python/x402_a2a

# Install dependencies for the ADK demo
uv sync --directory=python/examples/adk-demo
```

### Running the ADK Demo

The demo demonstrates complete end-to-end payment flow with real blockchain transactions.

```bash
# Run the merchant agent (in one terminal)
uv --directory=python/examples/adk-demo run server

# 4. Run the client agent (in another terminal)
uv --directory=python/examples/adk-demo run adk web --port=8000

# 5. Open browser to http://localhost:8000
```

### Running Tests

1. Open a brower and navigate to `http://localhost:8000/dev-ui/?app=client_agent` to interact with the client agent's web interface. The `client_agent` must be selected.
2. In the message input, type a query that requires payment, such as "I want to purchase a laptop."
3. Wait until the merchant returns the payment required message with the payment options
4. Select the payment option and confirm the payment (1 or 2)
5. Wait until the payment is processed and the merchant returns the completed response with the requested service.
6. Validate the transaction returned by the merchant is correct.



### Utility Scripts

```bash
# Create a pay-as-you-go payment plan
uv --directory=python/examples/adk-demo run create-payasyougo-plan

# Attach a payment plan to an agent
uv --directory=python/examples/adk-demo run attach-plan-to-agent
```

## Environment Configuration

The ADK demo requires configuration in `.env` (see `.env.sample` for template):

**Required:**
- `NVM_API_KEY_SERVER`: Nevermined API key for merchant (verify/settle permissions)
- `NVM_API_KEY_CLIENT`: Nevermined API key for client (access token generation)
- `NVM_ENVIRONMENT`: `sandbox` (testnet) or `production`
- `NVM_CREDITS_PLAN_ID`: Payment plan ID representing the Nevermined that gives credits when it's purchased
- `NVM_PAYASYOUGO_PLAN_ID`: Payment plan ID representing the Nevermined pay-as-you-go plan
- `NVM_AGENT_ID`: AI Agent ID from Nevermined
- `GOOGLE_API_KEY`: Google Generative AI API key

**Optional:**
- `LLM_MODEL`: Override to use OpenAI instead of Gemini (e.g., `gpt-4o`)
- `OPENAI_API_KEY`: Required if using OpenAI
- `LLM_PROVIDER`: Set to `openai` when using OpenAI

**IMPORTANT**: All transactions are REAL blockchain transactions. Credits are burned on-chain. Never commit `.env` with real credentials.

## Python Version Requirements

- **Core library (`python/x402_a2a`)**: Python >= 3.11
- **ADK Demo**: Python >= 3.13

## Dependency Management

This project uses `uv` for dependency management with editable local packages during development:

- The ADK demo uses an editable install of `x402_a2a` via `[tool.uv.sources]`
- The `x402` package is installed from GitHub branch `v2-development` (will migrate to PyPI when v2 releases)
- For local development of `payments-py`, uncomment the editable path in `pyproject.toml`

## Key Dependencies

- **a2a-sdk**: Core A2A protocol implementation
- **x402**: x402 payment protocol (from GitHub v2-development branch)
- **payments-py**: Nevermined payments SDK with x402 module
- **google-adk**: Google's Agent Development Kit (demo only)
- **eth-account**: Ethereum account management and signing
- **httpx**: Async HTTP client
- **web3**: Web3 blockchain interactions

## CI/CD

GitHub Actions workflows in `.github/workflows/`:

- `python-x402-a2a.yml`: Lints and formats the core library on PRs and main branch pushes
- `python-examples-adk-demo.yml`: Tests the ADK demo
- `public_pypi_x402_a2a.yml`: Publishes the library to PyPI
- `conventional-commits.yml`: Validates commit message format
- `release-please.yml`: Automates releases

## Payment Protocol Integration

When building agents with x402 payments:

1. **Import key types and functions** from `x402_a2a`:
   - `x402PaymentRequiredException`: Exception to trigger payment requirements
   - `X402A2AUtils`: State management utilities
   - `NeverminedFacilitator`: Payment verification and settlement
   - Core functions: `create_payment_requirements`, `verify_payment`, `settle_payment`

2. **Exception-based approach**: Throw `x402PaymentRequiredException` when payment is needed:
   ```python
   raise x402PaymentRequiredException.for_service(
       price="$5.00",
       pay_to_address="0x123...",
       resource="/premium-feature"
   )
   ```

3. **Use executors for automation**: Server and client executors handle the payment flow middleware

4. **All payments are on-chain**: The demo uses real blockchain transactions via Nevermined

## Branch Strategy

- **Main branch**: `main`
- **Feature branch**: `feat/a2a-nvm` (this is the main branch for PRs in this project)
- Always sync feature branches with `main` before creating PRs
