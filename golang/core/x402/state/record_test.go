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
	"testing"

	"github.com/a2aproject/a2a-go/a2a"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

func TestRecordPaymentFailedPreservesReceiptAndReason(t *testing.T) {
	task := &a2a.Task{
		ID: "task-123",
		Status: a2a.TaskStatus{
			State:   a2a.TaskStateWorking,
			Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "Payment required"}),
		},
	}
	if err := SetPaymentPayload(task.Status.Message, &x402types.PaymentPayload{X402Version: x402pkg.X402Version}); err != nil {
		t.Fatalf("SetPaymentPayload() error = %v", err)
	}
	if err := SetPaymentRequirements(task.Status.Message, &x402types.PaymentRequired{X402Version: x402pkg.X402Version}); err != nil {
		t.Fatalf("SetPaymentRequirements() error = %v", err)
	}
	receipt := &x402core.SettleResponse{
		Success:     false,
		ErrorReason: "settlement failed",
		Payer:       "0xpayer",
		Transaction: "0xtx",
		Network:     x402pkg.NetworkBaseSepolia,
	}

	if err := RecordPaymentFailed(task, x402pkg.ErrorCodeSettlementFailed, "settlement failed", receipt); err != nil {
		t.Fatalf("RecordPaymentFailed() error = %v", err)
	}
	if got := ExtractMessageText(task.Status.Message); got != "settlement failed" {
		t.Errorf("failure message = %q", got)
	}
	status, err := ExtractPaymentStatusFromTask(task)
	if err != nil || status != PaymentFailed {
		t.Errorf("payment status = %v, error = %v", status, err)
	}
	if got := task.Status.Message.Metadata[x402pkg.MetadataKeyError]; got != x402pkg.ErrorCodeSettlementFailed {
		t.Errorf("payment error code = %v", got)
	}
	if _, ok := task.Status.Message.Metadata[x402pkg.MetadataKeyPayload]; ok {
		t.Error("payment payload was not removed")
	}
	if _, ok := task.Status.Message.Metadata[x402pkg.MetadataKeyRequired]; !ok {
		t.Error("payment requirements should remain available after failure")
	}
	receipts, err := ExtractPaymentReceipts(task)
	if err != nil {
		t.Fatalf("ExtractPaymentReceipts() error = %v", err)
	}
	if len(receipts) != 1 || receipts[0].Payer != receipt.Payer || receipts[0].Transaction != receipt.Transaction {
		t.Errorf("receipt was not preserved: %#v", receipts)
	}
}

func TestRecordPaymentFailedRequiresReceipt(t *testing.T) {
	task := &a2a.Task{Status: a2a.TaskStatus{Message: a2a.NewMessage(a2a.MessageRoleAgent)}}
	if err := RecordPaymentFailed(task, x402pkg.ErrorCodeSettlementFailed, "failed", nil); err == nil {
		t.Fatal("RecordPaymentFailed() error = nil, want missing receipt error")
	}
}
