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

package merchant

import (
	"context"
	"fmt"

	"github.com/a2aproject/a2a-go/a2asrv"
	"github.com/google-agentic-commerce/a2a-x402/core/business"
	"github.com/google-agentic-commerce/a2a-x402/core/types"
)

type Merchant struct {
	orchestrator *BusinessOrchestrator
}

func NewMerchant(
	ctx context.Context,
	facilitatorURL string,
	businessService business.BusinessService,
	networkConfigs []types.NetworkConfig,
) (*Merchant, error) {
	if len(networkConfigs) == 0 {
		return nil, fmt.Errorf("no network configurations provided")
	}

	orchestrator, err := NewBusinessOrchestrator(ctx, facilitatorURL, businessService, networkConfigs)
	if err != nil {
		return nil, fmt.Errorf("failed to create business orchestrator: %w", err)
	}

	return &Merchant{
		orchestrator: orchestrator,
	}, nil
}

func (m *Merchant) Orchestrator() a2asrv.AgentExecutor {
	return m.orchestrator
}
