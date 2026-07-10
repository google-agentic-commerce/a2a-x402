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
	"time"

	"github.com/google-agentic-commerce/a2a-x402/core/client"
)

func init() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)
}

func main() {
	merchantURL := flag.String("merchant", "http://localhost:8080", "Merchant server URL")
	messageText := flag.String("message", "Generate an image of a sunset", "Message to send to the merchant")
	configPath := flag.String("config", "client_config.json", "Path to client config file")
	flag.Parse()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	clientConfig, err := LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("Failed to load client config: %v", err)
	}

	c, err := client.NewClient(*merchantURL, clientConfig.NetworkKeyPairs)
	if err != nil {
		log.Fatalf("Failed to create client: %v", err)
	}

	finalTask, err := c.WaitForCompletion(ctx, *messageText)
	if err != nil {
		log.Fatalf("Failed to wait for completion: %v", err)
	}
	_ = finalTask
}
