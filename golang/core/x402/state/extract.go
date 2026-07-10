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
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

func ExtractPaymentState(task *a2a.Task, message *a2a.Message) (*PaymentState, error) {
	paymentState := &PaymentState{}

	status, err := ExtractPaymentStatus(task)
	if err != nil {
		return nil, fmt.Errorf("failed to extract payment status: %w", err)
	}
	messageStatus, err := ExtractPaymentStatusFromMessage(message)
	if err != nil {
		return nil, fmt.Errorf("failed to extract message payment status: %w", err)
	}
	if messageStatus == PaymentSubmitted {
		status = messageStatus
	}
	paymentState.Status = status

	payload, err := ExtractPaymentPayload(task, message)
	if err != nil {
		return nil, fmt.Errorf("failed to extract payment payload: %w", err)
	}
	paymentState.Payload = payload

	requirements, err := ExtractPaymentRequirements(task)
	if err != nil {
		return nil, fmt.Errorf("failed to extract payment requirements: %w", err)
	}
	paymentState.Requirements = requirements

	receipts, err := ExtractPaymentReceipts(task)
	if err != nil {
		return nil, fmt.Errorf("failed to extract payment receipts: %w", err)
	}
	paymentState.Receipts = receipts

	return paymentState, nil
}

func ExtractPaymentStatus(task *a2a.Task) (PaymentStatus, error) {
	if task != nil && task.Status.Message != nil {
		metadata := task.Status.Message.Meta()
		if metadata != nil {
			if statusStr, ok := metadata[x402.MetadataKeyStatus].(string); ok {
				return PaymentStatus(statusStr), nil
			}
		}
	}

	return "", nil
}

func ExtractPaymentStatusFromTask(task *a2a.Task) (PaymentStatus, error) {
	if task == nil {
		return "", fmt.Errorf("task is nil")
	}

	if task.Status.Message == nil {
		return "", nil
	}

	meta := task.Status.Message.Meta()
	if meta == nil {
		return "", nil
	}

	statusValue, ok := meta[x402.MetadataKeyStatus].(string)
	if !ok {
		return "", nil
	}

	status := PaymentStatus(statusValue)
	if !status.IsValid() {
		return "", nil
	}

	return status, nil
}

func ExtractPaymentStatusFromMessage(message *a2a.Message) (PaymentStatus, error) {
	if message == nil || message.Meta() == nil {
		return "", nil
	}

	statusValue, ok := message.Meta()[x402.MetadataKeyStatus].(string)
	if !ok {
		return "", nil
	}

	status := PaymentStatus(statusValue)
	if !status.IsValid() {
		return "", nil
	}

	return status, nil
}

func ExtractPaymentRequirements(task *a2a.Task) (*x402types.PaymentRequired, error) {
	if task != nil && task.Status.Message != nil {
		metadata := task.Status.Message.Meta()
		if metadata != nil {
			if reqData, ok := metadata[x402.MetadataKeyRequired]; ok {
				reqMap, ok := reqData.(map[string]interface{})
				if !ok {
					return nil, fmt.Errorf("payment requirements is not a map")
				}
				var paymentRequired x402types.PaymentRequired
				if err := utils.FromMap(reqMap, &paymentRequired); err != nil {
					return nil, fmt.Errorf("failed to unmarshal payment requirements: %w", err)
				}
				return &paymentRequired, nil
			}
		}
	}

	return nil, nil
}

func ExtractPaymentReceipts(task *a2a.Task) ([]*x402core.SettleResponse, error) {
	if task != nil && task.Status.Message != nil {
		metadata := task.Status.Message.Meta()
		if metadata != nil {
			if receiptsData, ok := metadata[x402.MetadataKeyReceipts].([]interface{}); ok {
				receipts := make([]*x402core.SettleResponse, 0, len(receiptsData))
				for _, receiptData := range receiptsData {
					receiptMap, ok := receiptData.(map[string]interface{})
					if !ok {
						return nil, fmt.Errorf("receipt data is not a map")
					}
					var receipt x402core.SettleResponse
					if err := utils.FromMap(receiptMap, &receipt); err != nil {
						return nil, fmt.Errorf("failed to unmarshal receipt: %w", err)
					}
					receipts = append(receipts, &receipt)
				}
				return receipts, nil
			}
		}
	}

	return []*x402core.SettleResponse{}, nil
}

func ExtractPaymentPayload(task *a2a.Task, message *a2a.Message) (*x402types.PaymentPayload, error) {
	if message != nil {
		meta := message.Meta()
		if meta != nil {
			if payloadData, ok := meta[x402.MetadataKeyPayload]; ok {
				payloadMap, ok := payloadData.(map[string]interface{})
				if !ok {
					return nil, fmt.Errorf("payment payload is not a map")
				}
				var payload x402types.PaymentPayload
				if err := utils.FromMap(payloadMap, &payload); err != nil {
					return nil, fmt.Errorf("failed to unmarshal payment payload: %w", err)
				}
				return &payload, nil
			}
		}
	}

	if task != nil && task.Status.Message != nil {
		metadata := task.Status.Message.Meta()
		if metadata != nil {
			if payloadData, ok := metadata[x402.MetadataKeyPayload]; ok {
				payloadMap, ok := payloadData.(map[string]interface{})
				if !ok {
					return nil, fmt.Errorf("payment payload is not a map")
				}
				var payload x402types.PaymentPayload
				if err := utils.FromMap(payloadMap, &payload); err != nil {
					return nil, fmt.Errorf("failed to unmarshal payment payload: %w", err)
				}
				return &payload, nil
			}
		}
	}

	return nil, nil
}

func ExtractOriginalPrompt(task *a2a.Task) string {
	if task == nil || task.Status.Message == nil {
		return ""
	}

	meta := task.Status.Message.Meta()
	if meta == nil {
		return ""
	}

	if prompt, ok := meta[x402.MetadataKeyOriginalPrompt].(string); ok {
		return prompt
	}

	return ""
}

func ExtractMessageText(message *a2a.Message) string {
	if message == nil {
		return ""
	}

	for _, part := range message.Parts {
		switch p := part.(type) {
		case a2a.TextPart:
			if p.Text != "" {
				return p.Text
			}
		}
	}

	return ""
}
