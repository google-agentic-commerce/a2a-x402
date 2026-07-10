// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package client

import (
	"context"
	"strings"
	"testing"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/types"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402types "github.com/x402-foundation/x402/go/types"
)

func TestProcessPaymentRequiredValidatesV2Envelope(t *testing.T) {
	client := &X402Client{}
	taskID := a2a.TaskID("task-123")

	tests := []struct {
		name     string
		required *x402types.PaymentRequired
		want     string
	}{
		{
			name:     "nil requirements",
			required: nil,
			want:     "payment requirements are required",
		},
		{
			name: "v1 is rejected",
			required: &x402types.PaymentRequired{
				X402Version: 1,
			},
			want: "unsupported x402 version: 1",
		},
		{
			name: "v2 requires payment options",
			required: &x402types.PaymentRequired{
				X402Version: x402pkg.X402Version,
			},
			want: "no payment options available",
		},
		{
			name: "v2 rejects resource stored in requirement extra",
			required: &x402types.PaymentRequired{
				X402Version: x402pkg.X402Version,
				Accepts: []x402types.PaymentRequirements{{
					Scheme: "exact",
					Extra:  map[string]interface{}{"resource": "/legacy-resource"},
				}},
			},
			want: "payment resource URL is required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := client.ProcessPaymentRequired(context.Background(), taskID, tt.required)
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("error = %v, want substring %q", err, tt.want)
			}
		})
	}
}

func TestNewX402ClientRequiresSigner(t *testing.T) {
	_, err := NewX402Client(nil)
	if err == nil || !strings.Contains(err.Error(), "at least one network-key pair is required") {
		t.Fatalf("error = %v", err)
	}
}

func TestNewX402ClientRejectsLegacyNetworkAlias(t *testing.T) {
	_, err := NewX402Client([]types.NetworkKeyPair{{
		NetworkName: "base",
		PrivateKey:  "unused",
	}})
	if err == nil || !strings.Contains(err.Error(), "unsupported network: base") {
		t.Fatalf("error = %v", err)
	}
}
