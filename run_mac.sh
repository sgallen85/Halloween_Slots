#!/bin/bash
# Launches the game using the local virtual environment set up by
# setup_mac_env.sh. Run setup_mac_env.sh once first if you haven't yet.
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "No .venv found - run ./setup_mac_env.sh first."
    exit 1
fi

source .venv/bin/activate
python3 main.py
