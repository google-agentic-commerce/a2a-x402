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
	"github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

func RecordPaymentRequired(task *a2a.Task, requirements *x402types.PaymentRequired, defaultText string) error {
	if task.Status.Message == nil {
		if defaultText == "" {
			defaultText = "Payment required"
		}
		task.Status.Message = a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: defaultText})
	}
	SetPaymentStatus(task.Status.Message, PaymentRequired)
	return SetPaymentRequirements(task.Status.Message, requirements)
}

func RecordPaymentVerified(task *a2a.Task, paymentState *PaymentState, defaultText string) error {
	if task.Status.Message == nil {
		if defaultText == "" {
			defaultText = "Payment verified"
		}
		task.Status.Message = a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: defaultText})
	}
	SetPaymentStatus(task.Status.Message, paymentState.Status)
	if err := SetPaymentPayload(task.Status.Message, paymentState.Payload); err != nil {
		return err
	}
	return SetPaymentRequirements(task.Status.Message, paymentState.Requirements)
}

func RecordPaymentCompleted(task *a2a.Task, receipts []*x402core.SettleResponse, defaultText string) error {
	if task.Status.Message == nil {
		if defaultText == "" {
			defaultText = "Task completed"
		}
		task.Status.Message = a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: defaultText})
	}

	if task.Status.Message != nil && defaultText != "" {
		var newParts []a2a.Part
		for _, part := range task.Status.Message.Parts {
			if _, isTextPart := part.(a2a.TextPart); !isTextPart {
				newParts = append(newParts, part)
			}
		}
		newParts = append(newParts, a2a.TextPart{Text: defaultText})
		task.Status.Message.Parts = newParts
	}
	SetPaymentStatus(task.Status.Message, PaymentCompleted)
	if err := SetPaymentReceipts(task.Status.Message, receipts); err != nil {
		return err
	}
	ClearPaymentMetadata(task.Status.Message)
	return nil
}

func RecordPaymentFailed(task *a2a.Task, errorCode string, defaultText string, receipt *x402core.SettleResponse) error {
	if receipt == nil {
		return fmt.Errorf("failed payment receipt is required")
	}
	if task.Status.Message == nil {
		if defaultText == "" {
			defaultText = "Payment failed"
		}
		task.Status.Message = a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: defaultText})
	}
	if defaultText != "" {
		var newParts []a2a.Part
		for _, part := range task.Status.Message.Parts {
			if _, isTextPart := part.(a2a.TextPart); !isTextPart {
				newParts = append(newParts, part)
			}
		}
		newParts = append(newParts, a2a.TextPart{Text: defaultText})
		task.Status.Message.Parts = newParts
	}
	SetPaymentStatus(task.Status.Message, PaymentFailed)
	SetPaymentError(task.Status.Message, errorCode)
	if err := SetPaymentReceipts(task.Status.Message, []*x402core.SettleResponse{receipt}); err != nil {
		return err
	}
	delete(task.Status.Message.Metadata, x402.MetadataKeyPayload)
	return nil
}
