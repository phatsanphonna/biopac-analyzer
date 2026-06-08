#!/bin/bash
# BIOPAC Analyzer Launcher

# Change to the script's directory
cd "$(dirname "$0")"

echo "=========================================="
echo " Starting BIOPAC Physiological Analyzer..."
echo "=========================================="

# Run using uv
uv run app.py
