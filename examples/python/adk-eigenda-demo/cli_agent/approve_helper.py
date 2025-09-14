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

"""
Helper script to approve the merchant to spend USDC tokens.
This needs to be run once before making purchases.
"""

import os
import sys
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# ERC20 ABI for approve function
ERC20_ABI = json.loads('''[
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


def approve_merchant(amount_usdc: float = 100.0):
    """
    Approve the merchant to spend USDC tokens.
    
    Args:
        amount_usdc: Amount of USDC to approve (default 100 USDC)
    """
    # Configuration
    rpc_url = os.getenv("BASE_SEPOLIA_RPC_URL", "https://base-sepolia.g.alchemy.com/v2/_sTLFEOJwL7dFs2bLmqUo")
    buyer_private_key = os.getenv("WALLET_PRIVATE_KEY")
    merchant_address = "0x3B9b10B8a63B93Ae8F447A907FD1EF067153c4e5"  # From adk_merchant_agent.py
    usdc_address = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # Base Sepolia USDC
    
    if not buyer_private_key:
        print("❌ Error: WALLET_PRIVATE_KEY not found in .env")
        return False
    
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"❌ Error: Could not connect to {rpc_url}")
        return False
    
    # Set up account
    account = Account.from_key(buyer_private_key)
    print(f"👤 Buyer address: {account.address}")
    print(f"🏪 Merchant address: {merchant_address}")
    
    # Set up USDC contract
    usdc_contract = w3.eth.contract(
        address=Web3.to_checksum_address(usdc_address),
        abi=ERC20_ABI
    )
    
    # Check current allowance
    current_allowance = usdc_contract.functions.allowance(
        account.address,
        merchant_address
    ).call()
    
    current_allowance_usdc = current_allowance / 1_000_000  # Convert to USDC
    print(f"📊 Current allowance: {current_allowance_usdc} USDC")
    
    # Convert USDC amount to token units (6 decimals)
    amount_units = int(amount_usdc * 1_000_000)
    
    if current_allowance >= amount_units:
        print(f"✅ Already approved for {amount_usdc} USDC or more")
        return True
    
    print(f"🔄 Approving {amount_usdc} USDC...")
    
    try:
        # Build approval transaction
        transaction = usdc_contract.functions.approve(
            Web3.to_checksum_address(merchant_address),
            amount_units
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
            'chainId': w3.eth.chain_id
        })
        
        # Sign and send transaction
        signed_txn = account.sign_transaction(transaction)
        raw_tx = signed_txn.raw_transaction if hasattr(signed_txn, 'raw_transaction') else signed_txn.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        
        print(f"📤 Transaction sent: {tx_hash.hex()}")
        print("⏳ Waiting for confirmation...")
        
        # Wait for receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt.status == 1:
            print(f"✅ Approval successful! TX: {tx_hash.hex()}")
            print(f"🎉 Merchant can now spend up to {amount_usdc} USDC from your account")
            
            # Verify new allowance
            new_allowance = usdc_contract.functions.allowance(
                account.address,
                merchant_address
            ).call()
            new_allowance_usdc = new_allowance / 1_000_000
            print(f"📊 New allowance: {new_allowance_usdc} USDC")
            return True
        else:
            print(f"❌ Approval transaction failed. TX: {tx_hash.hex()}")
            return False
            
    except Exception as e:
        print(f"❌ Error during approval: {str(e)}")
        return False


def check_balance():
    """Check the buyer's USDC balance."""
    rpc_url = os.getenv("BASE_SEPOLIA_RPC_URL", "https://base-sepolia.g.alchemy.com/v2/_sTLFEOJwL7dFs2bLmqUo")
    buyer_private_key = os.getenv("WALLET_PRIVATE_KEY")
    usdc_address = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    
    if not buyer_private_key:
        print("❌ Error: WALLET_PRIVATE_KEY not found in .env")
        return
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = Account.from_key(buyer_private_key)
    
    # Simple balance check using eth_call
    # Function selector for balanceOf(address)
    function_selector = w3.keccak(text="balanceOf(address)")[:4].hex()
    # Pad address to 32 bytes
    padded_address = "0x" + account.address[2:].zfill(64)
    data = function_selector + padded_address[2:]
    
    result = w3.eth.call({
        'to': Web3.to_checksum_address(usdc_address),
        'data': data
    })
    
    balance = int(result.hex(), 16)
    balance_usdc = balance / 1_000_000
    
    print(f"💰 USDC Balance: {balance_usdc} USDC")
    print(f"👤 Address: {account.address}")
    
    # Check ETH balance for gas
    eth_balance = w3.eth.get_balance(account.address)
    eth_balance_ether = w3.from_wei(eth_balance, 'ether')
    print(f"⛽ ETH Balance: {eth_balance_ether} ETH (for gas)")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Approve merchant to spend USDC")
    parser.add_argument("--amount", type=float, default=100.0, help="Amount of USDC to approve (default: 100)")
    parser.add_argument("--check", action="store_true", help="Just check balance, don't approve")
    
    args = parser.parse_args()
    
    if args.check:
        check_balance()
    else:
        print(f"🚀 Approving merchant for {args.amount} USDC on Base Sepolia...")
        approve_merchant(args.amount)