#!/usr/bin/env bash
# Requires 'sox'
sleep 3s # wait for BT speaker welcoming message to end
play -n synth pl G2 pl B2 pl D3 pl G3 pl D4 pl G4 delay 0 .05 .1 .15 .2 .25 remix - fade 0 4 .1 norm -1 1>/dev/null 2>/dev/null