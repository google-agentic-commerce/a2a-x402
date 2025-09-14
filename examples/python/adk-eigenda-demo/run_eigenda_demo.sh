#!/bin/bash

# EigenDA Storage Demo Startup Script

echo "🚀 Starting EigenDA Storage Demo..."
echo "=================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check for .env file
if [ ! -f .env ]; then
    echo "❌ .env file not found. Creating template..."
    cat > .env << EOF
# Google AI API Key (required)
GOOGLE_API_KEY=your_google_api_key_here

# Use mock payments for testing (set to false for real payments)
USE_MOCK_FACILITATOR=true

# For real payments, uncomment and set:
# MERCHANT_PRIVATE_KEY=your_private_key_here
EOF
    echo "✅ Created .env template. Please edit it with your GOOGLE_API_KEY."
    exit 1
fi

# Check if GOOGLE_API_KEY is set
if grep -q "your_google_api_key_here" .env; then
    echo "❌ Please set your GOOGLE_API_KEY in the .env file"
    exit 1
fi

# Clean up any existing EigenDA container
echo "🧹 Cleaning up any existing EigenDA containers..."
docker rm -f eigenda-proxy 2>/dev/null || true

# Start the server
echo "🚀 Starting EigenDA storage server on port 10000..."
echo "The server will automatically start the EigenDA Docker container."
echo ""
echo "Once the server is ready, open a new terminal and run:"
echo "  cd client_agent && python -m google.adk.cli"
echo ""
echo "Press Ctrl+C to stop the server."
echo "=================================="

# Run the server
python -m server --host localhost --port 10000