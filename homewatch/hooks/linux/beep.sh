#!/usr/bin/env bash
# Requires 'sox'
sleep 3s
play -n synth sine G2 sine B2 sine D3 sine G3 sine D4 sine G4 delay 0 .05 .1 .15 .2 .25 remix - fade 1.6 2 0.4 vol -12dB 1>/dev/null 2>/dev/null