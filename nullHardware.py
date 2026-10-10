import time
import logging


def setup():
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

    def set_pattern(self, colors, offset=0):
        pass

    def set_pixels(self, colors):
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
