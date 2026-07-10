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

package main

import (
	"context"
	"fmt"
	"net/http"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/a2aproject/a2a-go/a2asrv"
	"github.com/gin-gonic/gin"
	"github.com/google-agentic-commerce/a2a-x402/core/business"
	"github.com/google-agentic-commerce/a2a-x402/core/merchant"
	"github.com/google-agentic-commerce/a2a-x402/core/types"
	"github.com/google-agentic-commerce/a2a-x402/core/x402"
)

type ServerHandler struct {
	agentCard *a2a.AgentCard
	handler   a2asrv.RequestHandler
}

func NewServerHandler(ctx context.Context, facilitatorURL string, networkConfigs []types.NetworkConfig, businessService business.BusinessService) (*ServerHandler, error) {

	merchantInstance, err := merchant.NewMerchant(ctx, facilitatorURL, businessService, networkConfigs)
	if err != nil {
		return nil, fmt.Errorf("failed to create merchant: %w", err)
	}

	agentCard := &a2a.AgentCard{
		Name:               "AI Image Generator",
		Description:        "An AI agent that generates images with payment support",
		URL:                "http://localhost:8080/rpc",
		PreferredTransport: a2a.TransportProtocolJSONRPC,
		DefaultInputModes:  []string{"text"},
		DefaultOutputModes: []string{"text", "image/png"},
		Capabilities: a2a.AgentCapabilities{
			Extensions: []a2a.AgentExtension{
				{
					URI:      x402.X402ExtensionURI,
					Required: true,
				},
			},
		},
		ProtocolVersion: "0.2",
		Version:         "1.0.0",
		Skills: []a2a.AgentSkill{
			{
				Name:        "generate-image",
				Description: "Generate an AI image based on a text prompt",
			},
		},
	}

	return &ServerHandler{
		agentCard: agentCard,
		handler:   a2asrv.NewHandler(merchantInstance.Orchestrator()),
	}, nil
}

func (sh *ServerHandler) StartServer(port string) error {
	gin.SetMode(gin.ReleaseMode)

	router := gin.Default()

	agentCardHandler := a2asrv.NewStaticAgentCardHandler(sh.agentCard)
	router.GET(a2asrv.WellKnownAgentCardPath, gin.WrapH(agentCardHandler))

	rpcHandler := a2asrv.NewJSONRPCHandler(sh.handler)
	wrappedHandler := extractHeadersMiddleware(rpcHandler)
	router.POST("/rpc", gin.WrapH(wrappedHandler))
	router.GET("/rpc", gin.WrapH(wrappedHandler))

	return router.Run(port)
}

func extractHeadersMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		headers := make(map[string][]string)
		for k, v := range r.Header {
			headers[k] = v
		}

		requestMeta := a2asrv.NewRequestMeta(headers)
		ctx, _ := a2asrv.WithCallContext(r.Context(), requestMeta)
		r = r.WithContext(ctx)

		next.ServeHTTP(w, r)
	})
}
