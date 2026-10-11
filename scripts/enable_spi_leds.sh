#!/bin/bash
# One-time setup so the LED strip runs on GPIO10 (SPI) and the game no longer
# needs sudo. Run it either way - it asks for your password where needed:
#
#     ./scripts/enable_spi_leds.sh
#
# Then: move the strip's data wire to GPIO10 (physical pin 19), set
# led_pin = 10 in config.py, and reboot. Safe to run more than once.
set -e

cd "$(dirname "$0")/.."   # project folder
ME="$(id -un)"
if [ "$ME" = "root" ]; then
    # Started with sudo - set things up for the user who ran sudo
    ME="${SUDO_USER:-}"
    if [ -z "$ME" ] || [ "$ME" = "root" ]; then
        echo "Run this as your normal user (e.g. admin), not as root."
        exit 1
    fi
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
if grep -q "^dtparam=spi=on" "$CONFIG"; then
    echo "already on"
elif grep -q "^#\s*dtparam=spi=on" "$CONFIG"; then
    sudo sed -i 's/^#\s*dtparam=spi=on/dtparam=spi=on/' "$CONFIG"   # uncomment the stock line
else
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

echo "=== Checking ==="
FAILED=0
if grep -q "^dtparam=spi=on" "$CONFIG"; then echo "ok  SPI turned on in $CONFIG"; else echo "!!  SPI is NOT on in $CONFIG"; FAILED=1; fi
case "$MODEL" in
    *"Raspberry Pi 4"*|*"Raspberry Pi 400"*|*"Compute Module 4"*)
        if grep -q "^core_freq_min=500" "$CONFIG"; then echo "ok  core clock pinned"; else echo "!!  core clock NOT pinned"; FAILED=1; fi ;;
esac
if id -nG "$ME" | grep -qw spi; then echo "ok  $ME is in the spi group"; else echo "!!  $ME is NOT in the spi group"; FAILED=1; fi
if [ "$FAILED" = "1" ]; then
    echo "Something above didn't take - see the !! lines."
    exit 1
fi

echo ""
echo "Done. Next:"
echo "  1. If you haven't yet: shut down and move the LED data wire to GPIO10"
echo "     (physical pin 19), and set  led_pin = 10  in config.py."
echo "  2. REBOOT - SPI and the group change only take effect after a restart."
echo "  3. Check with:  python3 tools/led_test.py   then start with ./launch.sh"
