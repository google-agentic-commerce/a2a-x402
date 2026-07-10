package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"log"
	"os"

	"github.com/a2aproject/a2a-go/a2a"
	"google.golang.org/genai"

	"github.com/google-agentic-commerce/a2a-x402/core/business"
)

type ImageService struct {
	client *genai.Client
}

func NewImageService() *ImageService {
	ctx := context.Background()
	client, err := genai.NewClient(ctx, nil)
	if err != nil {
		return &ImageService{client: nil}
	}

	return &ImageService{
		client: client,
	}
}

func (s *ImageService) Execute(ctx context.Context, request business.Request) (*business.Result, error) {
	prompt := request.Prompt
	if prompt == "" {
		return nil, fmt.Errorf("prompt cannot be empty")
	}
	if !request.PaymentVerified {
		requirements := s.ServiceRequirements(prompt)
		return nil, business.NewPaymentRequiredError(requirements.Description, requirements)
	}

	if s.client == nil {
		return nil, fmt.Errorf("genai client is not initialized. Please set GEMINI_API_KEY environment variable")
	}

	result, err := s.client.Models.GenerateContent(
		ctx,
		"gemini-2.5-flash-image",
		genai.Text(prompt),
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to generate image: %w", err)
	}

	if len(result.Candidates) == 0 {
		return nil, fmt.Errorf("no candidates in result")
	}

	artifactParts := make([]a2a.Part, 0)

	for _, part := range result.Candidates[0].Content.Parts {
		if part.Text != "" {
			artifactParts = append(artifactParts, a2a.TextPart{Text: part.Text})
		} else if part.InlineData != nil {
			imageBytes := part.InlineData.Data
			outputFilename := "./gemini_generated_image.png"
			if err := os.WriteFile(outputFilename, imageBytes, 0644); err != nil {
				log.Printf("failed to write image to file: %v", err)
			}

			mimeType := part.InlineData.MIMEType
			if mimeType == "" {
				mimeType = "image/png"
			}
			artifactParts = append(artifactParts, a2a.FilePart{
				File: a2a.FileBytes{
					FileMeta: a2a.FileMeta{
						Name:     "gemini_generated_image.png",
						MimeType: mimeType,
					},
					Bytes: base64.StdEncoding.EncodeToString(imageBytes),
				},
			})
		}
	}

	if len(artifactParts) == 0 {
		return nil, fmt.Errorf("no image or text data found in result")
	}

	return &business.Result{
		Message: "Image generated successfully",
		Artifacts: []*a2a.Artifact{
			{
				Name:        "generated-image",
				Description: fmt.Sprintf("Generated image for prompt: %s", prompt),
				Parts:       artifactParts,
			},
		},
	}, nil
}

func (s *ImageService) ServiceRequirements(prompt string) business.ServiceRequirements {
	basePrice := 1.0
	if len(prompt) > 100 {
		basePrice = 1.5
	}
	if len(prompt) > 500 {
		basePrice = 2.0
	}

	priceStr := fmt.Sprintf("%.1f", basePrice)

	description := "Generate an AI image"
	if len(prompt) > 50 {
		description = fmt.Sprintf("Generate an AI image: %s...", prompt[:50])
	}

	return business.ServiceRequirements{
		Price:             priceStr,
		Resource:          "/generate-image",
		Description:       description,
		MimeType:          "image/png",
		Scheme:            "exact",
		MaxTimeoutSeconds: 600,
	}
}
