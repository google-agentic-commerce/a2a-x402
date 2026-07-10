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

package main

import (
	"context"
	"flag"
	"log"
)

func init() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)
}

func main() {
	port := flag.String("port", ":8080", "Server port (e.g., :8080)")
	facilitatorURL := flag.String("facilitator", "https://www.x402.org/facilitator", "Facilitator URL for payment verification (testnet: https://www.x402.org/facilitator, mainnet: https://api.cdp.coinbase.com/platform/v2/x402)")
	configPath := flag.String("config", "server_config.json", "Path to server config file")
	flag.Parse()

	serverConfig, err := LoadServerConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load server config: %v", err)
	}

	imageService := NewImageService()

	serverHandler, err := NewServerHandler(context.Background(), *facilitatorURL, serverConfig.NetworkConfigs, imageService)
	if err != nil {
		log.Fatalf("Failed to create server handler: %v", err)
	}

	if err := serverHandler.StartServer(*port); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}
