#!/usr/bin/env bash

PYTHON="python"
SCRIPT="homewatch.py"
ARGS=("runserver")

RESTART_CODE=42

while true; do
    echo "Running Homewatch..."
    "$PYTHON" "$SCRIPT" "${ARGS[@]}"
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq "$RESTART_CODE" ]; then
        echo "Restarting..."
        sleep 2
    else
        break
    fi
done
