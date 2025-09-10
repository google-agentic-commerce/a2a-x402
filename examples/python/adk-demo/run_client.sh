#!/bin/bash

# EigenDA Client Startup Script

echo "🚀 Starting EigenDA Storage Client..."
echo "===================================="

# Check if server is running
if ! curl -s http://localhost:10000/agents/eigenda_agent/.well-known/agent-card.json > /dev/null 2>&1; then
    echo "❌ Server is not running. Please start the server first with:"
    echo "   ./run_eigenda_demo.sh"
    exit 1
fi

echo "✅ Server is running and ready!"
echo ""
echo "📝 EigenDA Storage Client"
echo "========================"
echo "Available commands:"
echo "  - Store text: 'Store this message: <your text>'"
echo "  - Retrieve text: 'Get text with certificate <certificate>'"
echo "  - List stored items: 'Show my stored certificates'"
echo ""
echo "💰 Pricing:"
echo "  - Storage: $0.01 per operation"
echo "  - Retrieval: FREE"
echo ""
echo "Starting client..."
echo "===================================="

cd client_agent && python -m google.adk.cli