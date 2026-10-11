#!/bin/bash
# Starts the game on the Pi's screen. Point any boot-time autostart at this
# file. The LED strip only needs root (sudo) when it's on GPIO21; on GPIO10
# (SPI) the game runs as your normal user.
export DISPLAY=:0
cd "$(dirname "$0")"
LED_PIN=$(python3 -c "import config; print(getattr(config, 'led_pin', 21))" 2>/dev/null)
if [ "$LED_PIN" = "10" ]; then
    python3 main.py
else
    sudo python3 main.py
fi
