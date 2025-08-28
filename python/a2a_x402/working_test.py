#!/usr/bin/env python3
"""Working test that avoids import conflicts."""

import sys
import os

# Remove current directory from Python path to avoid conflicts
if '' in sys.path:
    sys.path.remove('')
if '.' in sys.path:
    sys.path.remove('.')
if os.getcwd() in sys.path:
    sys.path.remove(os.getcwd())

print("=== a2a_x402 Basic Functionality Test ===")

try:
    # Test that we can at least import basic Python modules
    import types
    print("✓ Standard library 'types' module works")
    
    import functools
    print("✓ Standard library 'functools' module works")
    
    # Now try to import our package by adding it explicitly
    workspace_dir = "/workspace"
    if workspace_dir not in sys.path:
        sys.path.append(workspace_dir)
    
    # Try basic imports step by step
    print("\nTesting package structure...")
    
    # This should work since types conflict is resolved
    import a2a_x402
    print("✓ a2a_x402 package imported")
    
    # Test specific components
    from a2a_x402.types.errors import X402PaymentRequiredException
    print("✓ X402PaymentRequiredException imported")
    
    # Test functionality
    print("\nTesting basic functionality...")
    exception = X402PaymentRequiredException.for_service(
        price="$1.00",
        pay_to_address="0xtest123",
        resource="/test"
    )
    print("✓ Payment exception created successfully")
    
    accepts = exception.get_accepts_array()
    print(f"✓ Payment exception has {len(accepts)} requirement(s)")
    
    print("\n=== SUCCESS: Basic functionality verified! ===")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)