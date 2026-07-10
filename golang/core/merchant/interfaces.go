// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package merchant

import (
	"context"

	"github.com/a2aproject/a2a-go/a2asrv"
	x402 "github.com/x402-foundation/x402/go"
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

// ResourceServer abstracts the x402 resource server operations
// to enable testing with mock implementations.
// This interface contains all methods that BusinessOrchestrator needs from the merchant.
type ResourceServer interface {
	// BuildPaymentRequirementsFromConfig builds payment requirements from configuration
	BuildPaymentRequirementsFromConfig(ctx context.Context, config x402.ResourceConfig) ([]x402types.PaymentRequirements, error)

	// FindMatchingRequirements finds a matching payment requirement from accepts array
	FindMatchingRequirements(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements

	// VerifyPayment verifies a payment payload
	VerifyPayment(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error)

	// SettlePayment settles a payment
	SettlePayment(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error)
}

// ExtensionChecker abstracts extension checking to enable testing.
// This solves the problem of global function calls that cannot be mocked.
type ExtensionChecker interface {
	// ExtensionsFrom extracts extensions from context
	ExtensionsFrom(ctx context.Context) (*a2asrv.Extensions, bool)
}

// defaultExtensionChecker is the default implementation that uses the global function
type defaultExtensionChecker struct{}

func (d *defaultExtensionChecker) ExtensionsFrom(ctx context.Context) (*a2asrv.Extensions, bool) {
	return a2asrv.ExtensionsFrom(ctx)
}

// DefaultExtensionChecker returns the default extension checker implementation
func DefaultExtensionChecker() ExtensionChecker {
	return &defaultExtensionChecker{}
}
