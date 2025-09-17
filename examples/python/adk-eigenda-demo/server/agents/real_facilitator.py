import logging
import os
from typing import override
from web3 import Web3
from web3.providers import HTTPProvider
from eth_account import Account
from eth_account.messages import encode_defunct
import json
import time
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import requests

from x402.types import (
    ExactPaymentPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from x402_a2a import FacilitatorClient


# Standard ERC20 ABI for transfer and balanceOf functions
ERC20_ABI = json.loads('''[
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "sender", "type": "address"},
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
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


class RealFacilitator(FacilitatorClient):
    """
    A real facilitator that interacts with Base Sepolia blockchain.
    This implementation verifies signatures and executes actual token transfers.
    """

    def __init__(self):
        """Initialize Web3 connection and load configuration from environment."""
        # Get RPC URL from environment or use default Base Sepolia RPC
        rpc_url = os.getenv("BASE_SEPOLIA_RPC_URL", "https://base-sepolia.g.alchemy.com/v2/_sTLFEOJwL7dFs2bLmqUo")
        
        # Create a session with retry logic for better reliability
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Initialize Web3 connection with custom session
        provider = HTTPProvider(rpc_url, request_kwargs={'timeout': 30}, session=session)
        self.w3 = Web3(provider)
        
        # Try to connect with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if self.w3.is_connected():
                    chain_id = self.w3.eth.chain_id
                    logging.info(f"Connected to Base Sepolia. Chain ID: {chain_id}")
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ConnectionError(f"Failed to connect to Base Sepolia at {rpc_url} after {max_retries} attempts: {str(e)}")
                logging.warning(f"Connection attempt {attempt + 1} failed, retrying...")
                time.sleep(1)
        
        # Get merchant private key from environment (for executing transfers)
        # In production, this would be managed securely
        merchant_private_key = os.getenv("MERCHANT_PRIVATE_KEY")
        if merchant_private_key:
            self.merchant_account = Account.from_key(merchant_private_key)
            logging.info(f"Merchant account loaded: {self.merchant_account.address}")
        else:
            self.merchant_account = None
            logging.warning("No MERCHANT_PRIVATE_KEY set - settlement will fail")

    @override
    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """Verify the payment signature and check balances on-chain."""
        logging.info("--- REAL FACILITATOR: VERIFY ---")
        logging.info(f"Received payload:\n{payload.model_dump_json(indent=2)}")
        
        try:
            payer = None
            authorization = None
            signature = None
            
            # Extract payer address and signature from payload
            if isinstance(payload.payload, ExactPaymentPayload):
                payer = payload.payload.authorization.from_
                authorization = payload.payload.authorization
                signature = payload.payload.signature
                # For Pydantic objects, access attributes directly
                extra_data = authorization.extra if hasattr(authorization, 'extra') else {}
                message_to_verify = extra_data.get("message", "") if isinstance(extra_data, dict) else ""
            elif isinstance(payload.payload, dict):
                # Handle dict payload format
                payer = payload.payload.get("authorization", {}).get("from")
                authorization = payload.payload.get("authorization", {})
                signature = payload.payload.get("signature")
                message_to_verify = authorization.get("extra", {}).get("message", "")
            else:
                return VerifyResponse(
                    is_valid=False, 
                    invalid_reason=f"Unsupported payload type: {type(payload.payload)}",
                    payer=None  # Include payer field even on error
                )
            
            if not payer or not signature:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason="Missing payer address or signature",
                    payer=payer if payer else None
                )
            if not message_to_verify:
                # Reconstruct message if not provided
                message_to_verify = f"""Chain ID: {payload.network}
Contract: {requirements.asset}
User: {payer}
Receiver: {requirements.pay_to}
Amount: {requirements.max_amount_required}
"""
            
            # Recover address from signature
            message = encode_defunct(text=message_to_verify)
            recovered_address = Account.recover_message(message, signature=signature)
            
            if recovered_address.lower() != payer.lower():
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason=f"Signature verification failed. Expected {payer}, got {recovered_address}",
                    payer=payer
                )
            
            # Check token balance on-chain
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(requirements.asset),
                abi=ERC20_ABI
            )
            
            balance = token_contract.functions.balanceOf(
                Web3.to_checksum_address(payer)
            ).call()
            
            required_amount = int(requirements.max_amount_required)
            
            if balance < required_amount:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason=f"Insufficient balance. Has {balance}, needs {required_amount}",
                    payer=payer
                )
            
            # Note: Approval check removed from here because the client handles approval
            # automatically during the payment signing process. The approval will be
            # checked during the actual settlement phase when transferFrom is called.
            
            logging.info(f"Payment verified successfully. Payer: {payer}, Balance: {balance}")
            return VerifyResponse(is_valid=True, payer=payer)
            
        except Exception as e:
            logging.error(f"Verification error: {str(e)}")
            # Try to include payer if we have it
            return VerifyResponse(
                is_valid=False, 
                invalid_reason=str(e),
                payer=payer if 'payer' in locals() and payer else None
            )

    @override
    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """Execute the actual token transfer on Base Sepolia."""
        logging.info("--- REAL FACILITATOR: SETTLE ---")
        
        if not self.merchant_account:
            return SettleResponse(
                success=False,
                error_reason="Merchant account not configured"
            )
        
        try:
            # Extract payer information
            if isinstance(payload.payload, ExactPaymentPayload):
                payer = payload.payload.authorization.from_
            elif isinstance(payload.payload, dict):
                payer = payload.payload.get("authorization", {}).get("from")
            else:
                return SettleResponse(
                    success=False,
                    error_reason=f"Unsupported payload type: {type(payload.payload)}"
                )
            
            # Setup token contract
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(requirements.asset),
                abi=ERC20_ABI
            )
            
            amount = int(requirements.max_amount_required)
            
            # Build the transferFrom transaction
            # Note: This assumes the payer has approved the merchant to spend tokens
            # In a real implementation, you might use different patterns like:
            # - Meta-transactions
            # - Account abstraction
            # - Payment channels
            transaction = token_contract.functions.transferFrom(
                Web3.to_checksum_address(payer),
                Web3.to_checksum_address(requirements.pay_to),
                amount
            ).build_transaction({
                'from': self.merchant_account.address,
                'nonce': self.w3.eth.get_transaction_count(self.merchant_account.address),
                'gas': 200000,  # Estimate or set appropriate gas limit
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            # Sign and send transaction
            signed_txn = self.merchant_account.sign_transaction(transaction)
            # Handle both old and new web3.py API
            raw_tx = signed_txn.raw_transaction if hasattr(signed_txn, 'raw_transaction') else signed_txn.rawTransaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            # Wait for transaction receipt
            logging.info(f"Transaction sent: {tx_hash.hex()}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                logging.info(f"Settlement successful. TX: {tx_hash.hex()}")
                return SettleResponse(
                    success=True,
                    network="base-sepolia",
                    transaction_hash=tx_hash.hex()
                )
            else:
                # Try to get the revert reason
                try:
                    # Replay the transaction to get the revert reason
                    self.w3.eth.call(transaction, block_identifier=receipt.blockNumber)
                    error_msg = f"Transaction failed without revert message. TX: {tx_hash.hex()}"
                except Exception as replay_error:
                    error_str = str(replay_error)
                    # Check for common ERC20 errors
                    if "insufficient allowance" in error_str.lower() or "erc20: transfer amount exceeds allowance" in error_str.lower():
                        # Check current allowance for better error message
                        allowance = token_contract.functions.allowance(
                            Web3.to_checksum_address(payer),
                            Web3.to_checksum_address(self.merchant_account.address)
                        ).call()
                        error_msg = (f"Insufficient token approval. Current allowance: {allowance}, "
                                   f"needed: {amount}. The client should have auto-approved but it may have failed. "
                                   f"TX: {tx_hash.hex()}")
                    else:
                        error_msg = f"Transaction failed: {error_str}. TX: {tx_hash.hex()}"
                
                logging.error(f"Settlement failed: {error_msg}")
                logging.error(f"Transaction receipt: {receipt}")
                
                return SettleResponse(
                    success=False,
                    error_reason=error_msg
                )
                
        except Exception as e:
            logging.error(f"Settlement error: {str(e)}")
            return SettleResponse(
                success=False,
                error_reason=str(e)
            )

