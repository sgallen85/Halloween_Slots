import time
import logging


def setup():
    pass


class coinDispense:
    """
    Used when piHardware fails to import (e.g. testing on a Mac with no
    RPi.GPIO). No automated physical payout hardware is connected either
    way, so this stays quiet - payouts are tracked in the CSV game log
    instead (see GameLogger in main.py).
    """
    def __init__(self):
        return

    def dispenseCoin(self, number):
        pass


class hardwareButton:
    """
    No physical button available in this environment - always reports not
    pressed. Use spacebar to trigger spins instead.
    """
    def __init__(self):
        return

    def checkButton(self):
        return False
