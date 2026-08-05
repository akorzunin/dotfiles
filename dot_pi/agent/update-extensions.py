#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

file = Path(__file__).with_name("install.sh")
text = file.read_text()
rx = re.compile(
    r"ensure_npm (?P<pkg>@[^/\s]+/[^\s@]+|[^@\s]+) (?P<ver>\d+\.\d+\.\d+)"
)

updates = []
for match in rx.finditer(text):
    package, current = match["pkg"], match["ver"]
    latest = subprocess.check_output(
        ["npm", "view", package, "version"], text=True
    ).strip()
    if current != latest:
        updates.append((package, current, latest))

if not updates:
    print("All pinned extensions are current.")
    raise SystemExit

for package, current, latest in updates:
    print(f"{package}: {current} -> {latest}")

if "--apply" not in sys.argv:
    print("\nReview these, then rerun with --apply.")
    raise SystemExit

for package, current, latest in updates:
    subprocess.run(["pi", "install", f"npm:{package}@{latest}"], check=True)
    subprocess.run(
        [
            "npm",
            "install",
            "--save-exact",
            "--prefix",
            str(Path.home() / ".pi/agent/npm"),
            f"{package}@{latest}",
            "--legacy-peer-deps",
        ],
        check=True,
    )
    text = text.replace(
        f"ensure_npm {package} {current}", f"ensure_npm {package} {latest}"
    )

file.write_text(text)
print(f"Updated {file}")
