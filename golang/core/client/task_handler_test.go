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
	"time"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/x402/state"
	x402types "github.com/x402-foundation/x402/go/types"
)

func TestWaitForCompletionRejectsDirectMessage(t *testing.T) {
	a2aClient := &mockTaskClient{sendMessageFunc: func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
		return a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "done"}), nil
	}}
	client := &Client{client: a2aClient}

	_, err := client.WaitForCompletion(context.Background(), "request")
	if err == nil || !strings.Contains(err.Error(), "direct message") {
		t.Fatalf("error = %v", err)
	}
}

func TestWaitForCompletionWaitsForOrdinaryWorkingTask(t *testing.T) {
	working := newClientTestTask("working-flow", a2a.TaskStateWorking, "")
	completed := newClientTestTask("working-flow", a2a.TaskStateCompleted, "")
	a2aClient := &mockTaskClient{
		sendMessageFunc: func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
			return working, nil
		},
		getTaskFunc: func(context.Context, *a2a.TaskQueryParams) (*a2a.Task, error) {
			return completed, nil
		},
	}
	client := &Client{client: a2aClient, pollInterval: time.Nanosecond}

	got, err := client.WaitForCompletion(context.Background(), "request")
	if err != nil || got != completed {
		t.Fatalf("task = %#v, error = %v", got, err)
	}
	if a2aClient.sendCalls != 1 || a2aClient.getCalls != 1 {
		t.Fatalf("send calls = %d, get calls = %d", a2aClient.sendCalls, a2aClient.getCalls)
	}
}

func TestWaitForCompletionDoesNotRepeatPendingPayment(t *testing.T) {
	required := newPaymentRequiredTask("paid-flow")
	completed := newClientTestTask("paid-flow", a2a.TaskStateCompleted, state.PaymentCompleted)
	processor := &mockPaymentProcessor{processFunc: func(context.Context, a2a.TaskID, *x402types.PaymentRequired) (*a2a.Message, error) {
		return a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "payment"}), nil
	}}

	a2aClient := &mockTaskClient{}
	a2aClient.sendMessageFunc = func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
		if a2aClient.sendCalls <= 2 {
			return required, nil
		}
		t.Fatalf("unexpected repeated payment submission: send call %d", a2aClient.sendCalls)
		return nil, nil
	}
	a2aClient.getTaskFunc = func(context.Context, *a2a.TaskQueryParams) (*a2a.Task, error) {
		if a2aClient.getCalls == 1 {
			return required, nil
		}
		return completed, nil
	}

	client := &Client{
		x402Client:   processor,
		client:       a2aClient,
		pollInterval: time.Nanosecond,
	}
	got, err := client.WaitForCompletion(context.Background(), "request")
	if err != nil || got != completed {
		t.Fatalf("task = %#v, error = %v", got, err)
	}
	if processor.calls != 1 || a2aClient.sendCalls != 2 || a2aClient.getCalls != 2 {
		t.Fatalf("processor calls = %d, send calls = %d, get calls = %d", processor.calls, a2aClient.sendCalls, a2aClient.getCalls)
	}
}

func TestWaitForCompletionHonorsCancellation(t *testing.T) {
	working := newClientTestTask("cancel", a2a.TaskStateWorking, "")
	a2aClient := &mockTaskClient{sendMessageFunc: func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
		return working, nil
	}}
	client := &Client{client: a2aClient, pollInterval: time.Hour}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := client.WaitForCompletion(ctx, "request")
	if err == nil || !strings.Contains(err.Error(), context.Canceled.Error()) {
		t.Fatalf("error = %v", err)
	}
}
