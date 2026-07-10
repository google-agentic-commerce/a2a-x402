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

// Package business defines the interfaces and types that merchants must implement
// to integrate their business services with the x402 payment framework.
// These interfaces allow developers to implement custom business logic while
// the framework handles payment verification and settlement.
package business

import (
	"context"

	"github.com/a2aproject/a2a-go/a2a"
)

// Request describes a business invocation. Services are called once before
// payment and again after the submitted payment has been verified.
type Request struct {
	Prompt          string
	PaymentVerified bool
}

// Result contains the business output that will be returned with the A2A task.
type Result struct {
	Message   string
	Artifacts []*a2a.Artifact
}

type BusinessService interface {
	Execute(ctx context.Context, request Request) (*Result, error)
}

// PaymentRequiredError is returned by a service when the current request must
// be paid before execution can continue.
type PaymentRequiredError struct {
	Message      string
	Requirements []ServiceRequirements
}

func NewPaymentRequiredError(message string, requirements ...ServiceRequirements) *PaymentRequiredError {
	return &PaymentRequiredError{
		Message:      message,
		Requirements: requirements,
	}
}

func (e *PaymentRequiredError) Error() string {
	if e == nil || e.Message == "" {
		return "payment required"
	}
	return e.Message
}

type ServiceRequirements struct {
	// Price is the payment amount required for the service (as a string, e.g., "1", "0.5")
	Price string

	// Resource is the resource identifier or URL associated with this service
	Resource string

	// Description is a human-readable description of the service
	Description string

	// MimeType is the MIME type of the resource (e.g., "application/json", "image/png")
	MimeType string

	// Scheme is the payment scheme. This implementation currently registers "exact".
	Scheme string

	// MaxTimeoutSeconds is the maximum time in seconds before payment expires
	MaxTimeoutSeconds int
}
