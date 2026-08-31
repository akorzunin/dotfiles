# Pi model presets

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

