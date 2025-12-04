"""
Create a Pay-as-you-go plan for the Nevermined demo.

This script creates a pay-as-you-go plan that charges $0.01 USD per request.
It uses USDC (USD Coin) on Base Sepolia as the payment token.

Usage:
    uv run create-payasyougo-plan
    # OR
    uv run python utils/create_payasyougo_plan.py

Environment Variables Required:
    NVM_API_KEY_SERVER: Nevermined API key for the agent (merchant)
    NVM_ENVIRONMENT: Nevermined environment (default: "sandbox")
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

from payments_py.payments import Payments
from payments_py.common.types import PaymentOptions, PlanMetadata
from payments_py.plans import get_pay_as_you_go_credits_config

# Load environment variables from .env file
load_dotenv()

# USDC token address on Base Sepolia
# USDC has 6 decimals, so $0.01 = 0.01 * 10^6 = 10000 smallest units
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
PRICE_PER_REQUEST_USD = 0.01
PRICE_PER_REQUEST_SMALLEST_UNIT = int(
    PRICE_PER_REQUEST_USD * 1_000_000
)  # 10000 for $0.01


def main():
    """Create a pay-as-you-go plan."""
    # Get environment variables
    nvm_api_key = os.getenv("NVM_API_KEY_SERVER")
    if not nvm_api_key:
        print("❌ Error: NVM_API_KEY_SERVER environment variable is required")
        print("   This should be the agent's (merchant's) Nevermined API key")
        sys.exit(1)

    environment = os.getenv("NVM_ENVIRONMENT", "sandbox")

    print(f"\n🚀 Creating Pay-as-you-go Plan")
    print(f"   Environment: {environment}")
    print(f"   Price per request: ${PRICE_PER_REQUEST_USD} USD")
    print(f"   Payment token: USDC on Base Sepolia")
    print(f"   Token address: {USDC_BASE_SEPOLIA}\n")

    # Initialize Payments instance
    try:
        payments = Payments.get_instance(
            PaymentOptions(
                nvm_api_key=nvm_api_key,
                environment=environment,
            )
        )
        print("✅ Payments instance initialized")
    except Exception as e:
        print(f"❌ Error initializing Payments: {e}")
        sys.exit(1)

    # Get agent's address (receiver)
    try:
        agent_address = payments.get_account_address()
        if not agent_address:
            print("❌ Error: Could not get agent address from API key")
            sys.exit(1)
        print(f"✅ Agent address: {agent_address}")
    except Exception as e:
        print(f"❌ Error getting agent address: {e}")
        sys.exit(1)

    # Create plan metadata
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_metadata = PlanMetadata(
        name=f"Pay-as-you-go Plan - {timestamp}",
        description=f"Pay-as-you-go plan charging ${PRICE_PER_REQUEST_USD} USD per request using USDC",
    )

    # Create pay-as-you-go price config
    # This automatically fetches the PayAsYouGoTemplate contract address from the API
    try:
        price_config = payments.plans.get_pay_as_you_go_price_config(
            amount=PRICE_PER_REQUEST_SMALLEST_UNIT,  # 10000 = $0.01 USD (6 decimals)
            receiver=agent_address,
            token_address=USDC_BASE_SEPOLIA,
        )
        print(f"✅ Price config created")
        print(
            f"   Amount per request: {PRICE_PER_REQUEST_SMALLEST_UNIT} smallest units (${PRICE_PER_REQUEST_USD} USD)"
        )
        print(f"   Template address: {price_config.template_address}")
    except Exception as e:
        print(f"❌ Error creating price config: {e}")
        sys.exit(1)

    # Create pay-as-you-go credits config
    # Note: For pay-as-you-go, credits config values default to 1 and are not functionally used
    credits_config = get_pay_as_you_go_credits_config()
    print(f"✅ Credits config created (default values for pay-as-you-go)")

    # Register the plan
    try:
        print(f"\n📝 Registering plan...")
        response = payments.plans.register_credits_plan(
            plan_metadata=plan_metadata,
            price_config=price_config,
            credits_config=credits_config,
        )

        plan_id = response.get("planId")
        if not plan_id:
            print(f"❌ Error: No plan ID returned in response")
            print(f"   Response: {response}")
            sys.exit(1)

        print(f"\n✅ Pay-as-you-go plan created successfully!")
        print(f"\n📋 Plan Details:")
        print(f"   Plan ID: {plan_id}")
        print(f"   Name: {plan_metadata.name}")
        print(f"   Description: {plan_metadata.description}")
        print(f"   Price per request: ${PRICE_PER_REQUEST_USD} USD")
        print(f"   Payment token: USDC ({USDC_BASE_SEPOLIA})")
        print(f"   Receiver: {agent_address}")
        print(f"\n💡 Next Steps:")
        print(f"   1. Add this plan ID to your .env file:")
        print(f'      NVM_PAYASYOUGO_PLAN_ID="{plan_id}"')
        print(f"   2. Restart your merchant server")
        print(
            f"   3. The plan will appear as an option when users try to purchase items\n"
        )

    except Exception as e:
        print(f"❌ Error registering plan: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
