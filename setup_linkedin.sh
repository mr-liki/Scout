#!/bin/bash

# CADDY LinkedIn Job Tracker Setup Script
# This script helps you set up LinkedIn job tracking quickly

echo "=============================================="
echo "🚀 CADDY LinkedIn Job Tracker Setup"
echo "=============================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Check for .env file
echo ""
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✓ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your API keys!"
    echo ""
else
    echo "✓ .env file already exists"
fi

# Check for API keys
echo ""
echo "🔑 Checking API keys..."

if [ -z "$RAPID_API_KEY" ]; then
    echo "⚠️  RAPID_API_KEY not set"
    echo ""
    echo "To get your FREE RapidAPI key:"
    echo "1. Visit: https://rapidapi.com/"
    echo "2. Sign up (it's free!)"
    echo "3. Subscribe to: LinkedIn Data API"
    echo "   https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api"
    echo "4. Copy your API key"
    echo "5. Add to .env file: RAPID_API_KEY=your_key_here"
    echo ""
    echo "Then run: source .env"
else
    echo "✓ RAPID_API_KEY is set"
fi

if [ -z "$HF_API_KEY" ]; then
    echo "ℹ️  HF_API_KEY not set (optional for better AI chat)"
    echo "   Get one at: https://huggingface.co/settings/tokens"
else
    echo "✓ HF_API_KEY is set"
fi

echo ""
echo "=============================================="
echo "✅ Setup Complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. If you haven't already, add your RAPID_API_KEY to .env"
echo "2. Load environment variables: source .env"
echo "3. Run CADDY with LinkedIn: python caddy_with_linkedin.py"
echo ""
echo "Quick commands once inside CADDY:"
echo "  - add job search: Python Developer, Remote, Full-time"
echo "  - list jobs"
echo "  - start monitoring"
echo ""
echo "📚 Full documentation: See LINKEDIN_SETUP.md"
echo ""
