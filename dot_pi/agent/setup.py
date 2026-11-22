#!/usr/bin/env python3
"""Prepare Pi without replacing machine-local credentials or model settings."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

# These old global registrations overlap the curated tools or have invalid host dependencies.
LEGACY_PACKAGES = {"@pi-unipi/unipi", "@pi-unipi/notify", "pi-subagents", "pi-intercom",
                   "omniroute-pi-ext-integration"}


def npm_name(source):
    if not source.startswith("npm:"):
        return None
    return source[4:].rsplit("@", 1)[0] if "@" in source[5:] else source[4:]


def reconcile_settings(agent, manifest):
    path = agent / "settings.json"
    settings = json.loads(path.read_text()) if path.exists() else {}
    sources = [source for source in manifest["always"] if source.startswith("npm:")]
    replaced = LEGACY_PACKAGES | {npm_name(source) for source in sources}
    packages = [entry for entry in settings.get("packages", [])
                if npm_name(entry if isinstance(entry, str) else entry["source"]) not in replaced]
    settings["packages"] = packages + sources
    if not path.exists() or json.loads(path.read_text()) != settings:
        if path.exists():
            # Keep the original registration list for recovery; never overwrite the first backup.
            backup = agent / "settings.json.before-dotfiles"
            if not backup.exists():
                shutil.copy2(path, backup)
        path.write_text(json.dumps(settings, indent=2) + "\n")


def run(args, env, **kwargs):
    subprocess.run(args, env=env, check=True, **kwargs)


def main():
    agent = (Path.home() / ".pi/agent").resolve()
    manifest = json.loads((agent / "extensions.json").read_text())
    env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent))
    node_bin = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "pi-node/current/bin"
    env["PATH"] = os.pathsep.join(map(str, [agent / "bin", Path.home() / ".local/bin", node_bin])) + os.pathsep + env.get("PATH", "")
    pi = shutil.which("pi", path=env["PATH"])
    if not pi:
        # Download first: a failed curl | sh pipeline can otherwise look successful.
        with tempfile.TemporaryDirectory(prefix="pi-install-") as temporary:
            installer = Path(temporary) / "install.sh"
            with urllib.request.urlopen("https://pi.dev/install.sh", timeout=60) as response:
                installer.write_bytes(response.read())
            result = subprocess.run(["sh", str(installer)], env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(result.stdout, end="")
            result.check_returncode()
        pi = shutil.which("pi", path=env["PATH"])
        if not pi:
            raise RuntimeError("Installer completed but pi was not found in ~/.pi/agent/bin or ~/.local/bin")
    npm = shutil.which("npm", path=env["PATH"])
    if not npm:
        raise RuntimeError("npm is required to install local Pi extension dependencies")
    for package in sorted((agent / "extensions").glob("*/package-lock.json")):
        # Do not install host-provided peers: Pi's loader supplies its own runtime modules.
        run([npm, "ci", "--omit=dev", "--legacy-peer-deps", "--no-audit", "--no-fund"],
            env, cwd=package.parent)
    reconcile_settings(agent, manifest)
    run([pi, "update", "--extensions"], env)
    sources = [source for group in manifest.values() for source in group if source.startswith("npm:")]
    args = [pi, "--no-extensions", "--no-skills", "--no-mcp", "--no-session"]
    for source in sources:
        args.extend(["-e", source])
    # --help loads extensions but starts no session or model request; it also warms -e caches.
    result = subprocess.run(args + ["--help"], env=env, text=True, capture_output=True)
    if result.returncode or "Failed to load extension" in result.stderr or "conflicts with" in result.stderr:
        raise RuntimeError(result.stderr or result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    print("Pi and pinned extensions are ready. OmniRoute remains opt-in via -e.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Pi setup failed: {error}")
