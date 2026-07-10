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
	"errors"
	"strings"
	"testing"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/x402/state"
	x402types "github.com/x402-foundation/x402/go/types"
)

func TestProcessPaymentStateWaitsForOrdinaryWorkingTask(t *testing.T) {
	task := newClientTestTask("working", a2a.TaskStateWorking, "")
	got, submitted, err := (&Client{}).processPaymentState(context.Background(), task, true)
	if err != nil || got != task || submitted {
		t.Fatalf("task = %#v, submitted = %v, error = %v", got, submitted, err)
	}
}

func TestProcessPaymentStateRejectsNilTask(t *testing.T) {
	_, _, err := (&Client{}).processPaymentState(context.Background(), nil, true)
	if err == nil || !strings.Contains(err.Error(), "task is required") {
		t.Fatalf("error = %v", err)
	}
}

func TestProcessPaymentStateReturnsPaymentFailure(t *testing.T) {
	task := newClientTestTask("failed", a2a.TaskStateFailed, state.PaymentFailed)
	task.Status.Message = a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "insufficient funds"})
	state.SetPaymentStatus(task.Status.Message, state.PaymentFailed)

	_, _, err := (&Client{}).processPaymentState(context.Background(), task, true)
	if err == nil || !strings.Contains(err.Error(), "payment failed: insufficient funds") {
		t.Fatalf("error = %v", err)
	}
}

func TestProcessPaymentStateSubmitsAtMostWhenAllowed(t *testing.T) {
	task := newPaymentRequiredTask("required")
	processor := &mockPaymentProcessor{processFunc: func(
		context.Context,
		a2a.TaskID,
		*x402types.PaymentRequired,
	) (*a2a.Message, error) {
		return a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "payment"}), nil
	}}
	client := &Client{x402Client: processor}

	got, submitted, err := client.processPaymentState(context.Background(), task, false)
	if err != nil || got != task || submitted {
		t.Fatalf("task = %#v, submitted = %v, error = %v", got, submitted, err)
	}
	if processor.calls != 0 {
		t.Fatal("payment processor was called while submission was disabled")
	}
}

func TestProcessPaymentStateSubmitsPayment(t *testing.T) {
	task := newPaymentRequiredTask("submit")
	completed := newClientTestTask("submit", a2a.TaskStateCompleted, state.PaymentCompleted)
	processor := &mockPaymentProcessor{processFunc: func(context.Context, a2a.TaskID, *x402types.PaymentRequired) (*a2a.Message, error) {
		return a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "payment"}), nil
	}}
	a2aClient := &mockTaskClient{sendMessageFunc: func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
		return completed, nil
	}}
	client := &Client{x402Client: processor, client: a2aClient}

	got, submitted, err := client.processPaymentState(context.Background(), task, true)
	if err != nil || got != completed || !submitted {
		t.Fatalf("task = %#v, submitted = %v, error = %v", got, submitted, err)
	}
	if processor.calls != 1 || a2aClient.sendCalls != 1 {
		t.Fatalf("processor calls = %d, send calls = %d", processor.calls, a2aClient.sendCalls)
	}
}

func TestProcessPaymentStateHandlesSubmissionErrors(t *testing.T) {
	task := newPaymentRequiredTask("errors")

	t.Run("payment creation", func(t *testing.T) {
		client := &Client{x402Client: &mockPaymentProcessor{processFunc: func(context.Context, a2a.TaskID, *x402types.PaymentRequired) (*a2a.Message, error) {
			return nil, errors.New("signing failed")
		}}}
		_, _, err := client.processPaymentState(context.Background(), task, true)
		if err == nil || !strings.Contains(err.Error(), "signing failed") {
			t.Fatalf("error = %v", err)
		}
	})

	t.Run("direct message response", func(t *testing.T) {
		client := &Client{
			x402Client: &mockPaymentProcessor{processFunc: func(context.Context, a2a.TaskID, *x402types.PaymentRequired) (*a2a.Message, error) {
				return a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "payment"}), nil
			}},
			client: &mockTaskClient{sendMessageFunc: func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
				return a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "unexpected"}), nil
			}},
		}
		_, submitted, err := client.processPaymentState(context.Background(), task, true)
		if err == nil || !submitted || !strings.Contains(err.Error(), "direct message") {
			t.Fatalf("submitted = %v, error = %v", submitted, err)
		}
	})
}
