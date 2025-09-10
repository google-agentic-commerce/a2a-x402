# EigenDA + A2A + X402 Payment Integration

This example demonstrates how to integrate EigenDA decentralized storage with the A2A protocol and X402 payment system.

## Overview

The system consists of:
- **EigenDA Storage Agent**: A server-side agent that stores text data on EigenDA for $0.01 per operation
- **Client Agent**: An orchestrator that routes user requests to appropriate agents and handles payments
- **X402 Payment Protocol**: Handles micropayments for storage operations

## Features

- Store text strings on EigenDA decentralized storage
- Retrieve stored data using certificates (free operation)
- Automatic payment processing ($0.01 per storage)
- Docker-based EigenDA proxy management

## Architecture

### Server Side (`server/agents/eigenda_agent.py`)
- Manages EigenDA Docker container lifecycle
- Handles data submission and retrieval
- Integrates with X402 payment requirements
- Stores certificates for easy retrieval

### Client Side (`client_agent/`)
- Routes storage requests to EigenDA agent
- Handles payment confirmation flow
- Manages wallet signatures for payments

## Setup

### Prerequisites
- Docker installed and running
- Python 3.13+
- Base Sepolia testnet USDC for payments

### Installation

1. Install dependencies:
```bash
cd examples/python/adk-demo
pip install -e .
```

2. Set up environment variables in `.env`:
```bash
# For Google AI
GOOGLE_API_KEY=your_google_api_key

# For mock payments (development)
USE_MOCK_FACILITATOR=true

# For real payments (production)
USE_MOCK_FACILITATOR=false
MERCHANT_PRIVATE_KEY=your_merchant_private_key
```

## Usage

### Starting the Server

```bash
# Start the server with EigenDA agent
python -m server --host localhost --port 10000
```

The server will:
1. Start the EigenDA Docker container automatically
2. Register the EigenDA agent at `/agents/eigenda_agent`
3. Handle storage and retrieval requests

### Using the Client

```bash
# In another terminal
cd client_agent
python main.py
```

### Example Interactions

#### Store Text Data
```
User: Store this message on EigenDA: "Hello, decentralized world!"
Client: [Routes to EigenDA agent]
Client: EigenDA storage request: Store 28 characters for 10000 units ($0.01). Certificate preview: abc123... Do you want to approve this payment?
User: Yes
Client: Payment successful! Data stored with certificate: abc123...
```

#### Retrieve Stored Data
```
User: Retrieve the text with certificate abc123
Client: [Routes to EigenDA agent]
Client: Retrieved data: "Hello, decentralized world!"
```

#### List Stored Certificates
```
User: Show me all stored certificates
Client: [Routes to EigenDA agent]
Client: Available certificates:
- abc123...: "Hello, decentralized..." (stored at timestamp)
```

## Technical Details

### EigenDA Integration
- Uses `ghcr.io/layr-labs/eigenda-proxy:latest` Docker image
- Runs on port 3100 by default
- Memory store enabled for development
- Standard commitment mode for data operations

### Payment Flow
1. User requests to store text
2. EigenDA agent stores data and gets certificate
3. Agent raises `X402PaymentRequiredException` with $0.01 requirement
4. Client presents payment request to user
5. User approves payment
6. Client signs and sends payment
7. Server verifies payment and confirms storage

### Data Storage
- Text data is stored as UTF-8 encoded bytes
- Certificates are hex-encoded identifiers
- Data can be retrieved using full or partial certificates

## Troubleshooting

### Docker Issues
- Ensure Docker daemon is running: `docker ps`
- Check container logs: `docker logs eigenda-proxy`
- Remove stuck container: `docker rm -f eigenda-proxy`

### Payment Issues
- Verify wallet has sufficient USDC balance
- Check network configuration (Base Sepolia)
- Ensure correct USDC contract address

### Connection Issues
- Verify server is running on correct port
- Check firewall settings
- Ensure EigenDA proxy health endpoint responds

## Development Notes

- The EigenDA service is singleton-managed for efficiency
- Certificates are cached in memory for quick lookup
- Async operations are wrapped for sync ADK compatibility
- Payment amount is fixed at $0.01 (10000 USDC units)

## Future Enhancements

- Support for binary data storage
- Batch storage operations
- Certificate management UI
- Variable pricing based on data size
- Persistent certificate database