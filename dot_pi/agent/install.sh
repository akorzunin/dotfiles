#!/usr/bin/env bash
set -euo pipefail

pi install npm:pi-subagents@0.40.0
pi install npm:pi-web-access@0.18.0
pi install npm:@juicesharp/rpiv-ask-user-question@2.4.0
pi install npm:@pi-unipi/notify@2.2.1
pi install npm:pi-intercom@0.9.2
pi install npm:pi-prompt-template-model@0.10.0
pi install npm:pi-codex-limit@1.8.2
pi install git:github.com/DietrichGebert/ponytail@14a0d79548d4de8fc2de95c1b94bb0de63a739d3

echo 'Pi setup restored. Run `pi` then `/login` on a new machine.'
