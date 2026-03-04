#!/usr/bin/env bash

PYTHON="python"
SCRIPT="homewatch.py"
ARGS=("runserver")

RESTART_CODE=42

# Wait until interface gets an IP
while true; do
    localip=$(ip -4 addr show | awk '/inet /{print $2}' | cut -d/ -f1 | grep -v 127.0.0.1 | head -n1)
    if [ -n "$localip" ]; then
        break
    fi
    echo "Not connected to network, retrying in 1s..."
    sleep 1
done

# Check for update
git --version 2>&1 >/dev/null
GIT_IS_AVAILABLE=$?
if [ $GIT_IS_AVAILABLE -eq 0 ]; then
    CURRENT_BRANCH=$(git branch --show-current)
    if [ "$CURRENT_BRANCH" == "main" ]; then
        git pull
    else
        git checkout main
        git pull
        git checkout $CURRENT_BRANCH
        git merge main
    fi    
fi

while true; do
    "$PYTHON" "$SCRIPT" "${ARGS[@]}"
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq "$RESTART_CODE" ]; then
        echo "Restarting..."
        sleep 2
    else
        break
    fi
done
