# DK x402 Payment Protocol Demo with EigenDA Storage

A complete example demonstrating text storage on EigenDA with micropayments using the A2A protocol and X402 payment system.

## What This Does

This example provides a complete system for:
- **Storing text data** on EigenDA decentralized storage for $0.01 per operation
- **Retrieving stored data** using certificates (free)
- **Automatic payment processing** through the X402 protocol
- **User-friendly interface** via an AI agent client

## Quick Start

### 1. Prerequisites
- Docker installed and running
- Python 3.13+
- Google API key for the AI agents

### 2. Setup

```bash
# Navigate to the example directory
cd examples/python/adk-demo

# Install dependencies
pip install -e .

# Create .env file with your Google API key
echo "GOOGLE_API_KEY=your_key_here" > .env
echo "USE_MOCK_FACILITATOR=true" >> .env
```

### 3. Start the Server

```bash
# Terminal 1: Start the EigenDA storage server
uv run server
```

The server will automatically:
- Start the EigenDA Docker container
- Initialize the storage service
- Register the agent at `http://localhost:10000/agents/eigenda_agent`

### 4. Use the Client

```bash
# Terminal 2: Start the client
uv run adk web
```

### 5. (optional) Run the terminal client

```bash
# Terminal 2: Start the terminal client
chmod +x ./run_cli.sh
./run_cli.sh
```

## Example Usage

### Store Text
```
You: Store this message: "Hello, decentralized world!"
Assistant: I'll help you store that text on EigenDA. Let me send it to the storage agent.

EigenDA storage request: Store 28 characters for 10000 units ($0.01). 
Certificate preview: abc123def456... 
Do you want to approve this payment?

You: yes
Assistant: Payment successful! Your text has been stored on EigenDA. 
Certificate ID: abc123def456...
Please save this certificate - you'll need it to retrieve your data later.
```

### Retrieve Text
```
You: Retrieve text with certificate abc123def456
Assistant: I'll retrieve that text from EigenDA for you.

Retrieved data: "Hello, decentralized world!"
```

### List Stored Data
```
You: Show me what I've stored
Assistant: Here are your stored certificates:
- abc123def456...: "Hello, decentralized..." (stored at 1234567890)
- xyz789ghi012...: "Another message..." (stored at 1234567891)
```

## How It Works

### Architecture
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   Server    │────▶│  EigenDA    │
│   Agent     │◀────│   Agent     │◀────│   Docker    │
└─────────────┘     └─────────────┘     └─────────────┘
      │                    │                     │
      │   1. Store text    │   2. Submit data   │
      │───────────────────▶│────────────────────▶│
      │                    │                     │
      │   3. Payment req   │   4. Certificate   │
      │◀───────────────────│◀────────────────────│
      │                    │                     │
      │   5. Approve pay   │                     │
      │───────────────────▶│                     │
      │                    │                     │
      │   6. Confirmed     │                     │
      │◀───────────────────│                     │
```

### Payment Flow
1. User requests to store text
2. Server stores data in EigenDA and gets a certificate
3. Server requests $0.01 payment via X402 protocol
4. User approves the payment
5. Client signs and sends the payment
6. Server confirms storage with certificate ID

## Features

- **Decentralized Storage**: Data is permanently stored on EigenDA
- **Micropayments**: Fixed $0.01 fee per storage operation
- **Free Retrieval**: Retrieve your data anytime using the certificate
- **AI Assistant**: Natural language interface for all operations
- **Docker Integration**: Automatic EigenDA container management
- **Mock Mode**: Test without real payments using mock facilitator

## Configuration

### Environment Variables

Create a `.env` file:

```bash
# Required: Google AI API key
GOOGLE_API_KEY=your_google_api_key

# Payment mode (true for testing, false for real payments)
USE_MOCK_FACILITATOR=true

# For real payments only:
# MERCHANT_PRIVATE_KEY=your_private_key
```

### Server Options

```bash
python -m server --host 0.0.0.0 --port 8080
```

## Troubleshooting

### Docker Issues
```bash
# Check if EigenDA is running
docker ps | grep eigenda-proxy

# View logs
docker logs eigenda-proxy

# Restart container
docker restart eigenda-proxy
```

### Connection Issues
- Ensure server is running before starting client
- Check firewall settings for port 10000
- Verify Docker daemon is running

### Payment Issues
- In mock mode: payments are simulated
- In real mode: ensure wallet has USDC on Base Sepolia

## Technical Details

- **Storage Cost**: 10000 USDC units (0.01 USDC with 6 decimals)
- **EigenDA Port**: 3100 (configurable)
- **Commitment Mode**: Standard
- **Data Encoding**: UTF-8
- **Certificate Format**: Hexadecimal

## Project Structure

```
examples/python/adk-demo/
├── server/
│   └── agents/
│       ├── eigenda_agent.py    # EigenDA storage agent
│       └── routes.py            # Agent registration
├── client_agent/
│   ├── agent.py                # Client configuration
│   └── client_agent.py          # Client orchestrator
└── EIGENDA_README.md            # This file
```

## Next Steps

- Try storing different types of text
- Retrieve data using certificates
- Explore the code to understand the integration
- Modify the storage price or add new features
- Implement persistence for certificate management