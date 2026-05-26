#!/bin/bash

# SecureFlow Frontend Setup Script
# This script sets up and builds the React frontend

set -e

echo "🚀 SecureFlow Frontend Setup"
echo "============================"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "   Install from: https://nodejs.org/"
    exit 1
fi

echo "✅ Node.js v$(node --version)"
echo "✅ npm v$(npm --version)"

# Change to frontend directory
cd frontend

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
npm install

# Build the frontend
echo ""
echo "🔨 Building React app..."
npm run build

echo ""
echo "✅ Frontend build complete!"
echo ""
echo "📍 Output: secureflow/static/dist/"
echo "🌐 Access dashboard at: http://localhost:5000/ui"
echo ""
echo "To start the server:"
echo "  python -m secureflow server-launch"
