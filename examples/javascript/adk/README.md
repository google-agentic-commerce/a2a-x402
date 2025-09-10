## A2A x402 JavaScript Example

Minimal merchant/client example using the official A2A JS SDK with the x402 payments extension. Fully functional: client signs an EIP‑3009 authorization; server verifies and settles on-chain.

### What it does

- Server (merchant):
  - Advertises the x402 extension in its AgentCard.
  - On first message: returns a Task with `input-required` and `x402.payment.required` (payment terms).
  - On payment submission: verifies EIP‑712 signature, publishes `payment-pending`, calls `transferWithAuthorization`, then publishes `payment-completed` and appends to `x402.payment.receipts`.
- Client (buyer):
  - Fetches AgentCard, sends a message, receives payment terms, signs EIP‑3009 using a wallet, and submits `x402.payment.payload` with the original `taskId`.

### Prerequisites

- Node.js 18+

### Install

```bash
cd examples/javascript/adk
npm install
```

### Configure

Set these as environment variables (or in a local `.env` and export before running):

- RPC_URL: JSON‑RPC endpoint for your network (Base / Base Sepolia)
- MERCHANT_PRIVATE_KEY: merchant signer (submits settlement)
- CLIENT_PRIVATE_KEY: client signer (signs EIP‑3009)
- ASSET_ADDRESS: token contract (USDC) for your network
- X402_NETWORK: "base" or "base-sepolia" (placed in payment requirements)
- PRICE_USDC: human-readable price (e.g., `1` or `1.50`)
- PRICE_ATOMIC (optional): exact smallest-units string; overrides PRICE_USDC
- MAX_TIMEOUT_SECONDS (optional): default `600`

Notes:
- Merchant address is derived from `MERCHANT_PRIVATE_KEY`.
- Token decimals are read from the `ASSET_ADDRESS` at runtime.
- The server includes a precise EIP‑712 domain in `accepts[0].extra.domain`; the client uses it for signing.

### Run

1) Start the merchant server
```bash
npm run server
# http://localhost:10000
# AgentCard: http://localhost:10000/.well-known/agent-card.json
```

2) Run the client
```bash
npm run client
```

Expected client output (example):
- `Created Task: <id> input-required`
- `After payment submission, task state: completed`
- `Payment status: payment-completed`
- A receipt object with transaction hash and payer

### Verify a transaction’s logs

```bash
# Optional filter: export ASSET_ADDRESS=<token>
npm run verify -- <txHash>
```
Prints network, method (e.g., `transferWithAuthorization`), decoded args, and token Transfer/Authorization events.

### Files

- server.js: merchant A2A server + x402 settlement (EIP‑3009)
- client.js: buyer that signs EIP‑712/EIP‑3009 and submits the payload
- verify.js: helper to decode ERC‑20 Transfer and EIP‑3009 events
- package.json: scripts (`server`, `client`, `verify`)

### Spec compliance

- Activation header: server echoes `X-A2A-Extensions`, client attaches it to all requests.
- Metadata keys per spec: `x402.payment.status`, `x402.payment.required`, `x402.payment.payload`, `x402.payment.receipts`.

### Reference

- A2A JS SDK (official): [https://github.com/a2aproject/a2a-js](https://github.com/a2aproject/a2a-js)
- x402 extension spec: `v0.1/spec.md`
