# Payment Setup Guide

## How the Payment System Works

This demo uses the **ERC20 transferFrom pattern** with **automatic approval handling**:

1. **Automatic Approval**: When you make a purchase, the wallet automatically checks and handles USDC approval
2. **Payment Execution**: The merchant pulls the approved funds to complete the purchase

The approval step is now integrated into the payment flow - no manual setup required!

## Prerequisites

Before making purchases, you need:

1. **USDC tokens** on Base Sepolia testnet
   - Token address: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
   - Get test USDC from a faucet or bridge

2. **ETH for gas** on Base Sepolia
   - Both buyer and merchant need ETH
   - Get test ETH from: https://www.alchemy.com/faucets/base-sepolia

## Step 1: Check Your Balance (Optional)

Check if you have USDC and ETH:

```bash
cd examples/python/adk-demo
uv run python client_agent/approve_helper.py --check
```

## Step 2: Make Purchases

Simply start making purchases! The wallet will:
1. **Check if approval is needed** for the purchase amount
2. **Automatically approve** the merchant if needed (you'll see a log message)
3. **Complete the payment** once approval is confirmed

The first purchase may take slightly longer as it handles the approval transaction.

## How It Works

### Automatic Approval Flow

When you make a purchase:
1. **Wallet checks** current approval for the merchant
2. **If insufficient**: Automatically sends an approval transaction (with 10% buffer)
3. **Waits for confirmation**: Ensures approval is on-chain
4. **Signs payment**: Creates the payment authorization
5. **Merchant executes**: Pulls the approved funds

The `transferFrom` pattern provides:
- **Security**: You control exactly how much the merchant can spend
- **Proof**: Each payment is cryptographically linked to a specific purchase
- **Automation**: No manual transfers needed for each purchase
- **Seamless UX**: Approval is handled automatically in the payment flow

### Alternative Approaches

In production, you might use:
- **Meta-transactions**: Someone else pays the gas
- **Account Abstraction**: Smart contract wallets with better UX
- **Payment Channels**: Off-chain payments with periodic settlement

## Troubleshooting

### "Insufficient token approval" Error
- Run the approval script above
- Make sure you have enough USDC

### "Insufficient balance" Error  
- You need more USDC tokens
- Check your balance with `--check` flag

### Transaction Fails
- Make sure the merchant has ETH for gas
- Check that you approved enough USDC
- Verify the merchant address matches in both scripts

## Security Notes

- **Never share your private keys**
- **Only approve what you're willing to spend**
- **This is for testing only** - production systems should use secure key management