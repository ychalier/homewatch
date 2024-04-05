#!/bin/bash

# Get MAC address using the `bt-device -l` command from the bluez-tools package
devicemac=""

if [[ -z "$devicemac" ]]; then
    echo "Please provide a MAC address by editing hooks/linux/bluetooth.sh"
    exit 1
fi

# Find out which audio source to raise the volume of with `pacmd list-sinks`
sinkname="@DEFAULT_SINK@"

bluetoothctl power on
bluetoothctl connect "$devicemac"
pactl set-sink-volume "$sinkname" 100%