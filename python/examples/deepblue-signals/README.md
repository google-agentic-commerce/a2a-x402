# DeepBlue Signals — A2A x402 Demo

This project demonstrates a real-world, end-to-end payment flow where one agent **pays another agent per trading signal** using the **A2A x402 Payment Protocol Extension**.

A **Client Agent** asks the **DeepBlue Signal Agent** for a 5-minute directional trading signal (UP/DOWN) for BTC, ETH, SOL, or XRP. The signal merchant charges **$0.002 USDC per signal** via x402, verifies the payment, then fetches and delivers the live signal from the [DeepBlue autonomous trading bot](https://deepbluebase.xyz).

Signal source: **https://api.deepbluebase.xyz** — a live Polymarket trading bot that uses real-time Binance websocket data and 6 technical indicators (RSI, tick momentum, orderbook imbalance, aggressor ratio, volume spike, ROC) to generate high-frequency directional signals.

## Architecture

```
┌─────────────────────────────────┐      A2A x402      ┌──────────────────────────────────────┐
│         Client Agent            │ ─────────────────► │      DeepBlue Signal Agent           │
│  (orchestrator, ADK web UI)     │                     │  (merchant server, port 10001)       │
│                                 │ ◄───────────────── │                                      │
│  • Discovers signal_agent       │  payment-required   │  • get_trading_signal(coin) tool     │
│  • Asks user for coin           │                     │    raises x402PaymentRequiredException│
│  • Confirms payment (~$0.002)   │  ────────────────►  │  • x402MerchantExecutor verifies     │
│  • Signs via MockLocalWallet    │  payment-submitted  │    and settles payment               │
│  • Presents signal to user      │ ◄────────────────── │  • Fetches signal from               │
└─────────────────────────────────┘  signal delivered   │    api.deepbluebase.xyz              │
                                                        └──────────────────────────────────────┘
```

The core x402 protocol logic is provided by the `x402_a2a` library (located at `python/x402_a2a/` in the repository root). This example follows the same pattern as `python/examples/adk-demo` — the only unique file is `server/agents/signal_agent.py`.

## How to Run the Demo

### Prerequisites
- Python 3.13+
- `uv` (for environment and package management)
- Google API key — get one at https://ai.google.dev/gemini-api/docs/api-key

### 1. Set Up the Environment

Sync the virtual environment from the repository root:

```bash
uv sync --directory=python/examples/deepblue-signals
```

Copy the example environment file and fill in your values:

```bash
cp python/examples/deepblue-signals/.env.example python/examples/deepblue-signals/.env
```

Set your Google API key:

**Linux/macOS:**
```bash
export GOOGLE_API_KEY="your_api_key_here"
```

**Windows (PowerShell):**
```powershell
$env:GOOGLE_API_KEY="your_api_key_here"
```

### 2. Start the Signal Merchant Server

Run this from the repository root. The server starts on `localhost:10001`.

```bash
uv --directory=python/examples/deepblue-signals run server
```

You should see:
```
/agents/signal_agent/.well-known/agent-card.json
INFO:     Started server process
INFO:     Uvicorn running on http://localhost:10001
```

### 3. Start the Client Agent Web UI

Run this from the repository root in a separate terminal:

```bash
uv --directory=python/examples/deepblue-signals run adk web --port=8000
```

Open http://localhost:8000 in your browser and select the `client_agent`.

### 4. Try the Payment Demo

In the ADK web UI, try prompts like:

- `"Get me a BTC signal"`
- `"What's the ETH 5-minute signal?"`
- `"Should I go long or short SOL?"`

The client agent will:
1. Discover the DeepBlue Signal Agent
2. Request the signal (triggering the x402 payment flow)
3. Present the payment amount (~$0.002 USDC) and ask for confirmation
4. On confirmation, sign and submit the payment
5. Deliver the live signal: direction (UP/DOWN), confidence score, and context

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google Gemini API key |
| `CLIENT_PRIVATE_KEY` | No | EVM private key for signing payments (defaults to zero-balance test key) |
| `MERCHANT_WALLET_ADDRESS` | No | USDC recipient address on Base Sepolia (defaults to DeepBlue wallet) |
| `USE_MOCK_FACILITATOR` | No | `true` (default) bypasses real facilitator for local dev |
| `DEEPBLUE_API_URL` | No | Signal API base URL (default: `https://api.deepbluebase.xyz`) |

## Signal API

The merchant fetches signals from:

```
GET https://api.deepbluebase.xyz/signals?coin=BTC
```

Response format:
```json
{
  "coin": "BTC",
  "direction": "UP",
  "confidence": 0.67,
  "regime": "trending",
  "generated_at": "2025-04-20T09:00:00Z"
}
```

Supported coins: `BTC`, `ETH`, `SOL`, `XRP`

The API is served by the DeepBlue autonomous trading system — a live Polymarket bot that trades 5-minute BTC/ETH/SOL/XRP up/down markets using real-time Binance websocket data.

## Payment Details

| Field | Value |
|-------|-------|
| Protocol | x402 A2A (exact scheme) |
| Network | Base Sepolia (testnet) |
| Asset | USDC (`0x036CbD53842c5426634e7929541eC2318f3dCF7e`) |
| Price | 2000 atomic units = $0.002 USDC |
| Recipient | DeepBlue wallet (configurable via `MERCHANT_WALLET_ADDRESS`) |

## File Structure

```
deepblue-signals/
├── README.md
├── pyproject.toml
├── .env.example
├── server/
│   ├── __init__.py
│   ├── __main__.py               # Uvicorn entry point (port 10001)
│   └── agents/
│       ├── __init__.py
│       ├── routes.py             # Registers signal_agent with A2A routing
│       ├── signal_agent.py       # THE unique file: DeepBlueSignalAgent
│       ├── x402_executor.py      # x402MerchantExecutor (payment verification)
│       ├── mock_facilitator.py   # Mock facilitator for local dev
│       ├── base_agent.py         # Abstract BaseAgent interface
│       └── _adk_agent_executor.py  # ADK runner → A2A bridge
└── client_agent/
    ├── __init__.py
    ├── agent.py                  # root_agent (points to localhost:10001)
    ├── client_agent.py           # Orchestrator with x402 payment flow
    ├── wallet.py                 # MockLocalWallet (EIP-3009 signer)
    ├── _task_store.py            # In-memory task state manager
    └── _remote_agent_connection.py  # A2A client wrapper
```

## Key Design Decisions

**Payment before data**: `get_trading_signal()` always raises `x402PaymentRequiredException` — the signal is never returned without payment. The `x402MerchantExecutor` wrapper intercepts this exception, manages the full payment handshake, then injects the verified payment result into the session.

**Live data after payment**: `before_agent_callback` in `DeepBlueSignalAgent` fires after payment verification. It fetches the signal from `api.deepbluebase.xyz` and injects it as a virtual tool response, so the LLM presents the real signal without asking for payment again.

**Graceful fallback**: If the DeepBlue API is unreachable, `_fetch_signal()` returns a structured error dict rather than crashing. The agent can still complete the task and inform the user.

## About DeepBlue

[DeepBlue](https://deepbluebase.xyz) is a 5-agent autonomous Discord trading system that trades Polymarket prediction markets. Its signal engine uses:

- Real-time Binance websocket feed (BTC/ETH/SOL/XRP ticks + orderbook)
- 6 technical indicators: tick momentum, orderbook imbalance, aggressor ratio, RSI, volume spike, ROC
- Epoch-based 5-minute market discovery on Polymarket Gamma API
- Circuit breaker after 4 consecutive losses (30-minute pause)

This demo is a working example of how an autonomous agent can monetize its data outputs via A2A x402 micropayments.
