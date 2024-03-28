#!/bin/bash
# Get MAC address using the `bt-device -l` command from the bluez-tools package
bluetoothctl power on
bluetoothctl connect 00:0C:8A:F1:BD:0F
pactl set-sink-volume alsa_output.pci-0000_00_1f.3.analog-stereo 100%
pactl set-sink-volume bluez_sink.00_0C_8A_F1_BD_0F.a2dp_sink 100%