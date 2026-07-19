# Pi setup

From the dotfiles repo root:

```bash
./dot_local/bin/sync.py put .pi/agent
./dot_local/bin/sync.py put .unipi/config/notify
python3 - <<'PY'
import json
from pathlib import Path
config = Path.home() / ".unipi/config/notify/config.json"
data = json.loads(config.read_text())
data.setdefault("native", {})["soundPath"] = str(Path.home() / ".unipi/config/notify/complete.wav")
config.write_text(json.dumps(data, indent=2) + "\n")
PY
~/.pi/agent/install.sh
```

This syncs prompts/skills, the notify config, and `complete.wav`, then installs
packages. It intentionally does not copy `~/.pi/agent/auth.json`, sessions,
package caches, or runtime files.
