#!/usr/bin/env python3
"""
Attach a plan to an existing agent.

This script associates a Nevermined payment plan with an existing agent,
allowing users subscribed to that plan to access the agent.

Usage:
    uv run attach-plan-to-agent --agent-id <agent_id> --plan-id <plan_id>
    # OR
    uv run python utils/attach_plan_to_agent.py --agent-id <agent_id> --plan-id <plan_id>

Environment Variables Required:
    NVM_API_KEY_SERVER: Nevermined API key for the agent (merchant)
    NVM_ENVIRONMENT: Nevermined environment (default: "sandbox")
"""

import argparse
import os
import sys
from dotenv import load_dotenv

from payments_py.payments import Payments
from payments_py.common.types import PaymentOptions

# Load environment variables from .env file
load_dotenv()


def main():
    """Attach a plan to an agent."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Attach a Nevermined payment plan to an existing agent"
    )
    parser.add_argument(
        "--agent-id",
        required=True,
        help="The unique identifier of the agent",
    )
    parser.add_argument(
        "--plan-id",
        required=True,
        help="The unique identifier of the plan",
    )
    args = parser.parse_args()

    # Get environment variables
    nvm_api_key = os.getenv("NVM_API_KEY_SERVER")
    if not nvm_api_key:
        print("❌ Error: NVM_API_KEY_SERVER environment variable is required")
        print("   This should be the agent's (merchant's) Nevermined API key")
        sys.exit(1)

    environment = os.getenv("NVM_ENVIRONMENT", "sandbox")

    print(f"\n🔗 Attaching Plan to Agent")
    print(f"   Environment: {environment}")
    print(f"   Agent ID: {args.agent_id}")
    print(f"   Plan ID: {args.plan_id}\n")

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

    # Attach plan to agent
    try:
        print(f"\n📝 Attaching plan to agent...")
        result = payments.agents.add_plan_to_agent(
            plan_id=args.plan_id,
            agent_id=args.agent_id,
        )

        print(f"\n✅ Plan attached to agent successfully!")
        print(f"\n📋 Result:")
        print(f"   Agent ID: {args.agent_id}")
        print(f"   Plan ID: {args.plan_id}")
        if result:
            print(f"   Response: {result}")
        print(f"\n💡 Users subscribed to this plan can now access the agent.\n")

    except Exception as e:
        print(f"❌ Error attaching plan to agent: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
