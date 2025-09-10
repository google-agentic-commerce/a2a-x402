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
import time
import uuid
import eth_account
from eth_account.messages import encode_defunct

from a2a_x402.types import PaymentPayload, x402PaymentRequiredResponse


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
        Simulates a wallet signing a payment requirement.
        """
        private_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        account = eth_account.Account.from_key(private_key)
        
        payment_option = requirements.accepts[0]

        message_to_sign = f"""Chain ID: {payment_option.network}
Contract: {payment_option.asset}
User: {account.address}
Receiver: {payment_option.pay_to}
Amount: {payment_option.max_amount_required}
"""
        signature = account.sign_message(encode_defunct(text=message_to_sign))

        authorization_payload = {
            "from": account.address,
            "to": payment_option.pay_to,
            "value": payment_option.max_amount_required,
            "validAfter": str(int(time.time())),
            "validBefore": str(
                int(time.time()) + payment_option.max_timeout_seconds
            ),
            "nonce": f"0x{uuid.uuid4().hex}",
            "extra": {"message": message_to_sign},
        }

        final_payload = {
            "authorization": authorization_payload,
            "signature": signature.signature.hex(),
        }

        return PaymentPayload(
            x402Version=1,
            scheme=payment_option.scheme,
            network=payment_option.network,
            payload=final_payload,
        )