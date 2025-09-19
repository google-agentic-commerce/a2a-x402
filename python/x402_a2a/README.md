# x402 A2A Payment Protocol Extension

This package implements the x402 payment protocol extension for Agent-to-Agent (A2A) runtimes. It focuses on dynamic, exception-based payment requirements so agents can request payment at the exact moment it is needed while keeping business logic separate from payment orchestration.

## Quick Start

Run these commands from `python/x402_a2a/` to install the library in editable mode and execute the test suite:

```bash
python -m venv .venv
source .venv/bin/activate  # or use your preferred environment manager
pip install -e ".[dev]"
pytest
```

## Key Concepts

- Agents raise `x402PaymentRequiredException` when a task needs payment, and the executors translate those exceptions into protocol-compliant messages.
- The core package exposes low-level helpers for creating payment requirements, signing payloads, and verifying settlement, while the executors wrap those helpers for client and merchant hosts.
- All public types live under `x402_a2a.types`, mirroring the specification so integrators work with structured objects instead of manual dictionaries.

## Library Layout

`x402_a2a` follows a functional-core/imperative-shell design: the protocol math lives in `core/`, high-level adapters in `executors/`, and domain types plus exceptions in `types/`.

```
x402_a2a/
├── core/                # Protocol logic and orchestrators
│   ├── agent.py
│   ├── helpers.py
│   ├── merchant.py
│   ├── protocol.py
│   ├── utils.py
│   └── wallet.py
├── executors/           # Optional middleware bridges
│   ├── base.py
│   ├── client.py
│   └── server.py
├── types/               # Public types and configuration
│   ├── config.py
│   ├── errors.py
│   └── state.py
├── tests/               # Regression suite
│   └── test_core.py
├── extension.py
└── __init__.py
```

## Example Components

The full sample implementation lives under `examples/python/adk-demo/`. These quick descriptions highlight where to look for the main entry points:

- [`examples/python/adk-demo/client_agent/client_agent.py`](https://github.com/a2aproject/a2a-x402/blob/main/examples/python/adk-demo/client_agent/client_agent.py): Drives the interactive client flow, relaying payment-required messages to the wallet and submitting signed payloads back to the merchant.
- [`examples/python/adk-demo/server/agents/adk_merchant_agent.py`](https://github.com/a2aproject/a2a-x402/blob/main/examples/python/adk-demo/server/agents/adk_merchant_agent.py): Implements the merchant-facing business logic that decides when a payment is required and what is being sold.
- [`examples/python/adk-demo/server/agents/x402_merchant_executor.py`](https://github.com/a2aproject/a2a-x402/blob/main/examples/python/adk-demo/server/agents/x402_merchant_executor.py): Wraps the merchant agent with the server executor so x402 exceptions turn into payment-required tasks while providing the facilitator-backed verify and settle hooks.
- [`examples/python/adk-demo/server/agents/routes.py`](https://github.com/a2aproject/a2a-x402/blob/main/examples/python/adk-demo/server/agents/routes.py): Wires the merchant executor into the web server and exposes the endpoints that ADK calls during the payment flow.
- [`python/x402_a2a/types/config.py`](https://github.com/a2aproject/a2a-x402/blob/main/python/x402_a2a/types/config.py): Houses the extension and server configuration models (extension URI/version flags plus price, receiver, network, and timeout settings).

## Further Reading

- [Specification](https://github.com/a2aproject/a2a-x402/blob/main/v0.1/spec.md) — canonical x402 A2A protocol definition.
- [A2A Protocol](https://github.com/a2aproject/a2a-python) — base agent runtime used by the examples.
- [Contributing](https://github.com/google-agentic-commerce/a2a-x402/blob/main/CONTRIBUTING.md)
- [License](https://github.com/google-agentic-commerce/a2a-x402/blob/main/LICENSE)
