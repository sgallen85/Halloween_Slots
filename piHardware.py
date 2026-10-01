import os
import logging
import RPi.GPIO as GPIO
import config
import subprocess

try:
    from rpi_ws281x import PixelStrip, Color as WSColor
except ImportError:
    PixelStrip = None
    WSColor = None


def setup():
    # KIVY_AUDIO is set in main.py, before kivy.core.audio is imported -
    # setting it here was too late to have any effect.
    subprocess.call(['amixer', 'cset', "numid=1,iface=MIXER,name='PCM Playback Volume'", '100'])


class coinDispense:
    """
    No automated physical payout hardware is connected. Payouts are tracked
    in the CSV game log instead (see GameLogger in main.py), so this is a
    no-op - candy is handed out manually.
    """
    def __init__(self):
        pass

    def dispenseCoin(self, number):
        pass


class ledStrip:
    """
    Controls a WS2812B LED strip via rpi_ws281x. Defaults to GPIO19 (PWM
    channel 1) rather than GPIO18 - GPIO18 doubles as the Pi's onboard
    3.5mm audio PWM pin, and the two conflict (confirmed: booting with the
    strip on GPIO18 lit the first several LEDs solid white from the audio
    driver's own init, independent of any LED code).

    All methods here are instantaneous/non-blocking - any flashing or timed
    animation lives in main.py via Kivy's Clock, not here, so LED effects
    never freeze the game loop the way a time.sleep()-based effect would.

    Config overrides (all optional, in config.py):
      led_enabled     - set False to disable entirely without uninstalling anything
      led_count       - number of LEDs on the strip (default 60)
      led_pin         - GPIO pin number, BCM numbering (default 19)
      led_channel     - PWM channel matching the pin: 0 for GPIO18, 1 for GPIO19 (default 1)
      led_brightness  - 0-255 (default 128)
    """
    def __init__(self):
        self.strip = None

        if not getattr(config, 'led_enabled', True):
            logging.info('LED strip disabled via config.led_enabled = False')
            return

        if PixelStrip is None:
            logging.warning("rpi_ws281x not installed - LED strip disabled. "
                             "Install with: pip3 install rpi_ws281x --break-system-packages")
            return

        led_count = getattr(config, 'led_count', 60)
        led_pin = getattr(config, 'led_pin', 19)
        led_channel = getattr(config, 'led_channel', 1)
        led_brightness = getattr(config, 'led_brightness', 128)

        try:
            self.strip = PixelStrip(led_count, led_pin, 800000, 10, False,
                                     led_brightness, led_channel)
            self.strip.begin()
        except Exception as e:
            logging.warning('LED strip failed to initialize (often a permissions issue - '
                             'this needs to run as root): {}'.format(e))
            self.strip = None

    def set_all(self, r, g, b):
        if self.strip is None:
            return
        color = WSColor(r, g, b)
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
        self.strip.show()

    def set_pixel(self, i, r, g, b):
        if self.strip is None:
            return
        self.strip.setPixelColor(i, WSColor(r, g, b))
        self.strip.show()

    def off(self):
        self.set_all(0, 0, 0)


class hardwareButton:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.gpio_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.debounce = False

    def checkButton(self):
        input_state = GPIO.input(config.gpio_button)
        if self.debounce == True:
            if input_state == True:
                self.debounce = False
            return False
        if input_state == False:
            logging.warning('Button Pressed')
            self.debounce = True
            return True
        return False
