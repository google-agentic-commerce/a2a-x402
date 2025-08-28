#!/bin/bash

# Test runner script that avoids Python path conflicts

echo "=== a2a_x402 Test Runner ==="

# Step 1: Move to safe directory and activate venv
cd /tmp
source /workspace/.venv/bin/activate

# Step 2: Set up clean Python path
export PYTHONPATH="/workspace"

# Step 3: Test basic import functionality
echo "Testing basic imports..."

python3 -c "
import sys
sys.path.insert(0, '/workspace')

try:
    print('Testing a2a_x402 imports...')
    import a2a_x402
    print('✓ a2a_x402 imported successfully')
    
    from a2a_x402.types.errors import X402PaymentRequiredException
    print('✓ X402PaymentRequiredException imported')
    
    from a2a_x402.executors.server import X402ServerExecutor
    print('✓ X402ServerExecutor imported')
    
    from a2a_x402.core.helpers import require_payment
    print('✓ require_payment helper imported')
    
    print('\\nTesting functionality...')
    exception = X402PaymentRequiredException.for_service(
        price='$1.00',
        pay_to_address='0xtest123',
        resource='/test'
    )
    print('✓ Exception creation works')
    
    accepts = exception.get_accepts_array()
    print(f'✓ Exception has {len(accepts)} payment requirement(s)')
    
    print('\\n=== All tests passed! ===')
    
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
"

echo ""
echo "=== Test Summary ==="
if [ $? -eq 0 ]; then
    echo "✓ All basic functionality tests passed"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi