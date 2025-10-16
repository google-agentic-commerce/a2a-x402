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
"""Payment signing and processing functions."""

import datetime
import json
import logging
import os
from typing import Optional
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_account.messages import encode_typed_data
from web3 import Web3
from x402.clients.base import x402Client
from x402.common import x402_VERSION


from ..types import (
    PaymentRequirements,
    x402PaymentRequiredResponse,
    PaymentPayload,
    ExactPaymentPayload,
    EIP3009Authorization,
)

# Contract address for the asset being used. Can be overridden by an environment variable.
# Defaults to the Base Sepolia USDC Asset Contract
ASSET_CONTRACT_ADDRESS = os.getenv("ASSET_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")
ASSET_ABI = json.loads(
    """
[
    {
      "inputs": [],
      "name": "name",
      "outputs": [
        {
          "name": "",
          "type": "string"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "version",
      "outputs": [
        {
          "name": "",
          "type": "string"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "name": "owner",
          "type": "address"
        }
      ],
      "name": "nonces",
      "outputs": [
        {
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    }
]
"""
)

def process_payment_required(
    payment_required: x402PaymentRequiredResponse,
    account: Account,
    max_value: Optional[int] = None,
    valid_after: Optional[int] = None,
    valid_before: Optional[int] = None,
) -> PaymentPayload:
    """Process full payment required response using x402Client logic."""
    client = x402Client(account=account, max_value=max_value)
    selected_requirement = client.select_payment_requirements(payment_required.accepts)

    rpc_url = os.getenv(
        "RPC_URL", "https://base-mainnet.g.alchemy.com/v2/powzh9JFbTRlAV_cLhknU"
    )
    
    return process_payment(
        selected_requirement,
        account,
        rpc_url,
        ASSET_CONTRACT_ADDRESS,
        ASSET_ABI,
        max_value,
        valid_after,
        valid_before,
    )


def get_transfer_with_auth_typed_data(
    from_: str,
    to: str,
    value: int,
    valid_after: int,
    valid_before: int,
    nonce: bytes,
    chain_id: int,
    contract_address: str,
    token_name: str,
    token_version: str,
):
    """Creates the EIP-712 typed data for an EIP-3009 transferWithAuthorization signature."""
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": token_name,
            "version": token_version,
            "chainId": chain_id,
            "verifyingContract": contract_address,
        },
        "message": {
            "from": from_,
            "to": to,
            "value": value,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        },
    }


def process_payment(
    requirements: PaymentRequirements,
    account: LocalAccount,
    max_value: Optional[int] = None,
    valid_after: Optional[int] = None,
    valid_before: Optional[int] = None,
) -> PaymentPayload:
    """Creates a PaymentPayload containing a valid EIP-3009 signature."""

    rpc_url = os.getenv(
        "RPC_URL", "https://base-mainnet.g.alchemy.com/v2/powzh9JFbTRlAV_cLhknU"
    )
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    asset_contract = w3.eth.contract(address=ASSET_CONTRACT_ADDRESS, abi=ASSET_ABI)

    # --- 1. Get the current nonce from the contract ---
    nonce_uint = asset_contract.functions.nonces(account.address).call()
    nonce_bytes = nonce_uint.to_bytes(32, 'big')

    # --- 2. Generate the authorization data ONCE ---
    auth_data = {
        "from_": account.address,
        "to": requirements.to,
        "value": int(requirements.value),
        "valid_after": valid_after if valid_after is not None else 0,
        "valid_before": valid_before if valid_before is not None else int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).timestamp()),
        "nonce": nonce_bytes
    }

    # --- Get EIP-712 domain info from the contract ---
    chain_id = w3.eth.chain_id
    token_name = asset_contract.functions.name().call()
    token_version = asset_contract.functions.version().call()

    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # --- 2. Create the exact data structure for signing ---
    typed_data = get_transfer_with_auth_typed_data(
        from_=auth_data["from_"],
        to=auth_data["to"],
        value=auth_data["value"],
        valid_after=auth_data["valid_after"],
        valid_before=auth_data["valid_before"],
        nonce=auth_data["nonce"],
        chain_id=chain_id,
        contract_address=ASSET_CONTRACT_ADDRESS,
        token_name=token_name,
        token_version=token_version,
    )

    logging.info("--- SIGNING DEBUG DATA (Client) ---")
    logging.info(f"domain: {json.dumps(typed_data['domain'], indent=2)}")
    logging.info(f"message: {json.dumps({k: (f'0x{v.hex()}' if isinstance(v, bytes) else v) for k, v in typed_data['message'].items()}, indent=2)}")
    logging.info("-----------------------------------")

    # --- 3. Sign THIS EXACT DATA OBJECT ---
    signable_message = encode_typed_data(full_message=typed_data)
    signed_message = account.sign_message(signable_message)

    # --- 4. Construct the final payload using the SAME authorization data ---
    authorization = EIP3009Authorization(
        from_=auth_data["from_"],
        to=auth_data["to"],
        value=str(auth_data["value"]),
        valid_after=str(auth_data["valid_after"]),
        valid_before=str(auth_data["valid_before"]),
        nonce=f"0x{auth_data['nonce'].hex()}",
    )

    # The signature is a single bytes object, but some systems expect it as a hex string
    # with r, s, and v components concatenated.
    signature_hex = f"0x{signed_message.r.to_bytes(32, 'big').hex()}{signed_message.s.to_bytes(32, 'big').hex()}{signed_message.v:02x}"

    exact_payload = ExactPaymentPayload(
        signature=signature_hex, authorization=authorization
    )

    return PaymentPayload(
        x402_version=x402_VERSION,
        scheme="exact",
        network=requirements.network,
        payload=exact_payload,
    )