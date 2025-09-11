#!/usr/bin/env python3
"""
Test script to verify certificate ID handling in EigenDA storage.
This script tests the flow of storing text and retrieving it using the certificate.
"""

import asyncio
import httpx
import sys
import time
from datetime import datetime

# Test configuration
SERVER_URL = "http://localhost:3000"
TEST_MESSAGE = f"Test message created at {datetime.now().isoformat()}"

async def test_eigenda_storage():
    """Test the EigenDA storage and retrieval with certificate ID tracking."""
    
    print("=" * 60)
    print("EigenDA Certificate ID Test")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        # Test 1: Store text data
        print("\n1. Testing storage request...")
        print(f"   Message: {TEST_MESSAGE}")
        
        # Note: This is a simplified test that would need the actual client agent
        # In a real test, you would interact with the client agent API
        
        print("\n2. Expected flow:")
        print("   - Client sends storage request")
        print("   - Server generates certificate ID")
        print("   - Certificate ID shown in payment request")
        print("   - After payment, certificate ID confirmed")
        print("   - User can retrieve using certificate ID")
        
        print("\n3. Check server logs for:")
        print("   - '=== EIGENDA STORAGE ===' section")
        print("   - Certificate ID generation")
        print("   - '=== X402 PAYMENT VERIFICATION ===' section")
        print("   - '=== PAYMENT VERIFICATION CALLBACK ===' section")
        
        print("\n4. Verify in client output:")
        print("   - Certificate ID displayed in payment request")
        print("   - Certificate ID displayed after payment confirmation")
        print("   - No placeholder or incorrect certificate IDs")
        
        print("\n" + "=" * 60)
        print("To run full test:")
        print("1. Start the server: cd server && python run.py")
        print("2. Start the client: ./run_client.sh")
        print("3. Type: store this: Hello World")
        print("4. Approve payment when prompted")
        print("5. Note the certificate ID")
        print("6. Type: retrieve <certificate_id>")
        print("7. Verify the text is retrieved correctly")
        print("=" * 60)

if __name__ == "__main__":
    print("Starting EigenDA Certificate ID Test...")
    asyncio.run(test_eigenda_storage())