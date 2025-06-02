#!/bin/bash

set -e

export DISPLAY=:${DISPLAY_NUM}
./xvfb_startup.sh
./tint2_startup.sh
./mutter_startup.sh
./x11vnc_startup.sh

echo "Starting AI Service App on port 8081..."
# $HOME is /home/computeruse in the Docker image
# The script is in $HOME/computer_use_demo/computer_use_demo/ai_service_app.py
# Use `python` which should be from pyenv shims
python $HOME/computer_use_demo/computer_use_demo/ai_service_app.py >> /var/log/ai_service.log 2>&1 &
echo "AI Service App started in background."

# Keep the script running or start a primary foreground process if needed
# For example, if noVNC was the primary service, it might be started last and in foreground
# Or add a "sleep infinity" or "tail -f /dev/null" if all are background and script needs to keep container alive.
# Assuming one of the previous *_startup.sh scripts or a process started by them keeps the container alive.
# If not, the simplest way to keep it alive for now:
echo "Container startup complete. Services running in background."
tail -f /dev/null
