#!/bin/bash
# Start the Pokemon Red Dashboard
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

echo "🎮 Pokemon Red Dashboard"
echo "========================"

# Create venv if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install deps
echo "Installing dependencies..."
pip install -q fastapi uvicorn

# Start server
echo ""
echo "Starting dashboard at http://localhost:3456"
echo "Press Ctrl+C to stop"
echo ""

cd "$SCRIPT_DIR"
python server.py
