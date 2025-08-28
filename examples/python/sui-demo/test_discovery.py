#!/usr/bin/env python3
"""
Simple test for merchant discovery.
"""

import asyncio
from client.host import host_agent

async def test_discovery():
    """Test just the discovery functionality."""
    print("Testing merchant discovery...")
    
    try:
        result = await host_agent.discover_merchants()
        print(f"Discovery result: {result}")
        
        if result.get('discovered_merchants'):
            print(f"\nFound {len(result['discovered_merchants'])} merchants:")
            for merchant in result['discovered_merchants']:
                print(f"  - {merchant['name']}: {merchant['description']}")
        else:
            print("No merchants discovered!")
            
    except Exception as e:
        import traceback
        print(f"Discovery failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_discovery())