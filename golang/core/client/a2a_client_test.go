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
	"strings"
	"testing"

	"github.com/a2aproject/a2a-go/a2a"
	"github.com/a2aproject/a2a-go/a2aclient"
	x402pkg "github.com/google-agentic-commerce/a2a-x402/core/x402"
)

func TestExtractExtensionURIs(t *testing.T) {
	if got := extractExtensionURIs(nil); got != nil {
		t.Fatalf("extractExtensionURIs(nil) = %#v", got)
	}

	card := &a2a.AgentCard{Capabilities: a2a.AgentCapabilities{Extensions: []a2a.AgentExtension{
		{URI: ""},
		{URI: "https://example.com/other"},
		{URI: x402pkg.X402ExtensionURI},
	}}}
	got := extractExtensionURIs(card)
	if len(got) != 2 || !containsExtensionURI(got, x402pkg.X402ExtensionURI) {
		t.Fatalf("extension URIs = %#v", got)
	}
	if containsExtensionURI(got, "https://example.com/missing") {
		t.Fatal("unexpected extension match")
	}
}

func TestExtensionHeaderInterceptor(t *testing.T) {
	interceptor := newExtensionHeaderInterceptor([]string{x402pkg.X402ExtensionURI})
	request := &a2aclient.Request{}
	if _, err := interceptor.Before(context.Background(), request); err != nil {
		t.Fatalf("Before() error = %v", err)
	}
	values := request.Meta["X-A2A-Extensions"]
	if len(values) != 1 || values[0] != x402pkg.X402ExtensionURI {
		t.Fatalf("extension header = %#v", values)
	}
}

func TestSendMessage(t *testing.T) {
	message := a2a.NewMessage(a2a.MessageRoleUser, a2a.TextPart{Text: "hello"})
	task := newClientTestTask("task-send", a2a.TaskStateSubmitted, "")

	tests := []struct {
		name        string
		client      messageClient
		message     *a2a.Message
		result      a2a.SendMessageResult
		wantTask    bool
		wantMessage bool
		wantError   string
	}{
		{name: "missing client", message: message, wantError: "a2a client is required"},
		{name: "missing message", client: &mockTaskClient{}, wantError: "message is required"},
		{name: "task response", client: &mockTaskClient{}, message: message, result: task, wantTask: true},
		{name: "message response", client: &mockTaskClient{}, message: message, result: message, wantMessage: true},
		{name: "empty response", client: &mockTaskClient{}, message: message, wantError: "unexpected response type"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if mock, ok := tt.client.(*mockTaskClient); ok {
				mock.sendMessageFunc = func(context.Context, *a2a.MessageSendParams) (a2a.SendMessageResult, error) {
					return tt.result, nil
				}
			}
			gotTask, gotMessage, err := SendMessage(context.Background(), tt.client, tt.message)
			if tt.wantError != "" {
				if err == nil || !strings.Contains(err.Error(), tt.wantError) {
					t.Fatalf("error = %v, want substring %q", err, tt.wantError)
				}
				return
			}
			if err != nil {
				t.Fatalf("SendMessage() error = %v", err)
			}
			if (gotTask != nil) != tt.wantTask || (gotMessage != nil) != tt.wantMessage {
				t.Fatalf("task = %#v, message = %#v", gotTask, gotMessage)
			}
		})
	}
}
