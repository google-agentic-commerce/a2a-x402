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
	"fmt"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/utils"
	"github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402types "github.com/x402-foundation/x402/go/types"
)

func EncodePaymentSubmission(
	taskID a2a.TaskID,
	paymentPayload *x402types.PaymentPayload,
) (*a2a.Message, error) {
	payloadMap, err := utils.ToMap(paymentPayload)
	if err != nil {
		return nil, fmt.Errorf("failed to convert payment payload to map: %w", err)
	}

	message := a2a.NewMessageForTask(
		a2a.MessageRoleUser,
		a2a.TaskInfo{TaskID: taskID},
		a2a.TextPart{Text: "Payment authorization provided"},
	)

	message.Metadata = map[string]interface{}{
		x402.MetadataKeyStatus:  PaymentSubmitted.String(),
		x402.MetadataKeyPayload: payloadMap,
	}

	return message, nil
}
