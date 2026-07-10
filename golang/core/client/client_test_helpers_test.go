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

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/google-agentic-commerce/a2a-x402/core/x402/state"
	x402types "github.com/x402-foundation/x402/go/types"
)

type mockTaskClient struct {
	sendMessageFunc func(ctx context.Context, message *a2a.MessageSendParams) (a2a.SendMessageResult, error)
	getTaskFunc     func(ctx context.Context, query *a2a.TaskQueryParams) (*a2a.Task, error)
	sendCalls       int
	getCalls        int
}

func (m *mockTaskClient) SendMessage(ctx context.Context, message *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
	m.sendCalls++
	return m.sendMessageFunc(ctx, message)
}

func (m *mockTaskClient) GetTask(ctx context.Context, query *a2a.TaskQueryParams) (*a2a.Task, error) {
	m.getCalls++
	return m.getTaskFunc(ctx, query)
}

type mockPaymentProcessor struct {
	processFunc func(ctx context.Context, taskID a2a.TaskID, required *x402types.PaymentRequired) (*a2a.Message, error)
	calls       int
}

func (m *mockPaymentProcessor) ProcessPaymentRequired(
	ctx context.Context,
	taskID a2a.TaskID,
	required *x402types.PaymentRequired,
) (*a2a.Message, error) {
	m.calls++
	return m.processFunc(ctx, taskID, required)
}

func newClientTestTask(id string, taskState a2a.TaskState, paymentStatus state.PaymentStatus) *a2a.Task {
	message := a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "status"})
	if paymentStatus != "" {
		state.SetPaymentStatus(message, paymentStatus)
	}
	return &a2a.Task{
		ID:        a2a.TaskID(id),
		ContextID: "context-" + id,
		Status: a2a.TaskStatus{
			State:   taskState,
			Message: message,
		},
	}
}

func newPaymentRequiredTask(id string) *a2a.Task {
	task := newClientTestTask(id, a2a.TaskStateInputRequired, state.PaymentRequired)
	_ = state.SetPaymentRequirements(task.Status.Message, &x402types.PaymentRequired{
		X402Version: 2,
		Resource:    &x402types.ResourceInfo{URL: "/resource"},
		Accepts: []x402types.PaymentRequirements{
			{Scheme: "exact", Network: "eip155:84532", Amount: "100"},
		},
	})
	return task
}
