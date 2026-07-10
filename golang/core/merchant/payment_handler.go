// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed on the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package merchant

import (
	"context"
	"fmt"
	"strings"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/a2aproject/a2a-go/a2asrv"
	"github.com/a2aproject/a2a-go/a2asrv/eventqueue"
	"github.com/google-agentic-commerce/a2a-x402/core/business"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
	"github.com/google-agentic-commerce/a2a-x402/core/x402/state"
	x402core "github.com/x402-foundation/x402/go"
	x402types "github.com/x402-foundation/x402/go/types"
)

func (o *BusinessOrchestrator) buildPaymentRequirements(
	ctx context.Context,
	paymentRequired *business.PaymentRequiredError,
) (*state.PaymentState, error) {
	if paymentRequired == nil || len(paymentRequired.Requirements) == 0 {
		return nil, fmt.Errorf("at least one payment requirement is required")
	}

	allRequirements := make([]x402types.PaymentRequirements, 0)
	var resourceInfo *x402types.ResourceInfo

	for _, serviceReq := range paymentRequired.Requirements {
		if serviceReq.Resource == "" {
			return nil, fmt.Errorf("payment resource is required")
		}

		candidateResource := &x402types.ResourceInfo{
			URL:         serviceReq.Resource,
			Description: serviceReq.Description,
			MimeType:    serviceReq.MimeType,
		}
		if resourceInfo == nil {
			resourceInfo = candidateResource
		} else if resourceInfo.URL != candidateResource.URL ||
			resourceInfo.Description != candidateResource.Description ||
			resourceInfo.MimeType != candidateResource.MimeType {
			return nil, fmt.Errorf("all payment options must describe the same resource")
		}

		for _, networkConfig := range o.networkConfigs {
			reqs, err := BuildPaymentRequirements(ctx, o.merchant, networkConfig, serviceReq)
			if err != nil {
				return nil, fmt.Errorf("failed to create payment requirement for network %s: %w", networkConfig.NetworkName, err)
			}

			for _, req := range reqs {
				allRequirements = append(allRequirements, *req)
			}
		}
	}

	return &state.PaymentState{
		Status: state.PaymentRequired,
		Requirements: &x402types.PaymentRequired{
			X402Version: x402pkg.X402Version,
			Error:       paymentRequired.Error(),
			Resource:    resourceInfo,
			Accepts:     allRequirements,
		},
	}, nil
}

func (o *BusinessOrchestrator) findMatchingRequirement(paymentState *state.PaymentState) (*x402types.PaymentRequirements, error) {
	if paymentState.Payload == nil {
		return nil, fmt.Errorf("payment payload is required")
	}
	if paymentState.Requirements == nil || len(paymentState.Requirements.Accepts) == 0 {
		return nil, fmt.Errorf("payment requirements are required")
	}
	if paymentState.Requirements.X402Version != x402pkg.X402Version {
		return nil, fmt.Errorf("unsupported payment requirements version: %d", paymentState.Requirements.X402Version)
	}
	if paymentState.Payload.X402Version != x402pkg.X402Version {
		return nil, fmt.Errorf("unsupported payment payload version: %d", paymentState.Payload.X402Version)
	}

	matchedRequirement := o.merchant.FindMatchingRequirements(
		paymentState.Requirements.Accepts,
		*paymentState.Payload,
	)
	if matchedRequirement == nil {
		return nil, fmt.Errorf("no matching payment requirement found for payload (accepted: scheme=%s, network=%s, amount=%s, asset=%s, payTo=%s)",
			paymentState.Payload.Accepted.Scheme,
			paymentState.Payload.Accepted.Network,
			paymentState.Payload.Accepted.Amount,
			paymentState.Payload.Accepted.Asset,
			paymentState.Payload.Accepted.PayTo)
	}

	return matchedRequirement, nil
}

func (o *BusinessOrchestrator) verifyPayment(
	ctx context.Context,
	paymentState *state.PaymentState,
) error {
	matchedRequirement, err := o.findMatchingRequirement(paymentState)
	if err != nil {
		return fmt.Errorf("failed to find matching requirement: %w", err)
	}

	verifyResponse, err := o.merchant.VerifyPayment(
		ctx,
		*paymentState.Payload,
		*matchedRequirement,
	)
	if err != nil {
		return fmt.Errorf("payment verification failed: %w", err)
	}
	if verifyResponse == nil {
		return fmt.Errorf("payment verification failed: empty verification response")
	}

	if !verifyResponse.IsValid {
		return fmt.Errorf("payment verification failed: %s, %s", verifyResponse.InvalidReason, verifyResponse.InvalidMessage)
	}

	return nil
}

func (o *BusinessOrchestrator) handlePaymentSubmitted(
	ctx context.Context,
	requestContext *a2asrv.RequestContext,
	task *a2a.Task,
	eventQueue eventqueue.Queue,
	paymentState *state.PaymentState,
) (*state.PaymentState, error) {
	if task.Status.State == a2a.TaskStateFailed || task.Status.State == a2a.TaskStateCompleted {
		updatedState, err := state.ExtractPaymentState(task, requestContext.Message)
		if err != nil {
			return nil, fmt.Errorf("failed to re-extract payment state: %w", err)
		}
		return updatedState, nil
	}

	if err := o.verifyPayment(ctx, paymentState); err != nil {
		verificationErr := fmt.Errorf("payment verification failed: %w", err)
		return o.failPayment(
			ctx,
			requestContext,
			task,
			eventQueue,
			paymentState,
			verificationErr,
			x402pkg.ErrorCodeInvalidSignature,
			nil,
		)
	}

	paymentState.Status = state.PaymentVerified
	if err := o.transitionToPaymentVerified(ctx, requestContext, task, eventQueue, paymentState); err != nil {
		return nil, fmt.Errorf("failed to record payment verified state: %w", err)
	}

	return &state.PaymentState{
		Status:       state.PaymentVerified,
		Requirements: paymentState.Requirements,
		Payload:      paymentState.Payload,
		Receipts:     paymentState.Receipts,
	}, nil
}

func (o *BusinessOrchestrator) handlePaymentVerified(
	ctx context.Context,
	requestContext *a2asrv.RequestContext,
	task *a2a.Task,
	eventQueue eventqueue.Queue,
	paymentState *state.PaymentState,
) (*state.PaymentState, error) {
	matchedRequirement, err := o.findMatchingRequirement(paymentState)
	if err != nil {
		return o.failPayment(ctx, requestContext, task, eventQueue, paymentState, err, x402pkg.ErrorCodeInvalidSignature, nil)
	}

	prompt := state.ExtractOriginalPrompt(task)
	if prompt == "" {
		return o.failPayment(
			ctx,
			requestContext,
			task,
			eventQueue,
			paymentState,
			fmt.Errorf("prompt is required: original prompt not found in task metadata"),
			x402pkg.ErrorCodeSettlementFailed,
			nil,
		)
	}

	businessResult, err := o.businessService.Execute(ctx, business.Request{
		Prompt:          prompt,
		PaymentVerified: true,
	})
	if err != nil {
		return o.failPayment(
			ctx,
			requestContext,
			task,
			eventQueue,
			paymentState,
			fmt.Errorf("business logic execution failed: %w", err),
			x402pkg.ErrorCodeSettlementFailed,
			nil,
		)
	}
	if businessResult == nil {
		return o.failPayment(
			ctx,
			requestContext,
			task,
			eventQueue,
			paymentState,
			fmt.Errorf("business logic execution failed: empty result"),
			x402pkg.ErrorCodeSettlementFailed,
			nil,
		)
	}

	settleResponse, err := o.settlePayment(ctx, paymentState, matchedRequirement)
	if err != nil {
		return o.failPayment(
			ctx,
			requestContext,
			task,
			eventQueue,
			paymentState,
			err,
			settlementErrorCode(settleResponse, err),
			settleResponse,
		)
	}

	return &state.PaymentState{
		Status:    state.PaymentCompleted,
		Message:   businessResult.Message,
		Receipts:  []*x402core.SettleResponse{settleResponse},
		Artifacts: businessResult.Artifacts,
	}, nil
}

func (o *BusinessOrchestrator) settlePayment(
	ctx context.Context,
	paymentState *state.PaymentState,
	matchedRequirement *x402types.PaymentRequirements,
) (*x402core.SettleResponse, error) {
	settleResponse, err := o.merchant.SettlePayment(
		ctx,
		*paymentState.Payload,
		*matchedRequirement,
	)
	if err != nil {
		return settleResponse, fmt.Errorf("payment settlement failed: %w", err)
	}
	if settleResponse == nil {
		return nil, fmt.Errorf("payment settlement failed: empty settlement response")
	}

	if !settleResponse.Success {
		return settleResponse, fmt.Errorf("payment settlement failed: %s", settleResponse.ErrorReason)
	}

	return settleResponse, nil
}

func (o *BusinessOrchestrator) failPayment(
	ctx context.Context,
	requestContext *a2asrv.RequestContext,
	task *a2a.Task,
	eventQueue eventqueue.Queue,
	paymentState *state.PaymentState,
	err error,
	errorCode string,
	receipt *x402core.SettleResponse,
) (*state.PaymentState, error) {
	receipt = normalizeFailureReceipt(paymentState, receipt, err)
	if transitionErr := o.transitionToFailed(ctx, requestContext, task, eventQueue, err, errorCode, receipt); transitionErr != nil {
		return nil, fmt.Errorf("failed to transition to failed state: %w", transitionErr)
	}

	receipts := append([]*x402core.SettleResponse{}, paymentState.Receipts...)
	receipts = append(receipts, receipt)
	return &state.PaymentState{Status: state.PaymentFailed, Receipts: receipts}, nil
}

func normalizeFailureReceipt(
	paymentState *state.PaymentState,
	receipt *x402core.SettleResponse,
	err error,
) *x402core.SettleResponse {
	if receipt == nil {
		receipt = &x402core.SettleResponse{Success: false}
	} else {
		copy := *receipt
		receipt = &copy
	}

	if receipt.ErrorReason == "" && err != nil {
		receipt.ErrorReason = err.Error()
	}
	if receipt.Network == "" && paymentState != nil && paymentState.Payload != nil {
		receipt.Network = x402core.Network(paymentState.Payload.Accepted.Network)
	}
	if receipt.Network == "" && paymentState != nil && paymentState.Requirements != nil && len(paymentState.Requirements.Accepts) > 0 {
		receipt.Network = x402core.Network(paymentState.Requirements.Accepts[0].Network)
	}
	return receipt
}

func settlementErrorCode(response *x402core.SettleResponse, err error) string {
	message := ""
	if response != nil {
		message = response.ErrorReason + " " + response.ErrorMessage
	}
	if err != nil {
		message += " " + err.Error()
	}
	if strings.Contains(strings.ToLower(message), "insufficient") {
		return x402pkg.ErrorCodeInsufficientFunds
	}
	return x402pkg.ErrorCodeSettlementFailed
}
