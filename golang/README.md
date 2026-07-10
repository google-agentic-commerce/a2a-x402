# x402 A2A Payment Protocol - Go Implementation

This is the Go implementation of the x402 payment protocol extension for A2A (Agent-to-Agent) communication.

## Features

- **x402 v2 Support**: This implementation uses x402 protocol version 2
- Dynamic payment requirements using the same execute-and-request-payment model as the Python implementation
- Payment verification and settlement
- Support for multiple blockchain networks (EVM and Solana)
- Structured A2A artifact results
- Merchant and client examples included

## Requirements

- Go 1.24.4 or later
- GEMINI_API_KEY environment variable (for image generation example)

## Quick Start

### Running the Merchant Server

1. Configure the server by creating `examples/merchant/server_config.json` based on `server_config.example.json`:

```json
{
  "networkConfigs": [
    {
      "networkName": "eip155:84532",
      "payToAddress": "0xYOUR_BASE_SEPOLIA_ADDRESS"
    }
  ]
}
```

2. Set the GEMINI_API_KEY environment variable:
```bash
export GEMINI_API_KEY="your-api-key"
```

3. Run the server:
```bash
cd examples/merchant
go run . -port :8080 -facilitator https://www.x402.org/facilitator
```

### Running the Client

1. Configure the client by creating `examples/client/client_config.json` based on `client_config.example.json`:

```json
{
  "networkKeyPairs": [
    {
      "networkName": "eip155:84532",
      "privateKey": "0xYOUR_EVM_PRIVATE_KEY_HEX"
    }
  ]
}
```

2. Run the client:
```bash
cd examples/client
go run . -merchant http://localhost:8080 -message "Generate an image of a sunset"
```

## Project Structure

- `core/`: Core implementation of x402 payment protocol
  - `merchant/`: Merchant-side payment handling
  - `client/`: Client-side payment handling
  - `x402/`: x402 protocol state management
- `examples/`: Example implementations
  - `merchant/`: Merchant server example with image generation service
  - `client/`: Client example

## Configuration

### Server Configuration

The server requires a configuration file with network settings:
- `networkName`: Blockchain network identifier (e.g., "eip155:84532" for Base Sepolia)
- `payToAddress`: Address to receive payments

### Client Configuration

The client requires a configuration file with network key pairs:
- `networkName`: Blockchain network identifier
- `privateKey`: Private key for signing payment transactions

## x402 Protocol Version

This implementation uses **x402 protocol version 2** (`X402Version: 2`), which is set in the payment requirements when creating payment requests.
It declares the A2A x402 v0.2 extension URI and rejects v1 payment envelopes.
It targets the current `github.com/x402-foundation/x402/go` API and accepts only CAIP-2 network identifiers and the v2 top-level `resource` object. Legacy network aliases and resource fields embedded in payment requirement `extra` are not supported.

## Business Service Model

Business services are invoked once before payment. They can either return a result immediately for a free request, or return `business.PaymentRequiredError` with dynamic payment terms. After the client submits a valid payment, the service is invoked again with `PaymentVerified: true`.

```go
func (s *Service) Execute(ctx context.Context, request business.Request) (*business.Result, error) {
	if !request.PaymentVerified {
		terms := business.ServiceRequirements{
			Price:             "1.00",
			Resource:          "/service",
			Description:       "Paid service",
			MimeType:          "application/json",
			Scheme:            "exact",
			MaxTimeoutSeconds: 600,
		}
		return nil, business.NewPaymentRequiredError("Payment required", terms)
	}

	return &business.Result{Message: "Service completed"}, nil
}
```

`business.Result.Artifacts` can contain A2A text, data, or file parts. These artifacts are emitted before the final completed task update.
