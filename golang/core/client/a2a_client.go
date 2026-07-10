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
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/a2aproject/a2a-go/a2aclient"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
)

func NewA2AClient(ctx context.Context, merchantURL string) (*a2aclient.Client, error) {
	agentCardURL := merchantURL + "/.well-known/agent-card.json"
	agentCard, err := fetchAgentCard(ctx, agentCardURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch AgentCard: %w", err)
	}

	extensionURIs := extractExtensionURIs(agentCard)
	if !containsExtensionURI(extensionURIs, x402pkg.X402ExtensionURI) {
		return nil, fmt.Errorf("merchant does not advertise the required x402 extension: %s", x402pkg.X402ExtensionURI)
	}

	factory := a2aclient.NewFactory(
		a2aclient.WithInterceptors(newExtensionHeaderInterceptor(extensionURIs)),
	)

	rpcEndpoint := determineRPCEndpoint(merchantURL, agentCard)
	client, err := factory.CreateFromEndpoints(ctx, []a2a.AgentInterface{
		{
			URL:       rpcEndpoint,
			Transport: a2a.TransportProtocolJSONRPC,
		},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create A2A client from endpoints: %w. Ensure the server is running at %s", err, merchantURL)
	}

	return client, nil
}

func fetchAgentCard(ctx context.Context, url string) (*a2a.AgentCard, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpClient := &http.Client{Timeout: 10 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch agent card: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var card a2a.AgentCard
	if err := json.NewDecoder(resp.Body).Decode(&card); err != nil {
		return nil, fmt.Errorf("failed to decode agent card: %w", err)
	}

	return &card, nil
}

func extractExtensionURIs(agentCard *a2a.AgentCard) []string {
	if agentCard == nil {
		return nil
	}
	extensions := agentCard.Capabilities.Extensions
	uris := make([]string, 0, len(extensions))
	for _, ext := range extensions {
		if ext.URI != "" {
			uris = append(uris, ext.URI)
		}
	}
	return uris
}

func containsExtensionURI(extensionURIs []string, target string) bool {
	for _, uri := range extensionURIs {
		if uri == target {
			return true
		}
	}
	return false
}

func determineRPCEndpoint(merchantURL string, agentCard *a2a.AgentCard) string {
	if agentCard.URL != "" && agentCard.PreferredTransport == a2a.TransportProtocolJSONRPC {
		return agentCard.URL
	}
	return merchantURL + "/rpc"
}

func SendMessage(ctx context.Context, client messageClient, message *a2a.Message) (*a2a.Task, *a2a.Message, error) {
	if client == nil {
		return nil, nil, fmt.Errorf("a2a client is required")
	}
	if message == nil {
		return nil, nil, fmt.Errorf("message is required")
	}
	messageParams := &a2a.MessageSendParams{
		Message: message,
	}
	result, err := client.SendMessage(ctx, messageParams)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to send message: %w", err)
	}

	switch v := result.(type) {
	case *a2a.Task:
		return v, nil, nil
	case *a2a.Message:
		return nil, v, nil
	default:
		return nil, nil, fmt.Errorf("received unexpected response type: %T", result)
	}
}
