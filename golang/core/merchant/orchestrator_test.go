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

package merchant

import (
	"context"
	"errors"
	"testing"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/a2aproject/a2a-go/a2asrv"
	"github.com/google-agentic-commerce/a2a-x402/core/business"
	"github.com/google-agentic-commerce/a2a-x402/core/types"
	"github.com/google-agentic-commerce/a2a-x402/core/x402"
	x402state "github.com/google-agentic-commerce/a2a-x402/core/x402/state"
	x402core "github.com/x402-foundation/x402/go"
	x402pkg "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

type mockBusinessService struct {
	executeFunc func(ctx context.Context, request business.Request) (*business.Result, error)
}

func (m *mockBusinessService) Execute(ctx context.Context, request business.Request) (*business.Result, error) {
	if m.executeFunc != nil {
		return m.executeFunc(ctx, request)
	}
	if request.PaymentVerified {
		return &business.Result{Message: "Mock response"}, nil
	}
	requirements := business.ServiceRequirements{
		Price:             "1.00",
		Resource:          "/test",
		Description:       "Test service",
		MimeType:          "application/json",
		Scheme:            "exact",
		MaxTimeoutSeconds: 60,
	}
	return nil, business.NewPaymentRequiredError("Test service requires payment", requirements)
}

type MockResourceServer struct {
	BuildPaymentRequirementsFromConfigFunc func(ctx context.Context, config x402pkg.ResourceConfig) ([]x402types.PaymentRequirements, error)
	FindMatchingRequirementsFunc           func(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements
	VerifyPaymentFunc                      func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error)
	SettlePaymentFunc                      func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error)
}

func (m *MockResourceServer) BuildPaymentRequirementsFromConfig(ctx context.Context, config x402pkg.ResourceConfig) ([]x402types.PaymentRequirements, error) {
	if m.BuildPaymentRequirementsFromConfigFunc != nil {
		return m.BuildPaymentRequirementsFromConfigFunc(ctx, config)
	}
	return []x402types.PaymentRequirements{
		{
			Scheme:  "exact",
			Network: string(config.Network),
			PayTo:   config.PayTo,
			Asset:   "0x456",
		},
	}, nil
}

func (m *MockResourceServer) FindMatchingRequirements(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements {
	if m.FindMatchingRequirementsFunc != nil {
		return m.FindMatchingRequirementsFunc(accepts, payload)
	}
	if len(accepts) > 0 {
		return &accepts[0]
	}
	return nil
}

func (m *MockResourceServer) VerifyPayment(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error) {
	if m.VerifyPaymentFunc != nil {
		return m.VerifyPaymentFunc(ctx, payload, requirements)
	}
	return &x402core.VerifyResponse{IsValid: true, Payer: "0x789"}, nil
}

func (m *MockResourceServer) SettlePayment(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error) {
	if m.SettlePaymentFunc != nil {
		return m.SettlePaymentFunc(ctx, payload, requirements)
	}
	return &x402core.SettleResponse{Success: true, Network: x402.NetworkBaseSepolia}, nil
}

type MockExtensionChecker struct {
	ExtensionsFromFunc func(ctx context.Context) (*a2asrv.Extensions, bool)
}

func (m *MockExtensionChecker) ExtensionsFrom(ctx context.Context) (*a2asrv.Extensions, bool) {
	if m.ExtensionsFromFunc != nil {
		return m.ExtensionsFromFunc(ctx)
	}
	return a2asrv.ExtensionsFrom(ctx)
}

func newMockExtensionCheckerWithX402() *MockExtensionChecker {
	return &MockExtensionChecker{
		ExtensionsFromFunc: func(ctx context.Context) (*a2asrv.Extensions, bool) {
			headers := map[string][]string{
				"X-A2A-Extensions": {x402.X402ExtensionURI},
			}
			requestMeta := a2asrv.NewRequestMeta(headers)
			ctxWithMeta, _ := a2asrv.WithCallContext(context.Background(), requestMeta)
			exts, ok := a2asrv.ExtensionsFrom(ctxWithMeta)
			if !ok {
				return nil, false
			}
			return exts, true
		},
	}
}

type mockEventQueue struct {
	events []interface{}
}

func (m *mockEventQueue) Write(ctx context.Context, event a2a.Event) error {
	m.events = append(m.events, event)
	return nil
}

func (m *mockEventQueue) WriteVersioned(ctx context.Context, event a2a.Event, version a2a.TaskVersion) error {
	m.events = append(m.events, event)
	return nil
}

func (m *mockEventQueue) Read(ctx context.Context) (a2a.Event, a2a.TaskVersion, error) {
	if len(m.events) == 0 {
		return nil, 0, nil
	}
	event := m.events[0]
	m.events = m.events[1:]
	if e, ok := event.(a2a.Event); ok {
		return e, 0, nil
	}
	return nil, 0, nil
}

func (m *mockEventQueue) Close() error {
	return nil
}

func TestBusinessOrchestrator_ensureExtension(t *testing.T) {
	ctx := context.Background()
	mockService := &mockBusinessService{}
	mockQueue := &mockEventQueue{}

	tests := []struct {
		name           string
		checker        ExtensionChecker
		wantErr        bool
		expectedEvents int
	}{
		{
			name: "extension enabled",
			checker: &MockExtensionChecker{
				ExtensionsFromFunc: func(ctx context.Context) (*a2asrv.Extensions, bool) {
					// Create a context with x402 extension header
					headers := map[string][]string{
						"X-A2A-Extensions": {x402.X402ExtensionURI},
					}
					requestMeta := a2asrv.NewRequestMeta(headers)
					ctxWithMeta, _ := a2asrv.WithCallContext(context.Background(), requestMeta)
					exts, ok := a2asrv.ExtensionsFrom(ctxWithMeta)
					if !ok {
						return nil, false
					}
					return exts, true
				},
			},
			wantErr:        false,
			expectedEvents: 0,
		},
		{
			name: "extension missing",
			checker: &MockExtensionChecker{
				ExtensionsFromFunc: func(ctx context.Context) (*a2asrv.Extensions, bool) {
					return nil, false
				},
			},
			wantErr:        true,
			expectedEvents: 1,
		},
		{
			name: "extension not requested",
			checker: &MockExtensionChecker{
				ExtensionsFromFunc: func(ctx context.Context) (*a2asrv.Extensions, bool) {
					exts, ok := a2asrv.ExtensionsFrom(ctx)
					if ok {
						x402Ext := &a2a.AgentExtension{URI: x402.X402ExtensionURI}
						if !exts.Requested(x402Ext) {
							return exts, true
						}
					}
					headers := map[string][]string{
						"X-A2A-Extensions": {"https://other-extension.org/"},
					}
					requestMeta := a2asrv.NewRequestMeta(headers)
					ctxWithMeta, _ := a2asrv.WithCallContext(context.Background(), requestMeta)
					exts, ok = a2asrv.ExtensionsFrom(ctxWithMeta)
					if !ok {
						return nil, false
					}
					return exts, true
				},
			},
			wantErr:        true,
			expectedEvents: 1,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockQueue.events = nil
			mockMerchant := &MockResourceServer{}

			orchestrator := NewBusinessOrchestratorWithDeps(
				mockMerchant,
				mockService,
				[]types.NetworkConfig{
					{NetworkName: "eip155:84532", PayToAddress: "0x123"},
				},
				tt.checker,
			)

			task := &a2a.Task{
				ID:        "task-123",
				ContextID: "context-456",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
			}
			requestContext := &a2asrv.RequestContext{
				Message:    a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "test"}),
				StoredTask: task,
				TaskID:     "task-123",
				ContextID:  "context-456",
			}

			err := orchestrator.ensureExtension(ctx, requestContext, task, mockQueue)

			if tt.wantErr {
				if err == nil {
					t.Errorf("expected error but got nil")
				}
				if len(mockQueue.events) != tt.expectedEvents {
					t.Errorf("expected %d events, got %d", tt.expectedEvents, len(mockQueue.events))
				}
			} else {
				if err != nil {
					t.Errorf("unexpected error: %v", err)
				}
			}
		})
	}
}

func TestBusinessOrchestrator_Execute_PaymentFlow(t *testing.T) {
	ctx := context.Background()

	paymentRequirements := x402types.PaymentRequirements{
		Scheme:  "exact",
		Network: x402.NetworkBaseSepolia,
		PayTo:   "0x123",
		Asset:   "0x456",
	}

	paymentPayload := x402types.PaymentPayload{
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

	var verifyCalled, settleCalled, businessExecuteCalled bool
	artifact := &a2a.Artifact{
		Name:  "paid-result",
		Parts: []a2a.Part{a2a.DataPart{Data: map[string]any{"paid": true}}},
	}

	mockMerchant := &MockResourceServer{
		FindMatchingRequirementsFunc: func(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements {
			return &paymentRequirements
		},
		VerifyPaymentFunc: func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error) {
			verifyCalled = true
			return &x402core.VerifyResponse{IsValid: true, Payer: "0x789"}, nil
		},
		SettlePaymentFunc: func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error) {
			settleCalled = true
			return &x402core.SettleResponse{Success: true, Network: x402.NetworkBaseSepolia}, nil
		},
	}

	mockService := &mockBusinessService{
		executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
			businessExecuteCalled = true
			if !request.PaymentVerified {
				t.Fatal("business service was called without verified payment")
			}
			return &business.Result{
				Message:   "Business logic executed successfully",
				Artifacts: []*a2a.Artifact{artifact},
			}, nil
		},
	}

	mockQueue := &mockEventQueue{}
	mockExtensionChecker := newMockExtensionCheckerWithX402()

	orchestrator := NewBusinessOrchestratorWithDeps(
		mockMerchant,
		mockService,
		[]types.NetworkConfig{
			{NetworkName: "eip155:84532", PayToAddress: "0x123"},
		},
		mockExtensionChecker,
	)

	task := &a2a.Task{
		ID:        "task-123",
		ContextID: "context-456",
		Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
	}
	x402state.SetPaymentStatus(task.Status.Message, x402state.PaymentSubmitted)
	x402state.SetPaymentPayload(task.Status.Message, &paymentPayload)
	x402state.SetPaymentRequirements(task.Status.Message, &x402types.PaymentRequired{
		X402Version: x402.X402Version,
		Accepts:     []x402types.PaymentRequirements{paymentRequirements},
	})
	x402state.SetOriginalPrompt(task.Status.Message, "test prompt")

	message := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "Payment authorization provided"})
	x402state.SetPaymentStatus(message, x402state.PaymentSubmitted)
	x402state.SetPaymentPayload(message, &paymentPayload)

	requestContext := &a2asrv.RequestContext{
		Message:    message,
		StoredTask: task,
		TaskID:     "task-123",
		ContextID:  "context-456",
	}

	err := orchestrator.Execute(ctx, requestContext, mockQueue)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	if !verifyCalled {
		t.Error("verifyPayment was not called")
	}
	if !settleCalled {
		t.Error("settlePayment was not called")
	}
	if !businessExecuteCalled {
		t.Error("business service Execute was not called")
	}

	if task.Status.State != a2a.TaskStateCompleted {
		t.Errorf("expected task state to be Completed, got %v", task.Status.State)
	}

	if len(mockQueue.events) == 0 {
		t.Error("expected events to be written to queue")
	}
	var artifactEvent *a2a.TaskArtifactUpdateEvent
	for _, event := range mockQueue.events {
		if candidate, ok := event.(*a2a.TaskArtifactUpdateEvent); ok {
			artifactEvent = candidate
			break
		}
	}
	if artifactEvent == nil || artifactEvent.Artifact != artifact || artifact.ID == "" {
		t.Errorf("expected paid artifact event, got %#v", artifactEvent)
	}
}

func TestBusinessOrchestrator_Execute_DynamicPaymentFlow(t *testing.T) {
	ctx := context.Background()
	requirement := x402types.PaymentRequirements{
		Scheme:            "exact",
		Network:           x402.NetworkBaseSepolia,
		Asset:             "0x456",
		Amount:            "100",
		PayTo:             "0x123",
		MaxTimeoutSeconds: 60,
	}
	mockMerchant := &MockResourceServer{
		BuildPaymentRequirementsFromConfigFunc: func(ctx context.Context, config x402pkg.ResourceConfig) ([]x402types.PaymentRequirements, error) {
			return []x402types.PaymentRequirements{requirement}, nil
		},
		FindMatchingRequirementsFunc: func(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements {
			return &accepts[0]
		},
		VerifyPaymentFunc: func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error) {
			return &x402core.VerifyResponse{IsValid: true, Payer: "0xpayer"}, nil
		},
		SettlePaymentFunc: func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error) {
			return &x402core.SettleResponse{
				Success:     true,
				Payer:       "0xpayer",
				Transaction: "0xtx",
				Network:     x402.NetworkBaseSepolia,
			}, nil
		},
	}

	var calls []business.Request
	artifact := &a2a.Artifact{Name: "paid-output", Parts: []a2a.Part{a2a.TextPart{Text: "result"}}}
	mockService := &mockBusinessService{
		executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
			calls = append(calls, request)
			if !request.PaymentVerified {
				terms := business.ServiceRequirements{
					Price:             "1.00",
					Resource:          "/dynamic",
					Description:       "Dynamic paid service",
					MimeType:          "text/plain",
					Scheme:            "exact",
					MaxTimeoutSeconds: 60,
				}
				return nil, business.NewPaymentRequiredError("Payment required for dynamic service", terms)
			}
			return &business.Result{Message: "paid result", Artifacts: []*a2a.Artifact{artifact}}, nil
		},
	}
	mockQueue := &mockEventQueue{}
	orchestrator := NewBusinessOrchestratorWithDeps(
		mockMerchant,
		mockService,
		[]types.NetworkConfig{{NetworkName: x402.NetworkBaseSepolia, PayToAddress: "0x123"}},
		newMockExtensionCheckerWithX402(),
	)

	initialMessage := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "dynamic request"})
	initialContext := &a2asrv.RequestContext{
		Message:   initialMessage,
		TaskID:    "task-dynamic",
		ContextID: "context-dynamic",
	}
	if err := orchestrator.Execute(ctx, initialContext, mockQueue); err != nil {
		t.Fatalf("initial Execute() error = %v", err)
	}
	task := initialContext.StoredTask
	if task.Status.State != a2a.TaskStateInputRequired {
		t.Fatalf("initial task state = %v, want input-required", task.Status.State)
	}

	payload := &x402types.PaymentPayload{
		X402Version: x402.X402Version,
		Accepted:    requirement,
		Payload:     map[string]any{"signature": "0xabc"},
	}
	paymentMessage, err := x402state.EncodePaymentSubmission(task.ID, payload)
	if err != nil {
		t.Fatalf("EncodePaymentSubmission() error = %v", err)
	}
	paymentContext := &a2asrv.RequestContext{
		Message:    paymentMessage,
		StoredTask: task,
		TaskID:     task.ID,
		ContextID:  task.ContextID,
	}
	if err := orchestrator.Execute(ctx, paymentContext, mockQueue); err != nil {
		t.Fatalf("paid Execute() error = %v", err)
	}

	if len(calls) != 2 || calls[0].PaymentVerified || !calls[1].PaymentVerified {
		t.Fatalf("business calls = %#v, want unverified then verified", calls)
	}
	if calls[0].Prompt != "dynamic request" || calls[1].Prompt != "dynamic request" {
		t.Errorf("business prompts were not preserved: %#v", calls)
	}
	if task.Status.State != a2a.TaskStateCompleted {
		t.Errorf("final task state = %v, want completed", task.Status.State)
	}
	finalState, err := x402state.ExtractPaymentState(task, nil)
	if err != nil {
		t.Fatalf("ExtractPaymentState() error = %v", err)
	}
	if finalState.Status != x402state.PaymentCompleted || len(finalState.Receipts) != 1 {
		t.Errorf("final payment state = %#v", finalState)
	}
	if artifact.ID == "" {
		t.Error("paid artifact did not receive an ID")
	}
}

func TestBusinessOrchestrator_handlePaymentSubmitted(t *testing.T) {
	ctx := context.Background()

	paymentRequirements := x402types.PaymentRequirements{
		Scheme:  "exact",
		Network: x402.NetworkBaseSepolia,
		PayTo:   "0x123",
		Asset:   "0x456",
	}

	paymentPayload := x402types.PaymentPayload{
		X402Version: x402.X402Version,
		Accepted: x402types.PaymentRequirements{
			Scheme:  "exact",
			Network: x402.NetworkBaseSepolia,
			Amount:  "100",
			Asset:   "0x456",
			PayTo:   "0x123",
		},
	}

	tests := []struct {
		name           string
		verifyResponse *x402core.VerifyResponse
		verifyError    error
		x402Version    int
		wantVerify     bool
		wantErr        bool
		wantState      x402state.PaymentStatus
	}{
		{
			name:           "valid payment",
			verifyResponse: &x402core.VerifyResponse{IsValid: true, Payer: "0x789"},
			verifyError:    nil,
			wantVerify:     true,
			wantErr:        false,
			wantState:      x402state.PaymentVerified,
		},
		{
			name:           "invalid payment",
			verifyResponse: &x402core.VerifyResponse{IsValid: false, InvalidReason: "insufficient_funds"},
			verifyError:    nil,
			wantVerify:     true,
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
		},
		{
			name:           "verification error",
			verifyResponse: nil,
			verifyError:    errors.New("verification failed"),
			wantVerify:     true,
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
		},
		{
			name:           "empty verification response",
			verifyResponse: nil,
			verifyError:    nil,
			wantVerify:     true,
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
		},
		{
			name:        "v1 payload is rejected",
			x402Version: 1,
			wantVerify:  false,
			wantErr:     false,
			wantState:   x402state.PaymentFailed,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			verifyCalled := false
			mockMerchant := &MockResourceServer{
				FindMatchingRequirementsFunc: func(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements {
					return &paymentRequirements
				},
				VerifyPaymentFunc: func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.VerifyResponse, error) {
					verifyCalled = true
					return tt.verifyResponse, tt.verifyError
				},
			}

			mockService := &mockBusinessService{}
			mockQueue := &mockEventQueue{}
			mockExtensionChecker := newMockExtensionCheckerWithX402()

			orchestrator := NewBusinessOrchestratorWithDeps(
				mockMerchant,
				mockService,
				[]types.NetworkConfig{
					{NetworkName: "eip155:84532", PayToAddress: "0x123"},
				},
				mockExtensionChecker,
			)

			task := &a2a.Task{
				ID:        "task-123",
				ContextID: "context-456",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
			}
			testPayload := paymentPayload
			if tt.x402Version != 0 {
				testPayload.X402Version = tt.x402Version
			}
			paymentState := &x402state.PaymentState{
				Status:  x402state.PaymentSubmitted,
				Payload: &testPayload,
				Requirements: &x402types.PaymentRequired{
					X402Version: x402.X402Version,
					Accepts:     []x402types.PaymentRequirements{paymentRequirements},
				},
			}

			requestContext := &a2asrv.RequestContext{
				Message:    a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "test"}),
				StoredTask: task,
				TaskID:     "task-123",
				ContextID:  "context-456",
			}

			resultState, err := orchestrator.handlePaymentSubmitted(ctx, requestContext, task, mockQueue, paymentState)

			if (err != nil) != tt.wantErr {
				t.Errorf("error = %v, wantErr %v", err, tt.wantErr)
			}
			if verifyCalled != tt.wantVerify {
				t.Errorf("VerifyPayment called = %v, want %v", verifyCalled, tt.wantVerify)
			}
			if err == nil && resultState.Status != tt.wantState {
				t.Errorf("expected payment state %v, got %v", tt.wantState, resultState.Status)
			}
			if tt.wantState == x402state.PaymentFailed {
				if task.Status.State != a2a.TaskStateFailed {
					t.Errorf("expected task state to be Failed, got %v", task.Status.State)
				}
				status, statusErr := x402state.ExtractPaymentStatusFromTask(task)
				if statusErr != nil || status != x402state.PaymentFailed {
					t.Errorf("payment status = %v, error = %v", status, statusErr)
				}
				if len(resultState.Receipts) != 1 || resultState.Receipts[0].Network != x402.NetworkBaseSepolia {
					t.Errorf("expected one failed receipt on %s, got %#v", x402.NetworkBaseSepolia, resultState.Receipts)
				}
				if got := task.Status.Message.Metadata[x402.MetadataKeyError]; got != x402.ErrorCodeInvalidSignature {
					t.Errorf("payment error code = %v, want %s", got, x402.ErrorCodeInvalidSignature)
				}
			}
		})
	}
}

func TestBusinessOrchestrator_Execute_MalformedPaymentReturnsPaymentFailed(t *testing.T) {
	ctx := context.Background()
	serviceCalled := false
	orchestrator := NewBusinessOrchestratorWithDeps(
		&MockResourceServer{},
		&mockBusinessService{executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
			serviceCalled = true
			return &business.Result{Message: "unexpected"}, nil
		}},
		[]types.NetworkConfig{{NetworkName: x402.NetworkBaseSepolia, PayToAddress: "0x123"}},
		newMockExtensionCheckerWithX402(),
	)

	task := &a2a.Task{
		ID:        "task-malformed",
		ContextID: "context-malformed",
		Status: a2a.TaskStatus{
			State:   a2a.TaskStateWorking,
			Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "Payment required"}),
		},
	}
	x402state.SetPaymentStatus(task.Status.Message, x402state.PaymentRequired)
	if err := x402state.SetPaymentRequirements(task.Status.Message, &x402types.PaymentRequired{
		X402Version: x402.X402Version,
		Accepts: []x402types.PaymentRequirements{
			{Scheme: "exact", Network: x402.NetworkBaseSepolia, Amount: "100"},
		},
	}); err != nil {
		t.Fatalf("SetPaymentRequirements() error = %v", err)
	}

	message := a2a.NewMessageForTask(
		a2a.MessageRoleUser,
		a2a.TaskInfo{TaskID: task.ID, ContextID: task.ContextID},
		a2a.TextPart{Text: "Payment authorization provided"},
	)
	message.Metadata = map[string]any{
		x402.MetadataKeyStatus:  x402state.PaymentSubmitted.String(),
		x402.MetadataKeyPayload: "malformed",
	}
	requestContext := &a2asrv.RequestContext{
		Message:    message,
		StoredTask: task,
		TaskID:     task.ID,
		ContextID:  task.ContextID,
	}
	mockQueue := &mockEventQueue{}

	if err := orchestrator.Execute(ctx, requestContext, mockQueue); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if serviceCalled {
		t.Error("business service must not run for malformed payment")
	}
	status, err := x402state.ExtractPaymentStatusFromTask(task)
	if err != nil || status != x402state.PaymentFailed {
		t.Errorf("payment status = %v, error = %v", status, err)
	}
	if got := task.Status.Message.Metadata[x402.MetadataKeyError]; got != x402.ErrorCodeInvalidSignature {
		t.Errorf("payment error code = %v", got)
	}
	receipts, err := x402state.ExtractPaymentReceipts(task)
	if err != nil {
		t.Fatalf("ExtractPaymentReceipts() error = %v", err)
	}
	if len(receipts) != 1 || receipts[0].Network != x402.NetworkBaseSepolia {
		t.Errorf("failed receipt = %#v", receipts)
	}
}

func TestBusinessOrchestrator_Execute_MissingSubmittedPayloadReturnsPaymentFailed(t *testing.T) {
	ctx := context.Background()
	serviceCalled := false
	orchestrator := NewBusinessOrchestratorWithDeps(
		&MockResourceServer{},
		&mockBusinessService{executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
			serviceCalled = true
			return &business.Result{Message: "unexpected"}, nil
		}},
		[]types.NetworkConfig{{NetworkName: x402.NetworkBaseSepolia, PayToAddress: "0x123"}},
		newMockExtensionCheckerWithX402(),
	)

	task := &a2a.Task{
		ID:        "task-missing-payload",
		ContextID: "context-missing-payload",
		Status: a2a.TaskStatus{
			State:   a2a.TaskStateWorking,
			Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: "Payment required"}),
		},
	}
	x402state.SetPaymentStatus(task.Status.Message, x402state.PaymentRequired)
	if err := x402state.SetPaymentRequirements(task.Status.Message, &x402types.PaymentRequired{
		X402Version: x402.X402Version,
		Accepts: []x402types.PaymentRequirements{
			{Scheme: "exact", Network: x402.NetworkBaseSepolia, Amount: "100"},
		},
	}); err != nil {
		t.Fatalf("SetPaymentRequirements() error = %v", err)
	}

	message := a2a.NewMessageForTask(
		a2a.MessageRoleUser,
		a2a.TaskInfo{TaskID: task.ID, ContextID: task.ContextID},
		a2a.TextPart{Text: "Payment authorization provided"},
	)
	x402state.SetPaymentStatus(message, x402state.PaymentSubmitted)
	requestContext := &a2asrv.RequestContext{
		Message:    message,
		StoredTask: task,
		TaskID:     task.ID,
		ContextID:  task.ContextID,
	}

	if err := orchestrator.Execute(ctx, requestContext, &mockEventQueue{}); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if serviceCalled {
		t.Error("business service must not run when a submitted payment has no payload")
	}
	status, err := x402state.ExtractPaymentStatusFromTask(task)
	if err != nil || status != x402state.PaymentFailed {
		t.Errorf("payment status = %v, error = %v", status, err)
	}
	if got := task.Status.Message.Metadata[x402.MetadataKeyError]; got != x402.ErrorCodeInvalidSignature {
		t.Errorf("payment error code = %v", got)
	}
}

func TestBusinessOrchestrator_handlePaymentVerified(t *testing.T) {
	ctx := context.Background()

	paymentRequirements := x402types.PaymentRequirements{
		Scheme:  "exact",
		Network: x402.NetworkBaseSepolia,
		PayTo:   "0x123",
		Asset:   "0x456",
	}

	paymentPayload := x402types.PaymentPayload{
		X402Version: x402.X402Version,
		Accepted: x402types.PaymentRequirements{
			Scheme:  "exact",
			Network: x402.NetworkBaseSepolia,
			Amount:  "100",
			Asset:   "0x456",
			PayTo:   "0x123",
		},
	}

	tests := []struct {
		name           string
		businessError  error
		settleResponse *x402core.SettleResponse
		settleError    error
		wantErr        bool
		wantState      x402state.PaymentStatus
		wantErrorCode  string
		businessCalled bool
		settleCalled   bool
	}{
		{
			name:           "successful flow",
			businessError:  nil,
			settleResponse: &x402core.SettleResponse{Success: true, Network: x402.NetworkBaseSepolia},
			settleError:    nil,
			wantErr:        false,
			wantState:      x402state.PaymentCompleted,
			businessCalled: true,
			settleCalled:   true,
		},
		{
			name:           "business execution fails",
			businessError:  errors.New("business logic error"),
			settleResponse: nil,
			settleError:    nil,
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
			wantErrorCode:  x402.ErrorCodeSettlementFailed,
			businessCalled: true,
			settleCalled:   false,
		},
		{
			name:          "settlement fails",
			businessError: nil,
			settleResponse: &x402core.SettleResponse{
				Success:     false,
				ErrorReason: "settlement failed",
				Payer:       "0xpayer",
				Transaction: "0xtx",
				Network:     x402.NetworkBaseSepolia,
			},
			settleError:    nil,
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
			wantErrorCode:  x402.ErrorCodeSettlementFailed,
			businessCalled: true,
			settleCalled:   true,
		},
		{
			name:           "settlement error",
			businessError:  nil,
			settleResponse: nil,
			settleError:    errors.New("settlement error"),
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
			wantErrorCode:  x402.ErrorCodeSettlementFailed,
			businessCalled: true,
			settleCalled:   true,
		},
		{
			name: "settlement response with error",
			settleResponse: &x402core.SettleResponse{
				Success:     false,
				ErrorReason: "facilitator rejected settlement",
				Payer:       "0xerrorpayer",
				Transaction: "0xerrortx",
				Network:     x402.NetworkBaseSepolia,
			},
			settleError:    errors.New("facilitator error"),
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
			wantErrorCode:  x402.ErrorCodeSettlementFailed,
			businessCalled: true,
			settleCalled:   true,
		},
		{
			name:           "insufficient funds",
			businessError:  nil,
			settleResponse: &x402core.SettleResponse{Success: false, ErrorReason: "insufficient funds"},
			settleError:    nil,
			wantErr:        false,
			wantState:      x402state.PaymentFailed,
			wantErrorCode:  x402.ErrorCodeInsufficientFunds,
			businessCalled: true,
			settleCalled:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var businessCalled, settleCalled bool

			mockMerchant := &MockResourceServer{
				FindMatchingRequirementsFunc: func(accepts []x402types.PaymentRequirements, payload x402types.PaymentPayload) *x402types.PaymentRequirements {
					return &paymentRequirements
				},
				SettlePaymentFunc: func(ctx context.Context, payload x402types.PaymentPayload, requirements x402types.PaymentRequirements) (*x402core.SettleResponse, error) {
					settleCalled = true
					return tt.settleResponse, tt.settleError
				},
			}

			mockService := &mockBusinessService{
				executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
					businessCalled = true
					if tt.businessError != nil {
						return nil, tt.businessError
					}
					return &business.Result{Message: "result"}, nil
				},
			}

			mockExtensionChecker := newMockExtensionCheckerWithX402()

			orchestrator := NewBusinessOrchestratorWithDeps(
				mockMerchant,
				mockService,
				[]types.NetworkConfig{
					{NetworkName: "eip155:84532", PayToAddress: "0x123"},
				},
				mockExtensionChecker,
			)

			task := &a2a.Task{
				ID:        "task-123",
				ContextID: "context-456",
				Status:    a2a.TaskStatus{State: a2a.TaskStateWorking, Message: a2a.NewMessage(a2a.MessageRoleAgent, a2a.TextPart{Text: ""})},
			}
			x402state.SetOriginalPrompt(task.Status.Message, "test prompt")

			paymentState := &x402state.PaymentState{
				Status:  x402state.PaymentVerified,
				Payload: &paymentPayload,
				Requirements: &x402types.PaymentRequired{
					X402Version: x402.X402Version,
					Accepts:     []x402types.PaymentRequirements{paymentRequirements},
				},
			}
			requestContext := &a2asrv.RequestContext{
				Message:    a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "Payment authorization provided"}),
				StoredTask: task,
				TaskID:     task.ID,
				ContextID:  task.ContextID,
			}
			mockQueue := &mockEventQueue{}

			resultState, err := orchestrator.handlePaymentVerified(ctx, requestContext, task, mockQueue, paymentState)

			if (err != nil) != tt.wantErr {
				t.Errorf("error = %v, wantErr %v", err, tt.wantErr)
			}
			if err == nil && resultState.Status != tt.wantState {
				t.Errorf("expected payment state %v, got %v", tt.wantState, resultState.Status)
			}
			if tt.wantState == x402state.PaymentFailed && task.Status.State != a2a.TaskStateFailed {
				t.Errorf("expected failed task, got %v", task.Status.State)
			}
			if tt.wantErrorCode != "" {
				if got := task.Status.Message.Metadata[x402.MetadataKeyError]; got != tt.wantErrorCode {
					t.Errorf("payment error code = %v, want %s", got, tt.wantErrorCode)
				}
				if x402state.ExtractMessageText(task.Status.Message) == "" {
					t.Error("payment failure message must contain the reason")
				}
			}
			if tt.wantState == x402state.PaymentFailed && tt.settleResponse != nil && tt.settleResponse.Payer != "" {
				if len(resultState.Receipts) != 1 {
					t.Fatalf("expected one failed receipt, got %d", len(resultState.Receipts))
				}
				receipt := resultState.Receipts[0]
				if receipt.Payer != tt.settleResponse.Payer || receipt.Transaction != tt.settleResponse.Transaction || receipt.Network != tt.settleResponse.Network {
					t.Errorf("settlement receipt was not preserved: %#v", receipt)
				}
			}

			if businessCalled != tt.businessCalled {
				t.Errorf("business service called = %v, want %v", businessCalled, tt.businessCalled)
			}
			if settleCalled != tt.settleCalled {
				t.Errorf("settle payment called = %v, want %v", settleCalled, tt.settleCalled)
			}
		})
	}
}

func TestBusinessOrchestrator_Execute_InitialRequest(t *testing.T) {
	ctx := context.Background()
	var serviceCalls []business.Request

	mockMerchant := &MockResourceServer{
		BuildPaymentRequirementsFromConfigFunc: func(ctx context.Context, config x402pkg.ResourceConfig) ([]x402types.PaymentRequirements, error) {
			return []x402types.PaymentRequirements{
				{
					Scheme:  "exact",
					Network: string(config.Network),
					PayTo:   config.PayTo,
					Asset:   "0x456",
				},
			}, nil
		},
	}

	mockService := &mockBusinessService{
		executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
			serviceCalls = append(serviceCalls, request)
			requirements := business.ServiceRequirements{
				Price:             "1.00",
				Resource:          "/test",
				Description:       "Test service",
				MimeType:          "application/json",
				Scheme:            "exact",
				MaxTimeoutSeconds: 60,
			}
			return nil, business.NewPaymentRequiredError("Test service requires payment", requirements)
		},
	}
	mockQueue := &mockEventQueue{}
	mockExtensionChecker := newMockExtensionCheckerWithX402()

	orchestrator := NewBusinessOrchestratorWithDeps(
		mockMerchant,
		mockService,
		[]types.NetworkConfig{
			{NetworkName: "eip155:84532", PayToAddress: "0x123"},
		},
		mockExtensionChecker,
	)

	// Create initial request without payment state
	message := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "I want to use the service"})
	requestContext := &a2asrv.RequestContext{
		Message:   message,
		TaskID:    "task-123",
		ContextID: "context-456",
	}

	err := orchestrator.Execute(ctx, requestContext, mockQueue)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	// Verify task was created
	if requestContext.StoredTask == nil {
		t.Error("expected task to be created")
	}

	// Verify payment required state
	paymentState, err := x402state.ExtractPaymentState(requestContext.StoredTask, message)
	if err != nil {
		t.Fatalf("failed to extract payment state: %v", err)
	}

	if paymentState.Status != x402state.PaymentRequired {
		t.Errorf("expected payment state to be PaymentRequired, got %v", paymentState.Status)
	}

	if paymentState.Requirements == nil || len(paymentState.Requirements.Accepts) == 0 {
		t.Error("expected payment requirements to be set")
	}
	if paymentState.Requirements.X402Version != x402.X402Version {
		t.Errorf("x402 version = %d, want %d", paymentState.Requirements.X402Version, x402.X402Version)
	}
	if paymentState.Requirements.Resource == nil || paymentState.Requirements.Resource.URL != "/test" {
		t.Errorf("expected v2 resource at top level, got %#v", paymentState.Requirements.Resource)
	}
	for _, accepted := range paymentState.Requirements.Accepts {
		if _, ok := accepted.Extra["resource"]; ok {
			t.Errorf("v2 resource must not be stored in requirement extra: %#v", accepted.Extra)
		}
	}
	if paymentState.Requirements.Error != "Test service requires payment" {
		t.Errorf("payment error message = %q", paymentState.Requirements.Error)
	}
	if len(serviceCalls) != 1 || serviceCalls[0].PaymentVerified {
		t.Errorf("initial business calls = %#v, want one unverified call", serviceCalls)
	}

	// Verify event was written
	if len(mockQueue.events) == 0 {
		t.Error("expected events to be written to queue")
	}
}

func TestBusinessOrchestrator_Execute_FreeRequest(t *testing.T) {
	ctx := context.Background()
	artifact := &a2a.Artifact{
		Name:  "free-result",
		Parts: []a2a.Part{a2a.DataPart{Data: map[string]any{"value": "free"}}},
	}
	mockService := &mockBusinessService{
		executeFunc: func(ctx context.Context, request business.Request) (*business.Result, error) {
			if request.PaymentVerified {
				t.Fatal("free request must not be marked payment verified")
			}
			return &business.Result{
				Message:   "free result",
				Artifacts: []*a2a.Artifact{artifact},
			}, nil
		},
	}
	mockQueue := &mockEventQueue{}
	orchestrator := NewBusinessOrchestratorWithDeps(
		&MockResourceServer{},
		mockService,
		[]types.NetworkConfig{{NetworkName: x402.NetworkBaseSepolia, PayToAddress: "0x123"}},
		newMockExtensionCheckerWithX402(),
	)

	message := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "free request"})
	requestContext := &a2asrv.RequestContext{
		Message:   message,
		TaskID:    "task-free",
		ContextID: "context-free",
	}

	if err := orchestrator.Execute(ctx, requestContext, mockQueue); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if requestContext.StoredTask.Status.State != a2a.TaskStateCompleted {
		t.Errorf("task state = %v, want completed", requestContext.StoredTask.Status.State)
	}
	status, err := x402state.ExtractPaymentStatusFromTask(requestContext.StoredTask)
	if err != nil {
		t.Fatalf("ExtractPaymentStatusFromTask() error = %v", err)
	}
	if status != "" {
		t.Errorf("free request unexpectedly has payment status %q", status)
	}

	var artifactEvent *a2a.TaskArtifactUpdateEvent
	for _, event := range mockQueue.events {
		if candidate, ok := event.(*a2a.TaskArtifactUpdateEvent); ok {
			artifactEvent = candidate
			break
		}
	}
	if artifactEvent == nil || artifactEvent.Artifact != artifact || artifact.ID == "" {
		t.Errorf("expected artifact event with assigned ID, got %#v", artifactEvent)
	}
}
