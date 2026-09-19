#!/bin/bash
# One-time setup for a fresh Raspberry Pi OS install - installs everything
# needed to run Halloween Slots. Safe to re-run any time.
set -e

echo "=== Updating package lists ==="
sudo apt-get update

echo "=== Installing system libraries Kivy needs ==="
sudo apt-get install -y \
    build-essential \
    pkg-config \
    git \
    python3-pip python3-dev python3-setuptools \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libgl1-mesa-dev libgles2-mesa-dev \
    libgstreamer1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    libmtdev-dev \
    libjpeg-dev libpng-dev zlib1g-dev \
    alsa-utils

echo "=== Installing Python packages ==="
pip3 install --upgrade pip --break-system-packages
pip3 install "kivy[base]==2.3.1" --break-system-packages
pip3 install RPi.GPIO --break-system-packages

echo ""
echo "=== Verifying install ==="
python3 -c "import kivy; print('Kivy', kivy.__version__, 'OK')"
python3 -c "import RPi.GPIO; print('RPi.GPIO OK')"

echo ""
echo "Setup complete. Run the game with:"
echo "  cd ~/slots/Halloween_Slots && python3 main.py"
