# Pi model presets

## Startup and extension updates

`pi-mode` pins its npm extensions to exact versions in
[`dot_local/bin/pi-mode`](../../dot_local/bin/pi-mode). Temporary `-e npm:...`
extensions with ranges such as `^1.2.3` trigger sequential npm registry checks on
every launch (up to 10 seconds each on Pi 1.5.0). Exact versions load the cached
copy without those checks, so `hpi`, `hpie`, and `hpis` do not need `--offline`.
Normal model and web requests remain enabled.

To upgrade an extension, change its pinned version in `pi-mode` and launch the
corresponding mode online once. Pi installs missing or mismatched versions;
subsequent launches use the cache. `pi update --extensions` does not update these
temporary `-e` sources.

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
