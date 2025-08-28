#!/usr/bin/env python3
"""
Test specific purchase with exact product name.
"""

import asyncio
from client.host import host_agent

async def test_specific_purchase():
    """Test purchasing a specific item with exact name."""
    print("\n=== Testing Specific Purchase ===\n")
    
    # Step 1: Discover merchants
    print("Step 1: Discovering merchants...")
    result = await host_agent.discover_merchants()
    print(f"Found {result['total_found']} merchants")
    
    if not result['discovered_merchants']:
        print("No merchants found!")
        return
    
    # Step 2: Get product catalog
    merchant_name = result['discovered_merchants'][0]['name']  # penny_snacks_merchant
    print(f"\nStep 2: Getting product catalog from {merchant_name}...")
    
    catalog_response = await host_agent.ask_merchant(merchant_name, "What products do you have?")
    print(f"Catalog status: {catalog_response['status']}")
    print(f"Catalog: {catalog_response.get('message', 'No message')[:200]}...")
    
    # Step 3: Purchase specific item
    print(f"\nStep 3: Purchasing 'Chocolate Bar' from {merchant_name}...")
    purchase_response = await host_agent.ask_merchant(merchant_name, "I want to buy Chocolate Bar")
    
    print(f"Purchase status: {purchase_response['status']}")
    print(f"Purchase message: {purchase_response.get('message', 'No message')}")
    
    if purchase_response['status'] == 'success':
        message = purchase_response.get('message', '')
        if 'Price Paid:' in message:
            print("\n✅ SUCCESS: Purchase completed with specific pricing!")
        else:
            print("\n⚠️  Purchase completed but no pricing info found")
    else:
        print(f"\n❌ Purchase failed: {purchase_response.get('message', 'Unknown error')}")

if __name__ == "__main__":
    asyncio.run(test_specific_purchase())