#!/usr/bin/env python3
"""Test optimized batch payment functionality."""

import asyncio
import os
from client.host import SimpleHostAgent

async def test_optimized_batch():
    """Test that optimized batch payments work correctly."""
    print("🧪 Testing optimized batch payment transaction structure...")
    
    # Initialize host agent in batch mode
    host = SimpleHostAgent(batch_mode=True)
    
    # Discover merchants
    discovery_result = await host.discover_merchants()
    print(f"📋 Discovered {discovery_result['total_found']} merchants")
    
    # Test multiple purchases to trigger batch payment
    test_purchases = [
        ("penny_snacks_merchant", "I want to buy a cheese sandwich"),
        ("tiny_tools_merchant", "I'll take a screwdriver"),
        ("digital_bits_merchant", "I want to buy cloud storage"),
    ]
    
    print("🛒 Making multiple purchase requests...")
    for merchant, request in test_purchases:
        result = await host.ask_merchant(merchant, request)
        print(f"  {merchant}: {result.get('status')} - ${result.get('message', 'No message')[:50]}...")
    
    # Process batch payment
    print("💰 Processing batch payment with optimized transaction...")
    batch_result = await host.process_batch_payments()
    
    if batch_result.get("status") == "success":
        print("✅ Optimized batch payment completed successfully!")
        print(f"📊 Processed {batch_result.get('processed_count')} payments")
        print(f"💵 Total amount: ${batch_result.get('total_amount', 0):.3f}")
        
        # Check the receipt format
        receipt = batch_result.get('message', '')
        if 'Purchase Receipt' in receipt and len(receipt.split('\n')) < 20:
            print("✅ Receipt format is chat-friendly")
        else:
            print("⚠️ Receipt may be too verbose for chat")
            
        return True
    else:
        print(f"❌ Batch payment failed: {batch_result.get('message', 'Unknown error')}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_optimized_batch())
    exit(0 if success else 1)