# SUI x402 A2A Demo

A demo showing A2A-compliant agents with **X402 payment integration** on SUI blockchain, using Google ADK for the UI.

## Features

✅ **A2A Protocol Compliance**: Proper agent discovery and communication  
✅ **X402 Payment Integration**: On-chain payment requirements for merchant services  
✅ **Multi-turn Task Flow**: Payment required → Payment submitted → Payment settled → Service delivered  
✅ **SUI Blockchain**: Payments processed on SUI testnet  
✅ **Google ADK UI**: Interactive chat interface for testing  

## Structure

- `client/` - Host agent that discovers and communicates with merchants
  - `agent.py` - ADK wrapper agent for the UI
  - `host.py` - A2A-compliant host agent implementation
- `server/` - A2A merchant agents with X402 payment integration
  - `merchant.py` - Merchant business logic with payment support
  - `server.py` - A2A server with X402ServerExecutor wrapping

## Running

1. Start the merchant server:
```bash
uv run python server/server.py
```

2. Start the UI:
```bash
uv run adk web --port 9000
```

3. Open http://localhost:9000 and try:
   - "What merchants are available?" - Discovers merchants with payment capabilities
   - "Ask [merchant_name] what products do you have?" - Triggers payment flow for any discovered merchant

## Payment Flow

When you ask merchants about their products, the X402 payment flow is triggered:

1. **Payment Required**: Merchant responds with payment requirements (0.05 SUI)
2. **Payment Submission**: Client would sign and submit payment (requires wallet integration)
3. **Payment Settlement**: Merchant verifies and settles payment on SUI blockchain  
4. **Service Delivery**: Product list delivered after successful payment

## Configuration

Key settings in `.env`:
- `MERCHANT_ADDRESS`: SUI address to receive payments
- `NETWORK`: `sui-testnet` for testnet payments
- `FACILITATOR_URL`: X402 facilitator service for payment processing
- `DEFAULT_PRICE`: Price per service call (0.05 SUI)

## Merchants

The demo includes multiple merchant agents that implement:
- A2A protocol with agent cards and discovery
- X402 payment extension (declared in agent cards)
- Multi-turn task updating for payment flows
- Integration with SUI blockchain via X402 facilitator