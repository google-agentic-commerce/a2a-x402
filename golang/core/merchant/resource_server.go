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

package merchant

import (
	"context"
	"fmt"

	"github.com/google-agentic-commerce/a2a-x402/core/business"
	"github.com/google-agentic-commerce/a2a-x402/core/types"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402 "github.com/x402-foundation/x402/go"
	x402core "github.com/x402-foundation/x402/go"
	x402http "github.com/x402-foundation/x402/go/http"
	evm "github.com/x402-foundation/x402/go/mechanisms/evm/exact/server"
	svm "github.com/x402-foundation/x402/go/mechanisms/svm/exact/server"
	x402types "github.com/x402-foundation/x402/go/types"
)

func NewResourceServer(ctx context.Context, facilitatorURL string) (*x402.X402ResourceServer, error) {
	if facilitatorURL == "" {
		return nil, fmt.Errorf("facilitatorURL is required")
	}

	var opts []x402.ResourceServerOption

	facilitatorConfig := &x402http.FacilitatorConfig{
		URL: facilitatorURL,
	}
	facilitator := x402http.NewHTTPFacilitatorClient(facilitatorConfig)

	opts = append(opts,
		x402.WithFacilitatorClient(facilitator),
		x402.WithSchemeServer(x402.Network(x402pkg.NetworkBase), evm.NewExactEvmScheme()),
		x402.WithSchemeServer(x402.Network(x402pkg.NetworkBaseSepolia), evm.NewExactEvmScheme()),
		x402.WithSchemeServer(x402.Network(x402pkg.NetworkSolanaMainnet), svm.NewExactSvmScheme()),
		x402.WithSchemeServer(x402.Network(x402pkg.NetworkSolanaDevnet), svm.NewExactSvmScheme()),
		x402.WithSchemeServer(x402.Network(x402pkg.NetworkSolanaTestnet), svm.NewExactSvmScheme()),
	)

	server := x402.Newx402ResourceServer(opts...)

	if err := server.Initialize(ctx); err != nil {
		return nil, fmt.Errorf("failed to initialize x402 resource server: %w", err)
	}

	return server, nil
}

// resourceServerWrapper wraps *x402.X402ResourceServer to implement ResourceServer
type resourceServerWrapper struct {
	server *x402.X402ResourceServer
}

func (w *resourceServerWrapper) BuildPaymentRequirementsFromConfig(ctx context.Context, config x402.ResourceConfig) ([]x402types.PaymentRequirements, error) {
	return w.server.BuildPaymentRequirementsFromConfig(ctx, config)
}

func (w *resourceServerWrapper) FindMatchingRequirements(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements {
	return w.server.FindMatchingRequirements(accepts, payload)
}

func (w *resourceServerWrapper) VerifyPayment(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error) {
	return w.server.VerifyPayment(ctx, payload, requirements)
}

func (w *resourceServerWrapper) SettlePayment(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error) {
	return w.server.SettlePayment(ctx, payload, requirements, nil)
}

func BuildPaymentRequirements(
	ctx context.Context,
	server ResourceServer,
	networkConfig types.NetworkConfig,
	params business.ServiceRequirements,
) ([]*x402types.PaymentRequirements, error) {

	config := x402.ResourceConfig{
		Scheme:            params.Scheme,
		PayTo:             networkConfig.PayToAddress,
		Price:             params.Price,
		Network:           x402.Network(networkConfig.NetworkName),
		MaxTimeoutSeconds: params.MaxTimeoutSeconds,
	}

	reqs, err := server.BuildPaymentRequirementsFromConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("failed to build payment requirements: %w", err)
	}
	if len(reqs) == 0 {
		return nil, fmt.Errorf("no payment requirements returned")
	}

	result := make([]*x402types.PaymentRequirements, 0, len(reqs))
	for _, req := range reqs {
		result = append(result, &req)
	}
	return result, nil
}
