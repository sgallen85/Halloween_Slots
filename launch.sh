#!/bin/bash
# Starts the game on the Pi's screen. Runs as root (sudo) because the LED
# strip library needs it. Point any boot-time autostart at this file.
export DISPLAY=:0
cd "$(dirname "$0")"
sudo python3 main.py
