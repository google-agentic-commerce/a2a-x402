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

package x402

import "testing"

func TestProtocolVersionDeclaration(t *testing.T) {
	if X402Version != 2 {
		t.Fatalf("X402Version = %d, want 2", X402Version)
	}
	const wantURI = "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2"
	if X402ExtensionURI != wantURI {
		t.Fatalf("X402ExtensionURI = %q, want %q", X402ExtensionURI, wantURI)
	}
}
