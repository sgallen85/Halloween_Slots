#!/usr/bin/env python3
"""
Standalone LED strip test - checks wiring/library BEFORE trusting it wired
into the full game. Needs sudo, same as the real game will once LEDs are
enabled, since rpi_ws281x needs raw access to the PWM/DMA hardware:

    sudo python3 led_test.py

Reads the same led_count / led_pin / led_channel / led_brightness settings
from config.py that the real game uses, so a successful run here means the
same settings will work once wired into main.py.
"""
import time
import config

try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:
    print("rpi_ws281x not installed. Run:")
    print("  pip3 install rpi_ws281x --break-system-packages")
    raise SystemExit(1)

LED_COUNT = getattr(config, 'led_count', 60)
LED_PIN = getattr(config, 'led_pin', 19)
LED_CHANNEL = getattr(config, 'led_channel', 1)
LED_BRIGHTNESS = getattr(config, 'led_brightness', 128)

print("LED strip test - {} pixels on GPIO{}, channel {}, brightness {}".format(
    LED_COUNT, LED_PIN, LED_CHANNEL, LED_BRIGHTNESS))

strip = PixelStrip(LED_COUNT, LED_PIN, 800000, 10, False, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()


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
