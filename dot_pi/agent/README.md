# Pi model presets

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
