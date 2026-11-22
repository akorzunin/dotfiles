# Pi setup and model presets

## Install and reproduce

Run from the dotfiles repository root:

```sh
nu --no-config-file update.nu
```

Setup always prepares Pi. It keeps an existing installation; if Pi is absent,
[`setup.py`](setup.py) downloads and runs the official `https://pi.dev/install.sh`
installer. Downloading before execution ensures a failed download cannot be
hidden by a successful `sh` exit. The official installer manages its own release
lockfile and optional Node.js installation; installing missing Node/npm may
require an interactive terminal. Fresh installs use the current Pi release, not
a repository-pinned core version. Upgrade the core explicitly with `pi update`.

The updater installs local extension dependencies with `npm ci --omit=dev
--legacy-peer-deps`, reconciles global packages, and warms all pinned `-e`
extension caches without sending a model request. It requires network access.
Pi's managed Node/npm path is included even before restarting your shell.

Existing `auth.json`, `models.json`, provider/model defaults and unrelated
settings/packages are preserved. The first migration saves
`settings.json.before-dotfiles`. It removes legacy global UniPi/notify packages
that duplicate tools, old pi-subagents/pi-intercom packages with invalid host
runtime dependencies, and global OmniRoute loading. Their files may remain
cached but are no longer registered. Local bash-scoring dependencies are now
installed, fixing its missing `@openrouter/sdk` error.

Your credentials and gateway configuration remain machine-local; setup does not
copy them between machines. Setup links the whole agent directory into the
checkout, so keep its ignored runtime files private.

## Startup and extension updates

[`extensions.json`](extensions.json) is the shared exact-version manifest for
setup and [`pi-mode`](../../dot_local/bin/pi-mode). `always` packages are also
registered for plain `pi`; `subagent` and `optional` packages are only loaded when
requested. `hpi`/`hpie`/`hpis` disable discovery and load their curated list, avoiding
unrelated global extensions and notification skills.

Temporary `-e npm:...` sources with version ranges trigger registry checks on
every launch. Exact versions load their cached copy without those checks, so
these modes do not need `--offline`. Normal model and web requests remain enabled.
To upgrade an extension, change its version in `extensions.json` and rerun
`update.nu`. `pi update --extensions` alone does not update temporary `-e` sources.

## OmniRoute or direct Codex

OmniRoute is opt-in, not a global provider override:

```nu
hpi -e npm:omniroute-pi-ext-integration --model cx/gpt-6.1-sol-high
```

The wrapper resolves that unversioned extension argument to the manifest's pin
(currently `2.0.1`). Explicit versions and arbitrary user extensions are passed
through unchanged. On a fresh machine, start `hpi -e
npm:omniroute-pi-ext-integration`, run `/omni setup` to enter the gateway URL/key,
then `/omni sync` to populate models before selecting one. The gateway must be
running and reachable separately; installing its Pi extension does not deploy it.

For direct Codex subscription access, omit the extension:

```nu
pi auth login openai-codex
hpi --provider openai-codex --model <your-codex-model-id>
```

No OmniRoute endpoint or key is required for this path, and setup does not change
an existing default provider or model.

## Modes

`hpie` (`pi-mode --explore`) is for general questions and web research. It keeps
web access, ask-user-question, notifications, and usage limits, but removes the
system prompt, built-in coding tools, MCP, skills, prompt templates, and project
context files. Sessions are ephemeral (`--no-session`): they cannot be resumed.
This does not disable provider-side retention or extension caches.
`--no-extensions` also disables the explore prompt override.

`pi-mode` uses automatic completion notifications with sound, without a
model-callable notification tool or notification skills. See
[`extensions/notify-auto/README.md`](extensions/notify-auto/README.md) for setup
and settings commands.

Configure Luna Max and Sol High as the two models cycled by `Ctrl+P`:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path.home() / ".pi/agent/settings.json"
path.parent.mkdir(parents=True, exist_ok=True)
settings = json.loads(path.read_text()) if path.exists() else {}
settings["enabledModels"] = [
    "openai-codex/gpt-5.6-luna:max",
    "openai-codex/gpt-5.6-sol:high",
]
path.write_text(json.dumps(settings, indent=2) + "\n")
PY
```
