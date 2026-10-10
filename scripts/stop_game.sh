#!/bin/bash
# Force-quits the game - e.g. over SSH if the screen is frozen.
sudo pkill -9 -f "python3 main.py"
