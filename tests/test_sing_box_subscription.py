"""Real sing-box validation with sandboxed files and mocked systemctl/downloads."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("subscription", ROOT / "dot_config/sing-box/subscription.py")
subscription = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subscription)
URL = "https://example.invalid/token/linux.json"


class SubscriptionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        self.state = directory / "state"
        self.config = directory / "etc/config.json"
        self.calls = []
        self.running = True
        self.fail_restart = False
        self.profile = {
            "log": {"level": "warn"},
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1", "listen_port": 12334}],
            "outbounds": [{"type": "socks", "tag": "vpn", "server": "127.0.0.1", "server_port": 9999}],
            "route": {"final": "vpn"},
        }
        for target, value in [("STATE", self.state), ("CONFIG", self.config), ("command", self.command)]:
            mock = patch.object(subscription, target, value)
            mock.start()
            self.addCleanup(mock.stop)
        ownership = patch.object(subscription.os, "fchown")
        ownership.start()
        self.addCleanup(ownership.stop)
        download = patch.object(subscription, "download", side_effect=lambda url: copy.deepcopy(self.profile))
        self.download = download.start()
        self.addCleanup(download.stop)

    def command(self, *args):
        self.calls.append(args)
        if args[0].endswith("sing-box"):
            return subprocess.run(args, capture_output=True, timeout=10)
        if "is-active" in args:
            return subprocess.CompletedProcess(args, 0 if self.running else 3)
        if "restart" in args:
            if self.fail_restart:
                self.fail_restart = False
                return subprocess.CompletedProcess(args, 1)
            self.running = True
        if "start" in args:
            self.running = True
        if "stop" in args:
            self.running = False
        return subprocess.CompletedProcess(args, 0)

    def test_setup_preserves_full_config_and_private_state(self):
        result = subscription.update(URL)
        self.assertTrue(result["changed"])
        self.assertEqual(json.loads(self.config.read_text()), self.profile)
        self.assertEqual(json.loads((self.state / "source.json").read_text()), {"source": "url", "url": URL})
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.state / "source.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.config.parent.glob(".subscription-*")), [])

    def test_manual_pull_reuses_url_and_unchanged_does_not_restart(self):
        subscription.update(URL)
        self.calls.clear()
        self.download.reset_mock()
        self.config.write_text(json.dumps(self.profile, sort_keys=True))
        result = subscription.update()
        self.download.assert_called_once_with(URL)
        self.assertFalse(result["changed"])
        self.assertFalse(any("restart" in call for call in self.calls))
        self.running = False
        subscription.update()
        self.assertTrue(self.running)

    def test_hourly_changed_config_and_backup(self):
        subscription.update(URL)
        old = self.config.read_bytes()
        self.profile["outbounds"][0]["server_port"] = 9998
        self.calls.clear()
        result = subscription.update(automatic=True)
        self.assertTrue(result["changed"])
        self.assertEqual(json.loads(self.config.read_text()), self.profile)
        self.assertEqual((self.state / "previous.json").read_bytes(), old)
        self.assertEqual((self.state / "previous.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(sum("restart" in call for call in self.calls), 1)

    def test_bad_download_and_invalid_config_keep_existing_config_and_url(self):
        subscription.update(URL)
        old = self.config.read_bytes()
        self.download.side_effect = ValueError("download failed")
        with self.assertRaises(ValueError):
            subscription.update("https://example.invalid/new.json")
        self.download.side_effect = None
        self.download.return_value = {"outbounds": [{"type": "invalid", "tag": "vpn"}]}
        with self.assertRaisesRegex(ValueError, "failed sing-box check"):
            subscription.update("https://example.invalid/new.json")
        self.assertEqual(self.config.read_bytes(), old)
        self.assertEqual(json.loads((self.state / "source.json").read_text())["url"], URL)

    def test_restart_failure_rolls_back(self):
        subscription.update(URL)
        old = self.config.read_bytes()
        self.profile["outbounds"][0]["server_port"] = 9998
        self.fail_restart = True
        with self.assertRaisesRegex(ValueError, "previous config restored"):
            subscription.update("https://example.invalid/new.json")
        self.assertEqual(self.config.read_bytes(), old)
        self.assertEqual(json.loads((self.state / "source.json").read_text())["url"], URL)
        self.assertTrue(self.running)

    def test_initial_restart_failure_removes_config_and_does_not_track_url(self):
        self.running = False
        self.fail_restart = True
        with self.assertRaisesRegex(ValueError, "previous config restored"):
            subscription.update(URL)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.state / "source.json").exists())
        self.assertFalse(self.running)

    def test_automatic_does_not_start_stopped_service(self):
        self.running = False
        result = subscription.update(automatic=True)
        self.assertFalse(result["changed"])
        self.download.assert_not_called()
        self.assertFalse(self.config.exists())

    def test_missing_url_and_insecure_url(self):
        with self.assertRaisesRegex(ValueError, "sb setup"):
            subscription.update()
        for url in ["http://example.invalid/config", "file:///etc/passwd", "https://user:password@example.invalid", "https://example.invalid/\n"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                subscription.update(url)
        self.download.assert_not_called()


class DownloadTest(unittest.TestCase):
    def download_body(self, body):
        with patch.object(subscription.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout=body)
            return subscription.download(URL)

    def test_json_download(self):
        body = {"outbounds": [{"type": "direct", "tag": "direct"}]}
        self.assertEqual(self.download_body(json.dumps(body).encode()), body)

    def test_bad_responses(self):
        for body in [b"<html>error</html>", b"[]", b"{}", b"\xff", b"a" * (subscription.MAX_BYTES + 1)]:
            with self.subTest(body=body[:20]), self.assertRaises(ValueError):
                self.download_body(body)

    def test_download_errors_do_not_leak_url(self):
        for failure in [OSError(URL), subprocess.TimeoutExpired(URL, 65)]:
            with patch.object(subscription.subprocess, "run", side_effect=failure):
                with self.assertRaises(ValueError) as error:
                    subscription.download(URL)
                self.assertNotIn(URL, str(error.exception))
        with patch.object(subscription.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 22, stdout=b"", stderr=URL.encode())
            with self.assertRaises(ValueError) as error:
                subscription.download(URL)
            self.assertNotIn(URL, str(error.exception))

    def test_https_only_bounded_transfer_and_secret_not_in_process_arguments(self):
        with patch.object(subscription.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout=b'{"outbounds":[{"type":"direct"}]}')
            subscription.download(URL)
            args = run.call_args.args[0]
            self.assertNotIn(URL, args)
            self.assertEqual(args[1], "--disable")
            self.assertEqual(args[args.index("--proto") + 1], "=https")
            self.assertEqual(args[args.index("--proto-redir") + 1], "=https")
            self.assertEqual(args[args.index("--max-time") + 1], "60")
            self.assertEqual(args[args.index("--noproxy") + 1], "*")
            self.assertEqual(run.call_args.kwargs['timeout'], 65)
            self.assertIn(URL, run.call_args.kwargs['input'].decode())


if __name__ == "__main__":
    unittest.main()
