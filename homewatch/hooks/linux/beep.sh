#!/usr/bin/env bash
# Requires 'sox'
sleep 3s # wait for BT speaker welcoming message to end
sox -n -t wav - synth 0.15 sine 660 gain -8 fade q 0.03 0.15 0.03 | pw-play -