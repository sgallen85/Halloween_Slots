#!/bin/bash
# One-time setup: creates a local Python virtual environment (.venv) in this
# project folder and installs Kivy into it. Safe to re-run any time - it
# just reuses the existing .venv if one's already there.
set -e

cd "$(dirname "$0")"

echo "Using: $(python3 --version)"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    python3 -m venv .venv
else
    echo ".venv already exists, reusing it."
fi

source .venv/bin/activate

echo "Installing Kivy (this can take a minute the first time) ..."
pip install --upgrade pip
# Pinned to match the version running on the Pi, so behavior stays consistent
# between your Mac testing and the real thing.
pip install "kivy[base]==2.3.1"

echo ""
echo "Done. Verifying install:"
python -c "import kivy; print('Kivy', kivy.__version__, 'OK')"

echo ""
echo "Setup complete. From now on, use ./run_mac.sh to launch the game -"
echo "it activates this environment for you automatically."
