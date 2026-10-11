#!/bin/bash
# Starts the game on the Pi's screen. Point any boot-time autostart at this
# file. Runs as root (sudo) because the LED strip library needs it. Uses
# full paths so a sudo rule naming this exact command can skip the
# password prompt (see README).
export DISPLAY=:0
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
sudo /usr/bin/python3 "$DIR/main.py"
