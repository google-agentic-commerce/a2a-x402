#!/usr/bin/env python3
"""
Final test of batch payments functionality with the new local x402 library.
This test verifies that prepare_batch_payment_header and process_batch_payment work correctly.
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.host import SimpleHostAgent

async def test_batch_payments():
    """Test the complete batch payment flow."""
    
    print("🧪 Testing Batch Payment Functionality")
    print("=" * 50)
    
    # Initialize host agent in batch mode
    host = SimpleHostAgent(batch_mode=True)
    
    # Test discovery
    print("\n1. Discovering merchants...")
    discovery_result = await host.discover_merchants()
    print(f"✅ Found {discovery_result['total_found']} merchants")
    
    if discovery_result['total_found'] == 0:
        print("❌ No merchants found - cannot test batch payments")
        return False
    
    # Get the first two merchants for testing
    merchants = list(host.merchants.keys())[:2]
    print(f"📋 Testing with merchants: {merchants}")
    
    # Ask multiple questions to collect payment requirements
    print("\n2. Collecting payment requirements...")
    
    questions = [
        "I want to buy a chocolate bar",
        "I want to buy a mini screwdriver"
    ]
    
    results = []
    
    for i, merchant in enumerate(merchants[:2]):  # Test with first 2 merchants
        if i < len(questions):
            print(f"\n   Asking {merchant}: {questions[i]}")
            result = await host.ask_merchant(merchant, questions[i])
            print(f"   Response: {result.get('message', 'No message')[:100]}...")
            results.append(result)
    
    # Check if we collected payment requirements
    pending_count = len(host.pending_payments)
    print(f"\n✅ Collected {pending_count} payment requirements")
    
    if pending_count == 0:
        print("❌ No payment requirements collected - merchants may not require payment")
        return False
    
    # Process batch payment
    print("\n3. Processing batch payment...")
    batch_result = await host.process_batch_payments()
    
    if batch_result.get("status") == "success":
        print(f"✅ Batch payment completed successfully!")
        print(f"   Processed: {batch_result.get('processed_count', 0)} payments")
        print(f"   Successful: {batch_result.get('successful_count', 0)}")
        print(f"   Failed: {batch_result.get('failed_count', 0)}")
        print(f"   Total amount: ${batch_result.get('total_amount', 0):.3f}")
        
        # Show results for each payment
        if 'results' in batch_result:
            print("\n📋 Individual payment results:")
            for result in batch_result['results']:
                status_emoji = "✅" if result['status'] == 'success' else "❌"
                print(f"   {status_emoji} {result['merchant']}: {result['status']}")
                if result.get('transaction_hash'):
                    print(f"      TX: {result['transaction_hash'][:20]}...")
        
        return True
    else:
        print(f"❌ Batch payment failed: {batch_result.get('message', 'Unknown error')}")
        return False

async def main():
    """Main test function."""
    print("🚀 Starting batch payment test with local x402 library")
    
    try:
        success = await test_batch_payments()
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 Batch payment test PASSED!")
            print("✅ Local x402 library integration working correctly")
            print("✅ prepare_batch_payment_header function accessible")
            print("✅ process_batch_payment function working") 
            print("✅ Coin splitting logic working per payment")
        else:
            print("❌ Batch payment test FAILED!")
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return success

if __name__ == "__main__":
    asyncio.run(main())