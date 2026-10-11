#!/usr/bin/env python3
"""
Standalone LED strip test - checks wiring/library BEFORE trusting it wired
into the full game. With the strip on GPIO10 (SPI) it runs as a normal user;
on GPIO21 it needs sudo, same as the game:

    python3 tools/led_test.py          # GPIO10
    sudo python3 tools/led_test.py     # GPIO21

Reads the same led_count / led_pin / led_channel / led_brightness settings
from config.py that the real game uses, so a successful run here means the
same settings will work once wired into main.py.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config   # noqa: E402 - the game's config.py, one folder up

try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:
    print("rpi_ws281x not installed. Run:")
    print("  pip3 install rpi_ws281x --break-system-packages")
    raise SystemExit(1)

LED_COUNT = getattr(config, 'led_count', 60)
LED_PIN = getattr(config, 'led_pin', 21)
LED_CHANNEL = getattr(config, 'led_channel', 0)
LED_BRIGHTNESS = getattr(config, 'led_brightness', 128)

print("LED strip test - {} pixels on GPIO{}, channel {}, brightness {}".format(
    LED_COUNT, LED_PIN, LED_CHANNEL, LED_BRIGHTNESS))



def check_spi_setup():
    """GPIO10 drives the strip through the SPI port. Checks each piece
    scripts/enable_spi_leds.sh sets up and says which one is missing."""
    import glob, grp, pwd
    ok = True
    print("\nChecking the SPI setup for GPIO10:")
    dev = '/dev/spidev0.0'
    if not os.path.exists(dev):
        print("  X  {} doesn't exist - SPI is off. Run scripts/enable_spi_leds.sh,".format(dev))
        print("     then REBOOT (SPI only turns on at boot).")
        ok = False
    elif not os.access(dev, os.R_OK | os.W_OK):
        user = pwd.getpwuid(os.getuid()).pw_name
        listed = user in grp.getgrnam('spi').gr_mem if 'spi' in [g.gr_name for g in grp.getgrall()] else False
        print("  X  No permission to use {}.".format(dev))
        if listed:
            print("     You were added to the 'spi' group but it isn't active yet - log out")
            print("     and back in, or reboot.")
        else:
            print("     Run scripts/enable_spi_leds.sh (adds you to the 'spi' group), then reboot.")
        ok = False
    else:
        print("  ok {} is there and usable".format(dev))
    for cfg in ('/boot/firmware/config.txt', '/boot/config.txt'):
        if os.path.exists(cfg):
            text = open(cfg).read()
            model = open('/proc/device-tree/model').read() if os.path.exists('/proc/device-tree/model') else ''
            if 'Raspberry Pi 4' in model and 'core_freq_min=500' not in text:
                print("  !  {} has no core_freq_min=500 - on a Pi 4 the LED data can".format(cfg))
                print("     come out garbled or not at all. Run scripts/enable_spi_leds.sh and reboot.")
            else:
                print("  ok core clock setting looks right for this Pi")
            break
    print()
    return ok


if LED_PIN == 10 and not check_spi_setup():
    raise SystemExit(1)

strip = PixelStrip(LED_COUNT, LED_PIN, 800000, 10, False, LED_BRIGHTNESS, LED_CHANNEL)
try:
    strip.begin()
except RuntimeError as e:
    print("The LED library couldn't start the strip: {}".format(e))
    if LED_PIN != 10:
        print("On GPIO{} this needs sudo:  sudo python3 tools/led_test.py".format(LED_PIN))
    raise SystemExit(1)


def set_all(r, g, b):
    color = Color(r, g, b)
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
    strip.show()


def off():
    set_all(0, 0, 0)


COLOR_TESTS = [
    ("Red", (255, 0, 0)),
    ("Green", (0, 255, 0)),
    ("Blue", (0, 0, 255)),
    ("White", (255, 255, 255)),
    ("Orange (idle ambient color)", (255, 80, 0)),
]

print("Press Ctrl+C at any time to stop and turn off.\n")

try:
    for name, rgb in COLOR_TESTS:
        print("Showing: {}".format(name))
        set_all(*rgb)
        time.sleep(2)

    print("Chasing one pixel down the strip (confirms LED count and wiring direction)...")
    off()
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(255, 80, 0))
        if i > 0:
            strip.setPixelColor(i - 1, Color(0, 0, 0))
        strip.show()
        time.sleep(0.03)
    off()

    print("\nSimulating a jackpot flash (matches what the real game does)...")
    for _ in range(8):
        set_all(255, 64, 13)  # jackpot tier color
        time.sleep(0.1)
        off()
        time.sleep(0.1)

    print("\nTest complete - if every stage looked right, you're ready to wire this into the real game.")
finally:
    off()
    print("Strip turned off.")
