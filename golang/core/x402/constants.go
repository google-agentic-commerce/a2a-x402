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

import (
	svm "github.com/x402-foundation/x402/go/mechanisms/svm"
)

const (
	X402ExtensionURI = "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2"
	X402Version      = 2
)

const (
	NetworkBase          = "eip155:8453"
	NetworkBaseSepolia   = "eip155:84532"
	NetworkSolanaMainnet = svm.SolanaMainnetCAIP2
	NetworkSolanaDevnet  = svm.SolanaDevnetCAIP2
	NetworkSolanaTestnet = svm.SolanaTestnetCAIP2
)

const (
	MetadataKeyStatus         = "x402.payment.status"
	MetadataKeyRequired       = "x402.payment.required"
	MetadataKeyPayload        = "x402.payment.payload"
	MetadataKeyReceipts       = "x402.payment.receipts"
	MetadataKeyError          = "x402.payment.error"
	MetadataKeyOriginalPrompt = "x402.payment.original_prompt"
)

const (
	ErrorCodeInsufficientFunds = "INSUFFICIENT_FUNDS"
	ErrorCodeInvalidSignature  = "INVALID_SIGNATURE"
	ErrorCodeExpiredPayment    = "EXPIRED_PAYMENT"
	ErrorCodeDuplicateNonce    = "DUPLICATE_NONCE"
	ErrorCodeNetworkMismatch   = "NETWORK_MISMATCH"
	ErrorCodeInvalidAmount     = "INVALID_AMOUNT"
	ErrorCodeSettlementFailed  = "SETTLEMENT_FAILED"
)
