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
import os
import time
import uuid
import logging
import json
import eth_account
from eth_account.messages import encode_defunct
from web3 import Web3
from web3.providers import HTTPProvider

from x402_a2a.types import PaymentPayload, x402PaymentRequiredResponse


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
    A wallet implementation that uses a private key from environment variables
    and automatically handles USDC approvals when needed.
    FOR DEMONSTRATION PURPOSES ONLY. DO NOT USE IN PRODUCTION.
    """

    def __init__(self):
        """Initialize the wallet with private key and Web3 connection."""
        self.private_key = os.getenv(
            "WALLET_PRIVATE_KEY",
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        if not self.private_key:
            raise ValueError("WALLET_PRIVATE_KEY environment variable not set")
        
        # Initialize Web3 for approval transactions
        rpc_url = os.getenv("BASE_SEPOLIA_RPC_URL", "https://base-sepolia.g.alchemy.com/v2/_sTLFEOJwL7dFs2bLmqUo")
        self.w3 = Web3(HTTPProvider(rpc_url))
        self.account = eth_account.Account.from_key(self.private_key)
        
        # ERC20 ABI for approve and allowance functions
        self.erc20_abi = json.loads('''[
            {
                "inputs": [
                    {"name": "spender", "type": "address"},
                    {"name": "amount", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "owner", "type": "address"},
                    {"name": "spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]''')

    def ensure_approval(self, token_address: str, spender_address: str, amount: int) -> bool:
        """
        Ensure the spender has approval to spend at least the specified amount.
        Automatically approves if current allowance is insufficient.
        
        Returns:
            bool: True if approval is successful or already sufficient, False otherwise
        """
        try:
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.erc20_abi
            )
            
            # Check current allowance
            current_allowance = token_contract.functions.allowance(
                self.account.address,
                Web3.to_checksum_address(spender_address)
            ).call()
            
            logging.info(f"Current allowance: {current_allowance}, Required: {amount}")
            
            if current_allowance >= amount:
                logging.info("Sufficient allowance already exists")
                return True
            
            # Need to approve
            logging.info(f"Approving {spender_address} to spend {amount} tokens...")
            
            # Add 10% buffer to avoid multiple approvals for similar amounts
            approval_amount = int(amount * 1.1)
            
            # Build approval transaction
            transaction = token_contract.functions.approve(
                Web3.to_checksum_address(spender_address),
                approval_amount
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(transaction)
            raw_tx = signed_txn.raw_transaction if hasattr(signed_txn, 'raw_transaction') else signed_txn.rawTransaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            logging.info(f"Approval transaction sent: {tx_hash.hex()}")
            logging.info("Waiting for approval confirmation...")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            if receipt.status == 1:
                logging.info(f"Approval successful! TX: {tx_hash.hex()}")
                return True
            else:
                logging.error(f"Approval transaction failed. TX: {tx_hash.hex()}")
                return False
                
        except Exception as e:
            logging.error(f"Error during approval: {str(e)}")
            return False

    def sign_payment(self, requirements: x402PaymentRequiredResponse) -> PaymentPayload:
        """
        Signs a payment requirement, automatically handling approval if needed.
        """
        payment_option = requirements.accepts[0]
        
        # First, ensure approval for the merchant to spend the required amount
        # Extract token address and merchant address from requirements
        token_address = payment_option.asset
        merchant_address = payment_option.pay_to
        amount_required = int(payment_option.max_amount_required)
        
        logging.info(f"Payment requested: {amount_required} tokens to {merchant_address}")
        
        # Automatically handle approval
        if not self.ensure_approval(token_address, merchant_address, amount_required):
            raise Exception("Failed to approve token spending. Payment cannot proceed.")
        
        logging.info("Token approval confirmed, proceeding with payment signature...")
        
        # Now sign the payment authorization
        message_to_sign = f"""Chain ID: {payment_option.network}
Contract: {payment_option.asset}
User: {self.account.address}
Receiver: {payment_option.pay_to}
Amount: {payment_option.max_amount_required}
"""
        signature = self.account.sign_message(encode_defunct(text=message_to_sign))

        authorization_payload = {
            "from": self.account.address,
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
