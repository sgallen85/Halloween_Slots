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


class ledStrip:
    """
    No LED hardware available in this environment (e.g. Mac testing) - all
    calls are no-ops. Matches piHardware.ledStrip's interface exactly so
    main.py never needs to know or care which one it's actually talking to.
    """
    def __init__(self):
        self.strip = None

    def set_all(self, r, g, b):
        pass

    def set_pixel(self, i, r, g, b):
        pass

    def off(self):
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
