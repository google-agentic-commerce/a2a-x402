#!/usr/bin/env python3
"""
Test the full agent flow - simulating what the ADK agent would do.
"""

import asyncio
from client.host import host_agent

async def test_agent_flow():
    """Test the agent flow as if a user asked to buy something."""
    print("\n=== Simulating Agent Flow ===\n")
    print("User: 'I want to buy something'\n")
    
    # Step 1: Agent discovers merchants (proactive discovery)
    print("Agent: Let me find available merchants for you...\n")
    result = await host_agent.discover_merchants()
    print(f"Found {result['total_found']} merchants:")
    for merchant in result['discovered_merchants']:
        print(f"  - {merchant['name']}: {merchant['description']}")
        if merchant['skills']:
            print(f"    Skills: {', '.join(merchant['skills'])}")
    
    # Step 2: Agent selects first merchant from discovered list
    if result['discovered_merchants']:
        first_merchant = result['discovered_merchants'][0]
        merchant_name = first_merchant['name']
        print(f"\nAgent: Let me help you buy something from {merchant_name.replace('_merchant', '').replace('_', ' ').title()}.\n")
        
        # Step 3: Agent sends purchase request
        print(f"Agent: Sending purchase request to {merchant_name}...\n")
        response = await host_agent.ask_merchant(merchant_name, "I want to buy something")
        
        print(f"Response status: {response['status']}")
        if response['status'] == 'payment_required':
            print("✅ Payment is required - X402 protocol activated!")
            print(f"Message: {response.get('message', '')}")
        elif response['status'] == 'success':
            print(f"Merchant response: {response.get('message', '')[:300]}...")
            if "Payment verified" in response.get('message', ''):
                print("\n✅ Purchase completed successfully with payment!")
            else:
                print("\n⚠️  Received product list instead of purchase flow")
        else:
            print(f"Error: {response.get('message', 'Unknown error')}")
        
        # Test with second merchant if available
        if len(result['discovered_merchants']) > 1:
            second_merchant = result['discovered_merchants'][1]
            second_merchant_name = second_merchant['name']
            print(f"\n=== Alternative Test: {second_merchant_name.replace('_merchant', '').replace('_', ' ').title()} ===\n")
            print("User: 'I want to buy something else'\n")
            
            print(f"Agent: Let me help you buy from {second_merchant_name.replace('_merchant', '').replace('_', ' ').title()}...\n")
            response = await host_agent.ask_merchant(second_merchant_name, "I want to buy something")
            
            print(f"Response status: {response['status']}")
            if response['status'] == 'success':
                print(f"Merchant response: {response.get('message', '')[:300]}...")
    else:
        print("No merchants discovered!")
    
    print("\n=== Test Complete ===\n")

if __name__ == "__main__":
    asyncio.run(test_agent_flow())