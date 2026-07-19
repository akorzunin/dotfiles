#!/usr/bin/env bash
set -euo pipefail

if ! command -v pi >/dev/null 2>&1; then
  npm install -g --ignore-scripts @earendil-works/pi-coding-agent
fi

pi install npm:pi-subagents@0.32.0
pi install npm:pi-web-access@0.13.0
pi install npm:@juicesharp/rpiv-ask-user-question@1.20.0
pi install npm:@pi-unipi/notify@2.1.1
pi install npm:pi-intercom@0.6.0
pi install npm:pi-prompt-template-model@0.10.0
pi install npm:pi-codex-limit@1.8.2
pi install git:github.com/DietrichGebert/ponytail@14a0d79548d4de8fc2de95c1b94bb0de63a739d3

echo 'Pi setup restored. Run `pi` then `/login` on a new machine.'
