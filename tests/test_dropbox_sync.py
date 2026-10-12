"""Dropbox CLI checks with stubbed systemd/rclone; no real transfers or timers."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/dropbox-sync"


class DropboxSyncTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.nu = shutil.which("nu")
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        XDG_CONFIG_HOME=str(self.home / ".config"),
                        XDG_STATE_HOME=str(self.home / ".local/state"))
        self.state = self.home / ".local/state/rclone/bisync"
        self.state.mkdir(parents=True)
        (self.state / "initialized").touch()
        self.timer = dict(LoadState="loaded", ActiveState="active", UnitFileState="enabled")
        self.service = dict(LoadState="loaded", ActiveState="inactive", Result="success",
                            ExecMainStatus="0", ExecMainExitTimestamp="Mon 2026-03-23 12:00:00 UTC")
        self.stub("systemctl", f"""import json, os, pathlib, sys
args = sys.argv[1:]
with open(pathlib.Path(os.environ['HOME']) / 'systemctl-calls', 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args[1] == 'show':
    state = json.loads(os.environ['TIMER_STATE' if args[2].endswith('.timer') else 'SERVICE_STATE'])
    for key, value in state.items():
        print(key + '=' + value)
elif args[1] == 'list-timers':
    print('NEXT LEFT LAST PASSED UNIT ACTIVATES')
    print('12:00:30 20s 12:00:00 10s dropbox-sync.timer dropbox-sync.service')
""")

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n{body}")
        path.chmod(0o755)

    def run_cli(self, *args, success=True):
        self.env.update(TIMER_STATE=json.dumps(self.timer), SERVICE_STATE=json.dumps(self.service))
        result = subprocess.run([self.nu, "--no-config-file", str(SCRIPT), *args],
                                env=self.env, text=True, capture_output=True, timeout=10)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_check_shows_enabled_timer_and_success_without_rclone(self):
        result = self.run_cli("--check")
        for text in ("Initialized: true", "Autosync: ON", "Timer: active, enabled",
                     "Service: inactive", "Last result: success (exit 0)", "NEXT LEFT LAST",
                     "journalctl --user"):
            self.assertIn(text, result.stdout)
        calls = [json.loads(line) for line in (self.home / "systemctl-calls").read_text().splitlines()]
        self.assertEqual([call[1] for call in calls], ["show", "show", "list-timers"])

    def test_no_arguments_and_short_check_show_status(self):
        for args in ((), ("-c",)):
            with self.subTest(args=args):
                self.assertIn("Autosync: ON", self.run_cli(*args).stdout)

    def test_not_scheduled_without_initialization(self):
        (self.state / "initialized").unlink()
        self.timer.update(LoadState="not-found", ActiveState="inactive", UnitFileState="")
        result = self.run_cli("--check")
        self.assertIn("Initialized: false", result.stdout)
        self.assertIn("Autosync: not scheduled", result.stdout)
        self.assertIn("--schedule 30s", result.stdout)

    def test_disabled_timer(self):
        self.timer.update(ActiveState="inactive", UnitFileState="disabled")
        result = self.run_cli("--check")
        self.assertIn("Autosync: OFF", result.stdout)
        self.assertIn("Timer: inactive, disabled", result.stdout)

    def test_active_timer_does_not_hide_failed_transfer(self):
        self.service.update(ActiveState="failed", Result="exit-code", ExecMainStatus="1")
        result = self.run_cli("--check")
        self.assertIn("Autosync: ON", result.stdout)
        self.assertIn("Last result: exit-code (exit 1)", result.stdout)

    def test_currently_running(self):
        self.service.update(ActiveState="activating", ExecMainExitTimestamp="")
        result = self.run_cli("--check")
        self.assertIn("Sync: running", result.stdout)
        self.assertNotIn("Last result:", result.stdout)

    def test_never_run(self):
        self.service.update(ExecMainExitTimestamp="")
        self.assertIn("Last sync: not run yet", self.run_cli("--check").stdout)

    def test_warns_if_active_timer_not_enabled(self):
        self.timer.update(UnitFileState="disabled")
        self.assertIn("not enabled for future", self.run_cli("--check").stdout)

    def test_unavailable_user_manager(self):
        self.stub("systemctl", "import sys\nprint('Failed to connect to user bus', file=sys.stderr)\nsys.exit(1)\n")
        self.assertIn("Failed to connect to user bus", self.run_cli("--check", success=False).stderr)

    def test_mount_options_removed_from_cli(self):
        help_text = self.run_cli("--help").stdout
        for option in ("--unmount", "--force", "--tray"):
            with self.subTest(option=option):
                self.assertNotIn(option, help_text)
                self.run_cli(option, success=False)

    def test_invalid_option_combinations(self):
        for args in (("--setup", "--init"), ("--check", "--sync"), ("--check", "--dry-run")):
            with self.subTest(args=args):
                self.run_cli(*args, success=False)

    def complete(self, line):
        module = ROOT / "dot_config/nushell/dropbox-sync-completions.nu"
        content = f'use "{module}" *\n{line}'
        script = self.home / "completion-test.nu"
        script.write_text(content)
        result = subprocess.run([self.nu, "--no-config-file", "--ide-complete",
                                 str(len(content.encode())), str(script)],
                                env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)["completions"]

    def test_flag_completions_match_cli(self):
        flags = re.findall(r"^\s+(?:-\w, )?--([\w-]+)", self.run_cli("--help").stdout, re.MULTILINE)
        self.assertEqual(set(self.complete("dropbox-sync --")), {"--" + flag for flag in flags})
        self.assertEqual(self.complete("dropbox-sync --sch"), ["--schedule"])

    def test_schedule_interval_completions(self):
        self.assertEqual(set(self.complete("dropbox-sync --schedule ")), {"30s", "1min", "5min", "1h"})

    def test_completion_signature_keeps_external_execution(self):
        self.stub("dropbox-sync", "import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
        module = ROOT / "dot_config/nushell/dropbox-sync-completions.nu"
        for args in ("--schedule 42min", "--sync --init --dry-run", "-c"):
            with self.subTest(args=args):
                result = subprocess.run([self.nu, "--no-config-file", "-c",
                                         f'use "{module}" *; dropbox-sync {args}'],
                                        env=self.env, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                # Known externals normalize short flags to their long form.
                expected = ["--check"] if args == "-c" else args.split()
                self.assertEqual(json.loads(result.stdout), expected)

    def test_sync_uses_existing_state_paths(self):
        self.stub("mountpoint", "import sys\nsys.exit(1)\n")
        self.stub("rclone", "import sys\nassert sys.argv[1:] == ['listremotes', '--type', 'dropbox']\nprint('dropbox:')\n")
        self.stub("flock", "import json, os, pathlib, sys\n(pathlib.Path(os.environ['HOME']) / 'transfer-args').write_text(json.dumps(sys.argv[1:]))\n")
        self.run_cli("--sync")
        args = json.loads((self.home / "transfer-args").read_text())
        self.assertEqual(args[:4], ["--nonblock", str(self.state / "transfer.lock"), "rclone", "bisync"])
        self.assertEqual(args[args.index("--workdir") + 1], str(self.state))
        self.assertNotIn("--resync", args)


if __name__ == "__main__":
    unittest.main()
