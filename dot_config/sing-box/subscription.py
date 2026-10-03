#!/usr/bin/env python3
"""Root-owned URL updater. Installed by `sb setup`; never run repo code as root on a timer."""
import argparse
import fcntl
import grp
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.parse

STATE = Path("/var/lib/sing-box-subscription")
CONFIG = Path("/etc/sing-box/config.json")
MAX_BYTES = 5 * 1024 * 1024


def validate_url(url):
    if not isinstance(url, str) or any(ord(c) < 32 for c in url):
        raise ValueError("A valid HTTPS config URL is required")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an HTTPS URL without embedded username/password")
    return url


def download(url):
    # Bypass app proxies so a broken VPN cannot prevent its own repair. Bound the
    # whole transfer, not just each socket read, to leave time for rollback.
    try:
        response = subprocess.run(
            ["/usr/bin/curl", "--disable", "--fail", "--silent", "--show-error",
             "--location", "--proto", "=https", "--proto-redir", "=https",
             "--noproxy", "*", "--connect-timeout", "15", "--max-time", "60",
             "--max-filesize", str(MAX_BYTES), "--config", "-"],
            input=("url = " + json.dumps(validate_url(url), ensure_ascii=False) + "\n").encode(),
            capture_output=True, timeout=65,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Config download failed; existing config was kept") from None
    if response.returncode:
        # Curl diagnostics may contain bearer tokens; never log them or the URL.
        raise ValueError("Config download failed; existing config was kept")
    body = response.stdout
    if len(body) > MAX_BYTES:
        raise ValueError("Downloaded config exceeds the 5 MiB limit")
    try:
        config = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValueError("URL did not return sing-box JSON") from None
    if not isinstance(config, dict) or not config.get("outbounds"):
        raise ValueError("URL must return a complete sing-box JSON config with outbounds")
    return config


def command(*args):
    return subprocess.run(args, capture_output=True, timeout=30)


def atomic_write(path, body, mode, group=0):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".subscription-")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
            os.fchmod(file.fileno(), mode)
            os.fchown(file.fileno(), 0, group)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def apply(config):
    body = (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode()
    # Validate a private staging file before touching the running config.
    with tempfile.TemporaryDirectory(dir=STATE) as directory:
        candidate = Path(directory) / "config.json"
        candidate.write_bytes(body)
        candidate.chmod(0o600)
        if command("/usr/bin/sing-box", "check", "-c", str(candidate)).returncode:
            raise ValueError("Downloaded config failed sing-box check; existing config was kept")
    old = CONFIG.read_bytes() if CONFIG.exists() else None
    if old is not None:
        try:
            if json.loads(old) == config:
                return False
        except ValueError:
            pass
    group = grp.getgrnam("sing-box").gr_gid
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    was_running = command("/usr/bin/systemctl", "is-active", "--quiet", "sing-box.service").returncode == 0
    if old is not None:
        atomic_write(STATE / "previous.json", old, 0o600)
    atomic_write(CONFIG, body, 0o640, group)
    try:
        if command("/usr/bin/systemctl", "restart", "sing-box.service").returncode:
            raise ValueError("sing-box restart failed")
        if command("/usr/bin/systemctl", "is-active", "--quiet", "sing-box.service").returncode:
            raise ValueError("sing-box did not stay active")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        if old is None:
            CONFIG.unlink(missing_ok=True)
            command("/usr/bin/systemctl", "stop", "sing-box.service")
        else:
            atomic_write(CONFIG, old, 0o640, group)
            if was_running:
                if command("/usr/bin/systemctl", "restart", "sing-box.service").returncode:
                    raise ValueError("Update failed; previous config restored but restart also failed") from None
            else:
                command("/usr/bin/systemctl", "stop", "sing-box.service")
        raise ValueError("Update failed; previous config restored") from None
    return True


def update(url=None, automatic=False):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    # One machine-wide subscription/lock; use per-instance state for sing-box@ services.
    with (STATE / "update.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        source = STATE / "source.json"
        if automatic and command("/usr/bin/systemctl", "is-active", "--quiet", "sing-box.service").returncode:
            return {"changed": False, "status": "Service stopped; automatic update skipped"}
        if url is None:
            if not source.exists():
                raise ValueError("No config URL configured; run sb setup first")
            url = json.loads(source.read_text())["url"]
        url = validate_url(url)
        changed = apply(download(url))
        # An unchanged manual pull should also be able to start a stopped service.
        if not automatic and not changed:
            if command("/usr/bin/systemctl", "start", "sing-box.service").returncode:
                raise ValueError("Config unchanged but sing-box failed to start")
        record = {"source": "url", "url": url}
        atomic_write(source, json.dumps(record).encode(), 0o600)
        return {**record, "changed": changed, "status": "Updated" if changed else "Config unchanged"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "pull"])
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run through sb setup / sb pull (root privileges required)")
    try:
        # Read setup secrets on stdin, not from the process command line.
        url = json.load(sys.stdin)["url"] if args.action == "setup" else None
        result = update(url, args.automatic)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
        # No tracebacks/exception URLs in the system journal.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, ValueError) else "Subscription update failed; inspect service/config permissions", file=sys.stderr)
        return 1
    print(json.dumps(result) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
