// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed on the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package client

import (
	"context"
	"fmt"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/types"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
	"github.com/google-agentic-commerce/a2a-x402/core/x402/state"
	x402 "github.com/x402-foundation/x402/go"
	evm "github.com/x402-foundation/x402/go/mechanisms/evm/exact/client"
	svm "github.com/x402-foundation/x402/go/mechanisms/svm/exact/client"
	evmsigners "github.com/x402-foundation/x402/go/signers/evm"
	svmsigners "github.com/x402-foundation/x402/go/signers/svm"
	x402types "github.com/x402-foundation/x402/go/types"
)

type X402Client struct {
	client *x402.X402Client
}

func NewX402Client(networkKeyPairs []types.NetworkKeyPair) (*X402Client, error) {
	if len(networkKeyPairs) == 0 {
		return nil, fmt.Errorf("at least one network-key pair is required")
	}

	client := x402.Newx402Client()

	for _, pair := range networkKeyPairs {
		switch {
		case pair.NetworkName == x402pkg.NetworkBase || pair.NetworkName == x402pkg.NetworkBaseSepolia:
			evmSigner, err := evmsigners.NewClientSignerFromPrivateKey(pair.PrivateKey)
			if err != nil {
				return nil, fmt.Errorf("failed to create EVM signer for network %s: %w", pair.NetworkName, err)
			}
			client.Register(x402.Network(pair.NetworkName), evm.NewExactEvmScheme(evmSigner, nil))
		case pair.NetworkName == x402pkg.NetworkSolanaMainnet || pair.NetworkName == x402pkg.NetworkSolanaDevnet || pair.NetworkName == x402pkg.NetworkSolanaTestnet:
			svmSigner, err := svmsigners.NewClientSignerFromPrivateKey(pair.PrivateKey)
			if err != nil {
				return nil, fmt.Errorf("failed to create SVM signer for network %s: %w", pair.NetworkName, err)
			}
			client.Register(x402.Network(pair.NetworkName), svm.NewExactSvmScheme(svmSigner))
		default:
			return nil, fmt.Errorf("unsupported network: %s", pair.NetworkName)
		}
	}
	return &X402Client{
		client: client,
	}, nil
}

func (c *X402Client) ProcessPaymentRequired(
	ctx context.Context,
	taskID a2a.TaskID,
	paymentRequired *x402types.PaymentRequired,
) (*a2a.Message, error) {
	if paymentRequired == nil {
		return nil, fmt.Errorf("payment requirements are required")
	}
	if paymentRequired.X402Version != x402pkg.X402Version {
		return nil, fmt.Errorf("unsupported x402 version: %d", paymentRequired.X402Version)
	}
	if len(paymentRequired.Accepts) == 0 {
		return nil, fmt.Errorf("no payment options available")
	}
	if paymentRequired.Resource == nil || paymentRequired.Resource.URL == "" {
		return nil, fmt.Errorf("payment resource URL is required")
	}

	paymentRequirements, err := c.client.SelectPaymentRequirements(paymentRequired.Accepts)
	if err != nil {
		return nil, fmt.Errorf("no matching payment option found: %w", err)
	}

	payload, err := c.client.CreatePaymentPayload(
		ctx,
		paymentRequirements,
		paymentRequired.Resource,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create payment payload: %w", err)
	}

	paymentMessage, err := state.EncodePaymentSubmission(taskID, &payload)
	if err != nil {
		return nil, fmt.Errorf("failed to encode payment submission: %w", err)
	}

	return paymentMessage, nil
}
