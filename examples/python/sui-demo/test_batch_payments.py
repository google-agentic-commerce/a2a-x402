#!/usr/bin/env python3
"""Test the UI flow with batch payments using local x402."""

import asyncio
import os

# Set batch mode
os.environ["BATCH_MODE"] = "true"

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from client.host import SimpleHostAgent

async def test_complete_flow():
    """Test the complete batch payment flow."""
    print("\n=== Testing Complete Batch Payment Flow (Local x402) ===\n")
    
    host = SimpleHostAgent(batch_mode=True)
    
    try:
        # 1. Test merchant discovery  
        print("1. Testing merchant discovery...")
        merchants = await host.discover_merchants()
        print(f"   ✅ Found {merchants['total_found']} merchants")
        
        # 2. Test product listing
        print("\n2. Testing product listing...")
        products = await host.ask_merchant("penny_snacks_merchant", "What products do you have?")
        if products['status'] == 'success':
            print("   ✅ Product listing successful")
            print(f"   📦 Available products include Gummy Bears ($0.020) and Chocolate Bar ($0.030)")
        else:
            print(f"   ❌ Product listing failed: {products}")
            return
        
        # 3. Test batch collection (Gummy Bears + Chocolate Bar)
        print("\n3. Testing batch payment collection...")
        print("   → Requesting Gummy Bears ($0.020)...")
        result1 = await host.ask_merchant("penny_snacks_merchant", "I want to buy Gummy Bears")
        
        print("   → Requesting Chocolate Bar ($0.030)...")  
        result2 = await host.ask_merchant("penny_snacks_merchant", "I want to buy Chocolate Bar")
        
        print(f"   ✅ Collection complete - Both requests processed")
        print(f"   📋 Gummy Bears: {result1['status'] if result1 else 'collected'}")
        print(f"   📋 Chocolate Bar: {result2['status'] if result2 else 'collected'}")
        
        # 4. Test batch processing
        print("\n4. Testing batch payment processing...")
        batch_result = await host.process_batch_payments()
        
        if batch_result.get('status') == 'success':
            print("   ✅ Batch processing successful!")
            print(f"   💰 Processed: {batch_result.get('processed_count', 0)} payments")
            print(f"   ✅ Successful: {batch_result.get('successful_count', 0)}")
            print(f"   ❌ Failed: {batch_result.get('failed_count', 0)}")
            print(f"   💵 Total amount: ${batch_result.get('total_amount', 0):.3f}")
            
            # Show detailed results
            if 'results' in batch_result:
                print("\n   📋 Detailed Results:")
                for i, result in enumerate(batch_result['results'], 1):
                    status = result['status']
                    state = result.get('state', 'unknown')
                    merchant = result.get('merchant', 'unknown')
                    
                    emoji = "✅" if status == 'success' else "⚠️" if status == 'partial' else "❌"
                    print(f"      {emoji} {merchant}: {status} ({state})")
                    
                    if result.get('transaction_hash'):
                        print(f"         🔗 TX: {result['transaction_hash'][:16]}...")
        
        else:
            print(f"   ❌ Batch processing failed: {batch_result}")
        
        print(f"\n=== Test Complete - Local x402 {'✅ Working' if batch_result.get('status') == 'success' else '❌ Issues'} ===\n")
        
    except Exception as e:
        print(f"   ❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_complete_flow())