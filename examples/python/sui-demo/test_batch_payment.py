#!/usr/bin/env python3
"""
Test batch payment functionality directly.
"""

import asyncio
import os
import sys
sys.path.append('.')

from client.host import SimpleHostAgent

async def test_batch_payment():
    """Test a batch payment with multiple merchants."""
    print("[TEST] Starting batch payment test")
    
    # Create host agent in batch mode
    host = SimpleHostAgent(batch_mode=True)
    
    # Simulate payment requirements from multiple merchants
    print("[TEST] Simulating requests to multiple merchants...")
    
    try:
        # This will trigger the batch payment flow
        print("[TEST] Processing batch payments...")
        result = await host.process_batch_payments()
        
        print(f"[TEST] Batch payment result: {result}")
        
    except Exception as e:
        print(f"[TEST] Error in batch payment: {e}")

if __name__ == "__main__":
    asyncio.run(test_batch_payment())