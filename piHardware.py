import os
import logging
import RPi.GPIO as GPIO
import config
import subprocess


def setup():
    os.environ['KIVY_AUDIO'] = 'sdl2'
    subprocess.call(['amixer', 'cset', "numid=1,iface=MIXER,name='PCM Playback Volume'", '100'])


class coinDispense:
    """
    No automated physical payout hardware is connected. This just logs what
    would have been dispensed, so payouts are still visible in the console
    for debugging, without needing any servo/PCA9685 hardware or I2C setup.
    """
    def __init__(self):
        pass

    def dispenseCoin(self, number):
        logging.info("payout: {} treats (no physical dispenser configured)".format(number))


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
