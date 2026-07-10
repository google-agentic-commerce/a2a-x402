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

func SetPaymentStatus(msg *a2a.Message, status PaymentStatus) {
	if msg.Metadata == nil {
		msg.Metadata = make(map[string]interface{})
	}
	msg.Metadata[x402.MetadataKeyStatus] = status.String()
}

func SetPaymentRequirements(msg *a2a.Message, requirements *x402types.PaymentRequired) error {
	if requirements == nil {
		return nil
	}
	if msg.Metadata == nil {
		msg.Metadata = make(map[string]interface{})
	}
	reqMap, err := utils.ToMap(requirements)
	if err != nil {
		return fmt.Errorf("failed to convert payment requirements to map: %w", err)
	}
	msg.Metadata[x402.MetadataKeyRequired] = reqMap
	return nil
}

func SetPaymentPayload(msg *a2a.Message, payload *x402types.PaymentPayload) error {
	if payload == nil {
		return nil
	}
	if msg.Metadata == nil {
		msg.Metadata = make(map[string]interface{})
	}
	payloadMap, err := utils.ToMap(payload)
	if err != nil {
		return fmt.Errorf("failed to convert payment payload to map: %w", err)
	}
	msg.Metadata[x402.MetadataKeyPayload] = payloadMap
	return nil
}

func SetPaymentReceipts(msg *a2a.Message, receipts []*x402core.SettleResponse) error {
	if len(receipts) == 0 {
		return nil
	}
	if msg.Metadata == nil {
		msg.Metadata = make(map[string]interface{})
	}

	var receiptsArray []interface{}
	if existing, ok := msg.Metadata[x402.MetadataKeyReceipts].([]interface{}); ok {
		receiptsArray = existing
	} else {
		receiptsArray = make([]interface{}, 0)
	}

	for _, receipt := range receipts {
		receiptMap, err := utils.ToMap(receipt)
		if err != nil {
			return fmt.Errorf("failed to convert receipt to map: %w", err)
		}
		receiptsArray = append(receiptsArray, receiptMap)
	}

	msg.Metadata[x402.MetadataKeyReceipts] = receiptsArray
	return nil
}

func SetPaymentError(msg *a2a.Message, errorCode string) {
	if errorCode == "" {
		return
	}
	if msg.Metadata == nil {
		msg.Metadata = make(map[string]interface{})
	}
	msg.Metadata[x402.MetadataKeyError] = errorCode
}

func SetOriginalPrompt(msg *a2a.Message, prompt string) {
	if prompt == "" {
		return
	}
	if msg.Metadata == nil {
		msg.Metadata = make(map[string]interface{})
	}
	msg.Metadata[x402.MetadataKeyOriginalPrompt] = prompt
}

func ClearPaymentMetadata(msg *a2a.Message) {
	if msg.Metadata == nil {
		return
	}
	delete(msg.Metadata, x402.MetadataKeyPayload)
	delete(msg.Metadata, x402.MetadataKeyRequired)
}
