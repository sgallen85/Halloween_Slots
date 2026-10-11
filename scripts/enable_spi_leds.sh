#!/bin/bash
# One-time setup so the LED strip runs on GPIO10 (SPI) and the game no longer
# needs sudo. Run as your normal user (it asks for sudo where needed):
#
#     ./scripts/enable_spi_leds.sh
#
# Then: move the strip's data wire to GPIO10 (physical pin 19), set
# led_pin = 10 in config.py, and reboot. Safe to run more than once.
set -e

cd "$(dirname "$0")/.."   # project folder
ME="$(id -un)"

if [ "$ME" = "root" ]; then
    echo "Run this as your normal user, not with sudo - it uses sudo itself."
    exit 1
fi

# Raspberry Pi OS keeps config.txt in /boot/firmware on Bookworm, /boot before that
CONFIG=/boot/firmware/config.txt
[ -f "$CONFIG" ] || CONFIG=/boot/config.txt
if [ ! -f "$CONFIG" ]; then
    echo "Couldn't find config.txt - is this a Raspberry Pi?"
    exit 1
fi
MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)"
echo "Pi model: $MODEL"
echo "Boot config: $CONFIG"

echo "=== Turning on SPI ==="
if command -v raspi-config > /dev/null; then
    sudo raspi-config nonint do_spi 0
elif ! grep -q "^dtparam=spi=on" "$CONFIG"; then
    echo "dtparam=spi=on" | sudo tee -a "$CONFIG" > /dev/null
fi

# The SPI clock follows the GPU core clock, which the Pi changes on the fly -
# that garbles the LED data unless the core clock is pinned.
add_line() {
    grep -q "^$1" "$CONFIG" || echo "$1" | sudo tee -a "$CONFIG" > /dev/null
}
case "$MODEL" in
    *"Raspberry Pi 4"*|*"Raspberry Pi 400"*|*"Compute Module 4"*)
        echo "=== Pinning the core clock (Pi 4) ==="
        add_line "core_freq=500"
        add_line "core_freq_min=500"
        ;;
    *"Raspberry Pi 3"*|*"Raspberry Pi Zero 2"*)
        echo "=== Pinning the core clock (Pi 3 / Zero 2) ==="
        add_line "core_freq=250"
        ;;
    *"Raspberry Pi 5"*)
        echo "!!! The LED library (rpi_ws281x) doesn't support the Pi 5 yet."
        ;;
esac

echo "=== Giving $ME access to the button (gpio) and LED strip (spi) ==="
sudo usermod -aG gpio,spi "$ME"

# Files created while the game ran under sudo (logs, light maps) belong to
# root; hand them back so the game can write them as a normal user.
echo "=== Making sure $ME owns the game folder ==="
sudo chown -R "$ME":"$ME" .

echo ""
echo "Done. Next:"
echo "  1. Shut down and move the LED data wire to GPIO10 (physical pin 19)."
echo "  2. Set  led_pin = 10  in config.py."
echo "  3. Boot up and start the game with ./launch.sh - no sudo needed."
