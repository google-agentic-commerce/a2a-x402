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
import json
import logging
import os
from typing import override

from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from x402_a2a import FacilitatorClient
from x402_a2a.types import (
    ExactPaymentPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)

# Base Sepolia USDC contract details for EIP-3009 transferWithAuthorization
USDC_BASE_SEPOLIA_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
USDC_ABI = json.loads(
    """
[
    {
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
            {"name": "signature", "type": "bytes"}
        ],
        "name": "transferWithAuthorization",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
"""
)


class LocalFacilitator(FacilitatorClient):
    """
    A local facilitator that can be swapped in for testing.
    It makes calls to default base sepolia network endpoints.
    """

    def __init__(self, is_valid: bool = True, is_settled: bool = True):
        self._is_valid = is_valid
        self._is_settled = is_settled
        load_dotenv()
        base_sepolia_rpc_url = os.getenv(
            "RPC_URL",
            "https://sepolia.base.org",
        )
        self.w3 = Web3(
            Web3.HTTPProvider(base_sepolia_rpc_url, request_kwargs={"timeout": 120})
        )
        # TODO: Replace with your facilitator's private key
        self.facilitator_private_key = os.getenv(
            "FACILITATOR_PRIVATE_KEY", "0000000000000000000000000000000000000001"
        )

    @override
    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """Mocks the verification step."""
        logging.info("--- MOCK FACILITATOR: VERIFY ---")
        logging.info(f"Received payload:\n{payload.model_dump_json(indent=2)}")

        payer = None
        if isinstance(payload.payload, ExactPaymentPayload):
            payer = payload.payload.authorization.from_
        else:
            raise TypeError(f"Unsupported payload type: {type(payload.payload)}")

        if self._is_valid:
            return VerifyResponse(is_valid=True, payer=payer)
        return VerifyResponse(is_valid=False, invalid_reason="mock_invalid_payload")

    @override
    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """Settles a USDC transaction on Base Sepolia using EIP-3009."""
        logging.info("--- REAL FACILITATOR: SETTLE (USDC with EIP-3009) ---")
        try:
            if not isinstance(payload.payload, ExactPaymentPayload):
                raise TypeError(f"Unsupported payload type: {type(payload.payload)}")

            auth = payload.payload.authorization
            facilitator_account = self.w3.eth.account.from_key(
                self.facilitator_private_key
            )
            facilitator_address = facilitator_account.address

            usdc_contract = self.w3.eth.contract(
                address=USDC_BASE_SEPOLIA_ADDRESS, abi=USDC_ABI
            )

            # --- Get all parameters from the payload ---
            from_ = self.w3.to_checksum_address(auth.from_)
            to = self.w3.to_checksum_address(auth.to)
            value = int(auth.value)
            valid_after = int(auth.valid_after)
            valid_before = int(auth.valid_before)
            nonce = bytes.fromhex(auth.nonce.removeprefix("0x"))
            signature = bytes.fromhex(payload.payload.signature.removeprefix("0x"))

            # --- Off-chain signature verification (for detailed debugging) ---
            try:
                chain_id = self.w3.eth.chain_id
                domain_data = {
                    "name": "USD Coin",
                    "version": "2",
                    "chainId": chain_id,
                    "verifyingContract": USDC_BASE_SEPOLIA_ADDRESS,
                }
                # IMPORTANT: Use the values from the payload for verification
                message_data = {
                    "from": from_,
                    "to": to,
                    "value": value,
                    "validAfter": valid_after,
                    "validBefore": valid_before,
                    "nonce": nonce,
                }

                full_message = {
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
                    "domain": domain_data,
                    "message": message_data,
                }

                signable_message = encode_typed_data(full_message=full_message)

                # We need v, r, s for the recovery check, even if the contract doesn't
                sig_hex = payload.payload.signature.removeprefix("0x")
                r = bytes.fromhex(sig_hex[0:64])
                s = bytes.fromhex(sig_hex[64:128])
                v = int(sig_hex[128:130], 16)
                recovered_address = Account.recover_message(
                    signable_message, vrs=(v, r, s)
                )

                logging.info(
                    f"Off-chain verification successful. Recovered address: {recovered_address}"
                )

            except Exception as e:
                logging.error(f"CRITICAL: Off-chain signature verification failed: {e}")
                logging.error(
                    f"VERIFICATION DATA DUMP: {json.dumps(full_message, indent=2)}"
                )
                return SettleResponse(
                    success=False,
                    error_reason=f"off-chain_verification_failed: {e}",
                )

            # --- Transaction: transferWithAuthorization ---
            logging.info("Submitting transferWithAuthorization transaction...")
            logging.info("--- SETTLEMENT DEBUG DATA (Server) ---")
            logging.info(f"from: {from_}")
            logging.info(f"to: {to}")
            logging.info(f"value: {value}")
            logging.info(f"valid_after: {valid_after}")
            logging.info(f"valid_before: {valid_before}")
            logging.info(f"nonce: {nonce.hex()}")
            logging.info(f"signature: {signature.hex()}")
            logging.info("------------------------------------")

            tx_nonce = self.w3.eth.get_transaction_count(facilitator_address)
            latest_block = self.w3.eth.get_block("latest")
            max_priority_fee = self.w3.eth.max_priority_fee
            max_fee = max_priority_fee + 2 * latest_block["baseFeePerGas"]

            tx_unsigned = usdc_contract.functions.transferWithAuthorization(
                from_, to, value, valid_after, valid_before, nonce, signature
            ).build_transaction(
                {
                    "from": facilitator_address,
                    "nonce": tx_nonce,
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": max_priority_fee,
                    "gas": 200000,  # Hardcoded gas limit
                    "chainId": self.w3.eth.chain_id,
                }
            )

            signed_tx = self.w3.eth.account.sign_transaction(
                tx_unsigned, self.facilitator_private_key
            )
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt.status == 1:
                logging.info(
                    f"transferWithAuthorization transaction successful: {tx_hash.hex()}"
                )
                return SettleResponse(
                    success=True, network="base-sepolia", transaction=tx_hash.hex()
                )
            else:
                logging.error(
                    "transferWithAuthorization transaction failed. Receipt:"
                    f" {Web3.to_json(receipt)}"
                )
                return SettleResponse(success=False, error_reason="transaction_failed")

        except Exception as e:
            logging.error(f"Settlement failed: {e}")
            return SettleResponse(success=False, error_reason=str(e))
