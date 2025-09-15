# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from abc import ABC, abstractmethod
import eth_account

from x402_a2a.types import PaymentPayload, x402PaymentRequiredResponse
from x402_a2a.core.wallet import process_payment_required

class Wallet(ABC):
    """
    An abstract base class for a wallet that can sign payment requirements.
    This interface allows for different wallet implementations (e.g., local, MCP, hardware)
    to be used interchangeably by the client agent.
    """

    @abstractmethod
    def sign_payment(self, requirements: x402PaymentRequiredResponse) -> PaymentPayload:
        """
        Signs a payment requirement and returns the signed payload.
        """
        raise NotImplementedError


class MockLocalWallet(Wallet):
    """
    A mock wallet implementation that uses a hardcoded local private key.
    FOR DEMONSTRATION PURPOSES ONLY. DO NOT USE IN PRODUCTION.
    """

    def sign_payment(self, requirements: x402PaymentRequiredResponse) -> PaymentPayload:
        """
        Signs a payment requirement using x402.exact EIP-3009 signing.
        """
        private_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        account = eth_account.Account.from_key(private_key)
        
        return process_payment_required(requirements, account)