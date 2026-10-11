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
    alsa-utils \
    ffmpeg python3-numpy   # only for tools/make_light_maps.py (music lights)

# Installed system-wide (with sudo) so they work both for your normal user
# and under sudo - the game needs sudo when the LED strip is on GPIO21.
echo "=== Installing Python packages ==="
sudo pip3 install "kivy[base]==2.3.1" --break-system-packages
sudo pip3 install RPi.GPIO rpi_ws281x --break-system-packages

echo ""
echo "=== Verifying install ==="
sudo python3 -c "import kivy; print('Kivy', kivy.__version__, 'OK')"
sudo python3 -c "import RPi.GPIO; print('RPi.GPIO OK')"
sudo python3 -c "import rpi_ws281x; print('rpi_ws281x OK')"

echo ""
echo "Setup complete. For the LED strip on GPIO10 (no sudo needed), also run:"
echo "  ~/Halloween_Slots/scripts/enable_spi_leds.sh"
echo "Start the game with:"
echo "  ~/Halloween_Slots/launch.sh"
