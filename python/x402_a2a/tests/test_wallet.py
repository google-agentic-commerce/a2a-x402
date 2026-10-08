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
"""Unit tests for EIP-3009 payment signing."""

from unittest.mock import patch

import pytest
from eth_account import Account

from x402_a2a.core.wallet import process_payment
from x402_a2a.types import PaymentRequirements


@pytest.fixture
def account():
    return Account.create()


@pytest.fixture
def requirements():
    return PaymentRequirements(
        scheme="exact",
        network="base-sepolia",
        pay_to="0x000000000000000000000000000000000000dEaD",
        max_amount_required="100",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        description="Test Payment",
        resource="/test",
        mime_type="application/json",
        max_timeout_seconds=600,
    )


@pytest.fixture
def mock_web3():
    """Patches Web3 so no RPC is made. The token exposes name() and version()
    but no nonces(), like tokens that implement EIP-3009 without EIP-2612."""
    with patch("x402_a2a.core.wallet.Web3") as web3_cls:
        w3 = web3_cls.return_value
        w3.eth.chain_id = 84532
        functions = w3.eth.contract.return_value.functions
        functions.name.return_value.call.return_value = "USDC"
        functions.version.return_value.call.return_value = "2"
        functions.nonces.return_value.call.side_effect = Exception(
            "execution reverted: nonces() not implemented"
        )
        yield functions


def _nonce(payload) -> str:
    return payload.payload.authorization.nonce


def test_nonce_does_not_depend_on_token_nonces(account, requirements, mock_web3):
    """EIP-3009 nonces are caller-chosen; signing must not need nonces()."""
    process_payment(requirements, account)

    mock_web3.nonces.assert_not_called()


def test_nonce_is_32_random_bytes(account, requirements, mock_web3):
    nonce = _nonce(process_payment(requirements, account))

    assert nonce.startswith("0x")
    assert len(bytes.fromhex(nonce[2:])) == 32


def test_nonce_is_unique_per_payment(account, requirements, mock_web3):
    first = _nonce(process_payment(requirements, account))
    second = _nonce(process_payment(requirements, account))

    assert first != second
