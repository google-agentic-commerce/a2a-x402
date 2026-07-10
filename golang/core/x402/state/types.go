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

package state

import (
	"github.com/a2aproject/a2a-go/a2a"
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

type PaymentStatus string

const (
	PaymentRequired  PaymentStatus = "payment-required"
	PaymentSubmitted PaymentStatus = "payment-submitted"
	PaymentVerified  PaymentStatus = "payment-verified"
	PaymentRejected  PaymentStatus = "payment-rejected"
	PaymentCompleted PaymentStatus = "payment-completed"
	PaymentFailed    PaymentStatus = "payment-failed"
)

func (ps PaymentStatus) IsValid() bool {
	switch ps {
	case PaymentRequired, PaymentSubmitted, PaymentVerified,
		PaymentRejected, PaymentCompleted, PaymentFailed:
		return true
	default:
		return false
	}
}

func (ps PaymentStatus) String() string {
	return string(ps)
}

type PaymentState struct {
	Status       PaymentStatus
	Message      string
	Requirements *x402types.PaymentRequired
	Payload      *x402types.PaymentPayload
	Receipts     []*x402core.SettleResponse
	Artifacts    []*a2a.Artifact
}
