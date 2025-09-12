#!/bin/bash

# EigenDA CLI Client Startup Script

echo "🚀 Starting EigenDA Storage CLI Client..."
echo "===================================="

# Check if server is running
if ! curl -s http://localhost:10000/agents/eigenda_agent/.well-known/agent-card.json > /dev/null 2>&1; then
    echo "❌ Server is not running. Please start the server first with:"
    echo "   uv run server"
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
echo "Starting CLI client..."
echo "===================================="

# Set environment variables to suppress warnings
export PYTHONWARNINGS="ignore::UserWarning"

# Run using uv with the ADK CLI
# The warnings will still appear but won't interfere with the CLI
uv run python -m google.adk.cli run cli_agent