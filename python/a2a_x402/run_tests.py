#!/usr/bin/env python3
"""Simple test runner for a2a_x402 when pytest is not available."""

import sys
import os
import importlib.util
from pathlib import Path

def run_tests():
    """Run tests without pytest."""
    print("=== Simple Test Runner ===")
    
    # Add current directory to Python path for imports
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))
    
    # Try to import and check basic functionality
    try:
        print("Testing basic imports...")
        
        # Test importing main module
        import a2a_x402
        print("✓ a2a_x402 module imported successfully")
        
        # Test importing key components
        from a2a_x402 import X402PaymentRequiredException
        print("✓ X402PaymentRequiredException imported successfully")
        
        from a2a_x402.executors import X402ServerExecutor
        print("✓ X402ServerExecutor imported successfully")
        
        from a2a_x402.core.helpers import require_payment
        print("✓ require_payment helper imported successfully")
        
        # Test basic functionality
        print("\nTesting basic functionality...")
        
        # Test exception creation
        exception = X402PaymentRequiredException.for_service(
            price="$1.00",
            pay_to_address="0xtest123",
            resource="/test"
        )
        print("✓ X402PaymentRequiredException.for_service() works")
        
        # Test helper function
        helper_exception = require_payment(
            price="$2.00",
            pay_to_address="0xtest456",
            resource="/helper-test"
        )
        print("✓ require_payment() helper works")
        
        # Verify exception properties
        accepts = exception.get_accepts_array()
        if len(accepts) == 1:
            print("✓ Exception accepts array is correct")
        else:
            print("✗ Exception accepts array is incorrect")
            return False
            
        print("\n=== All basic tests passed! ===")
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)