#!/bin/bash
# Launches the game using the local virtual environment set up by
# scripts/setup_mac.sh. Run scripts/setup_mac.sh once first if you haven't yet.
set -e

cd "$(dirname "$0")/.."   # project folder

if [ ! -d ".venv" ]; then
    echo "No .venv found - run ./scripts/setup_mac.sh first."
    exit 1
fi

source .venv/bin/activate
python3 main.py
