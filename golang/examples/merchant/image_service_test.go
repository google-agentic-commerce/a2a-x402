package main

import (
	"context"
	"errors"
	"testing"

	"github.com/google-agentic-commerce/a2a-x402/core/business"
)

func TestImageServiceRequestsPaymentBeforeGeneration(t *testing.T) {
	service := &ImageService{}
	_, err := service.Execute(context.Background(), business.Request{Prompt: "a sunset"})
	if err == nil {
		t.Fatal("Execute() error = nil, want payment required")
	}

	var paymentRequired *business.PaymentRequiredError
	if !errors.As(err, &paymentRequired) {
		t.Fatalf("Execute() error = %T, want *business.PaymentRequiredError", err)
	}
	if len(paymentRequired.Requirements) != 1 {
		t.Fatalf("payment requirements = %d, want 1", len(paymentRequired.Requirements))
	}
	requirements := paymentRequired.Requirements[0]
	if requirements.Resource != "/generate-image" || requirements.MimeType != "image/png" {
		t.Errorf("payment requirements = %#v", requirements)
	}
}
