import RPi.GPIO as GPIO
import time

PIN = 18  # BCM numbering — change to match config.gpio_button

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Watching BCM GPIO {} — press the button (Ctrl+C to quit)".format(PIN))
last = None
try:
    while True:
        state = GPIO.input(PIN)
        if state != last:
            print("Pin is now", "HIGH (not pressed)" if state else "LOW (pressed!)")
            last = state
        time.sleep(0.05)
except KeyboardInterrupt:
    GPIO.cleanup()