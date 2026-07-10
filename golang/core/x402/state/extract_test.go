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

package state

import (
	"testing"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

func TestExtractPaymentStatus(t *testing.T) {
	tests := []struct {
		name    string
		task    *a2a.Task
		want    PaymentStatus
		wantErr bool
	}{
		{
			name:    "nil task",
			task:    nil,
			want:    "",
			wantErr: false,
		},
		{
			name: "task without message",
			task: &a2a.Task{
				ID:        "task-1",
				ContextID: "context-1",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking},
			},
			want:    "",
			wantErr: false,
		},
		{
			name: "task with message but no payment status",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				return task
			}(),
			want:    "",
			wantErr: false,
		},
		{
			name: "payment-required status from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateInputRequired, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentStatus(task.Status.Message, PaymentRequired)
				return task
			}(),
			want:    PaymentRequired,
			wantErr: false,
		},
		{
			name: "payment-submitted status from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentStatus(task.Status.Message, PaymentSubmitted)
				return task
			}(),
			want:    PaymentSubmitted,
			wantErr: false,
		},
		{
			name: "payment-verified status from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentStatus(task.Status.Message, PaymentVerified)
				return task
			}(),
			want:    PaymentVerified,
			wantErr: false,
		},
		{
			name: "payment-completed status from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateCompleted, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentStatus(task.Status.Message, PaymentCompleted)
				return task
			}(),
			want:    PaymentCompleted,
			wantErr: false,
		},
		{
			name: "payment-failed status from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateFailed, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentStatus(task.Status.Message, PaymentFailed)
				return task
			}(),
			want:    PaymentFailed,
			wantErr: false,
		},
		{
			name: "payment-rejected status from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateInputRequired, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentStatus(task.Status.Message, PaymentRejected)
				return task
			}(),
			want:    PaymentRejected,
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ExtractPaymentStatus(tt.task)
			if (err != nil) != tt.wantErr {
				t.Errorf("ExtractPaymentStatus() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if got != tt.want {
				t.Errorf("ExtractPaymentStatus() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestExtractMessageText(t *testing.T) {
	tests := []struct {
		name    string
		message *a2a.Message
		want    string
	}{
		{
			name:    "nil message",
			message: nil,
			want:    "",
		},
		{
			name:    "message with text part",
			message: a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "Hello, world!"}),
			want:    "Hello, world!",
		},
		{
			name:    "message without text part",
			message: a2a.NewMessage(a2a.MessageRoleUser),
			want:    "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ExtractMessageText(tt.message)
			if got != tt.want {
				t.Errorf("ExtractMessageText() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestExtractOriginalPrompt(t *testing.T) {
	tests := []struct {
		name string
		task *a2a.Task
		want string
	}{
		{
			name: "nil task",
			task: nil,
			want: "",
		},
		{
			name: "task without message",
			task: &a2a.Task{
				ID:        "task-1",
				ContextID: "context-1",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking},
			},
			want: "",
		},
		// Add more test cases with actual metadata containing original prompt
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ExtractOriginalPrompt(tt.task)
			if got != tt.want {
				t.Errorf("ExtractOriginalPrompt() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestExtractPaymentPayload(t *testing.T) {
	payload := &x402types.PaymentPayload{
		X402Version: x402.X402Version,
		Accepted: x402types.PaymentRequirements{
			Scheme:  "exact",
			Network: x402.NetworkBaseSepolia,
			Amount:  "100",
			Asset:   "0x456",
			PayTo:   "0x123",
		},
		Payload: map[string]interface{}{
			"signature": "0xabc",
			"authorization": map[string]interface{}{
				"from":         "0x789",
				"to":           "0x123",
				"value":        "100",
				"valid_after":  "0",
				"valid_before": "9999999999",
				"nonce":        "0xdef",
			},
		},
	}

	tests := []struct {
		name    string
		task    *a2a.Task
		message *a2a.Message
		want    *x402types.PaymentPayload
		wantErr bool
	}{
		{
			name:    "nil task and message",
			task:    nil,
			message: nil,
			want:    nil,
			wantErr: false,
		},
		{
			name: "payload from message",
			task: nil,
			message: func() *a2a.Message {
				msg := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "test"})
				SetPaymentPayload(msg, payload)
				return msg
			}(),
			want:    payload,
			wantErr: false,
		},
		{
			name: "payload from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentPayload(task.Status.Message, payload)
				return task
			}(),
			message: nil,
			want:    payload,
			wantErr: false,
		},
		{
			name: "message takes precedence over task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				otherPayload := &x402types.PaymentPayload{
					X402Version: x402.X402Version,
					Accepted: x402types.PaymentRequirements{
						Scheme:  "exact",
						Network: x402.NetworkBaseSepolia,
						Amount:  "200",
					},
				}
				SetPaymentPayload(task.Status.Message, otherPayload)
				return task
			}(),
			message: func() *a2a.Message {
				msg := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "test"})
				SetPaymentPayload(msg, payload)
				return msg
			}(),
			want:    payload,
			wantErr: false,
		},
		{
			name: "invalid payload type",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				task.Status.Message.Metadata = map[string]interface{}{
					x402.MetadataKeyPayload: "invalid string",
				}
				return task
			}(),
			message: nil,
			want:    nil,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ExtractPaymentPayload(tt.task, tt.message)
			if (err != nil) != tt.wantErr {
				t.Errorf("ExtractPaymentPayload() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr {
				return
			}
			if tt.want == nil {
				if got != nil {
					t.Errorf("ExtractPaymentPayload() = %v, want nil", got)
				}
				return
			}
			if got == nil {
				t.Errorf("ExtractPaymentPayload() = nil, want %v", tt.want)
				return
			}
			if got.X402Version != tt.want.X402Version {
				t.Errorf("ExtractPaymentPayload() X402Version = %v, want %v", got.X402Version, tt.want.X402Version)
			}
			if got.Accepted.Scheme != tt.want.Accepted.Scheme {
				t.Errorf("ExtractPaymentPayload() Scheme = %v, want %v", got.Accepted.Scheme, tt.want.Accepted.Scheme)
			}
		})
	}
}

func TestExtractPaymentRequirements(t *testing.T) {
	requirements := &x402types.PaymentRequired{
		X402Version: x402.X402Version,
		Accepts: []x402types.PaymentRequirements{
			{
				Scheme:  "exact",
				Network: x402.NetworkBaseSepolia,
				PayTo:   "0x123",
				Asset:   "0x456",
			},
		},
	}

	tests := []struct {
		name    string
		task    *a2a.Task
		want    *x402types.PaymentRequired
		wantErr bool
	}{
		{
			name:    "nil task",
			task:    nil,
			want:    nil,
			wantErr: false,
		},
		{
			name: "task without message",
			task: &a2a.Task{
				ID:        "task-1",
				ContextID: "context-1",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking},
			},
			want:    nil,
			wantErr: false,
		},
		{
			name: "requirements from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentRequirements(task.Status.Message, requirements)
				return task
			}(),
			want:    requirements,
			wantErr: false,
		},
		{
			name: "invalid requirements type",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				task.Status.Message.Metadata = map[string]interface{}{
					x402.MetadataKeyRequired: "invalid string",
				}
				return task
			}(),
			want:    nil,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ExtractPaymentRequirements(tt.task)
			if (err != nil) != tt.wantErr {
				t.Errorf("ExtractPaymentRequirements() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr {
				return
			}
			if tt.want == nil {
				if got != nil {
					t.Errorf("ExtractPaymentRequirements() = %v, want nil", got)
				}
				return
			}
			if got == nil {
				t.Errorf("ExtractPaymentRequirements() = nil, want %v", tt.want)
				return
			}
			if got.X402Version != tt.want.X402Version {
				t.Errorf("ExtractPaymentRequirements() X402Version = %v, want %v", got.X402Version, tt.want.X402Version)
			}
			if len(got.Accepts) != len(tt.want.Accepts) {
				t.Errorf("ExtractPaymentRequirements() Accepts length = %v, want %v", len(got.Accepts), len(tt.want.Accepts))
			}
		})
	}
}

func TestExtractPaymentReceipts(t *testing.T) {
	receipts := []*x402core.SettleResponse{
		{
			Success: true,
			Network: x402.NetworkBaseSepolia,
		},
		{
			Success: true,
			Network: "base",
		},
	}

	tests := []struct {
		name    string
		task    *a2a.Task
		want    []*x402core.SettleResponse
		wantErr bool
	}{
		{
			name:    "nil task",
			task:    nil,
			want:    []*x402core.SettleResponse{},
			wantErr: false,
		},
		{
			name: "task without message",
			task: &a2a.Task{
				ID:        "task-1",
				ContextID: "context-1",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking},
			},
			want:    []*x402core.SettleResponse{},
			wantErr: false,
		},
		{
			name: "receipts from task",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				SetPaymentReceipts(task.Status.Message, receipts)
				return task
			}(),
			want:    receipts,
			wantErr: false,
		},
		{
			name: "empty receipts",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				return task
			}(),
			want:    []*x402core.SettleResponse{},
			wantErr: false,
		},
		{
			name: "invalid receipt type",
			task: func() *a2a.Task {
				task := &a2a.Task{
					ID:        "task-1",
					ContextID: "context-1",
					Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
				}
				task.Status.Message.Metadata = map[string]interface{}{
					x402.MetadataKeyReceipts: []interface{}{"invalid string"},
				}
				return task
			}(),
			want:    nil,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ExtractPaymentReceipts(tt.task)
			if (err != nil) != tt.wantErr {
				t.Errorf("ExtractPaymentReceipts() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr {
				return
			}
			if len(got) != len(tt.want) {
				t.Errorf("ExtractPaymentReceipts() length = %v, want %v", len(got), len(tt.want))
				return
			}
			for i, receipt := range got {
				if receipt.Success != tt.want[i].Success {
					t.Errorf("ExtractPaymentReceipts() receipt[%d].Success = %v, want %v", i, receipt.Success, tt.want[i].Success)
				}
			}
		})
	}
}
