#!/usr/bin/env bash
set -euo pipefail

ensure_npm() {
  local name="$1" version="$2"
  local package="$HOME/.pi/agent/npm/node_modules/$name/package.json"
  if [[ ! -f "$package" || "$(node -p 'require(process.argv[1]).version' "$package" 2>/dev/null)" != "$version" ]]; then
    pi install "npm:$name@$version"
    npm install --save-exact --prefix "$HOME/.pi/agent/npm" "$name@$version" --legacy-peer-deps
  fi
}

ensure_git() {
  local source="$1" ref="$2" dir="$HOME/.pi/agent/git/github.com/DietrichGebert/ponytail"
  if [[ ! -d "$dir" || "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" != "$ref" ]]; then
    pi install "$source"
  fi
}

ensure_git git:github.com/DietrichGebert/ponytail@14a0d79548d4de8fc2de95c1b94bb0de63a739d3 14a0d79548d4de8fc2de95c1b94bb0de63a739d3
ensure_npm pi-web-access 0.18.0
ensure_npm @juicesharp/rpiv-ask-user-question 2.4.0
ensure_npm @pi-unipi/notify 2.2.1
ensure_npm pi-prompt-template-model 0.10.0
ensure_npm pi-codex-limit 1.8.2
# ensure_npm pi-subagents 0.40.0
# ensure_npm pi-intercom 0.9.2
# ensure_npm npm:pi-mono-figma

echo 'Pi setup restored. Run `pi` then `/login` on a new machine.'
