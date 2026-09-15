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
    No automated physical payout hardware is connected. Payouts are tracked
    in the CSV game log instead (see GameLogger in main.py), so this is a
    no-op - candy is handed out manually.
    """
    def __init__(self):
        pass

    def dispenseCoin(self, number):
        pass


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
