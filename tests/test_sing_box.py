"""Run with python -m unittest discover -s tests -p test_sing_box.py.

Uses real nu/sing-box validation, but mocks sudo: no system config is changed.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "dot_config/nushell/sing-box.nu"


class SingBoxTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        for directory in [".local/share", ".config/sing-box", "Dropbox/env", "bin"]:
            (self.home / directory).mkdir(parents=True)
        shared = ROOT / "dot_config/sing-box/config-all-proxy.json"
        (self.home / ".config/sing-box/config-all-proxy.json").write_bytes(shared.read_bytes())
        sudo = self.home / "bin/sudo"
        sudo.write_text('#!/bin/sh\nif [ "$1" = install ]; then\n cp "$9" "$HOME/installed.json"\nelse\n echo "$*" >> "$HOME/service-calls"\nfi\n')
        sudo.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{self.home / 'bin'}:{os.environ['PATH']}")
        self.profile(".local/share/config1.json")

    def profile(self, relative):
        (self.home / relative).write_text(json.dumps({"outbounds": [{
            "type": "socks", "tag": "test-vpn", "server": "127.0.0.1", "server_port": 9999
        }]}))

    def nu(self, command):
        return subprocess.run(["nu", "--no-config-file", "-c", f'use "{MODULE}" *; $env.SB_CONFIG_DIRS = [($env.HOME | path join ".local/share") ($env.HOME | path join "Dropbox/env")]; {command}'],
                              env=self.env, text=True, capture_output=True)

    def mock_probe(self, proxies, fail=False):
        curl = self.home / "bin/curl"
        curl.write_text(
            '#!/usr/bin/env python3\nimport json, sys\n'
            f'proxies = {proxies!r}\n'
            'if sys.argv[-1].endswith("/proxies"):\n'
            ' print(json.dumps({"proxies": proxies}))\n'
            'else:\n'
            ' assert sys.argv[-1].endswith("/test%20vpn/delay"), sys.argv\n'
            ' assert "--max-time" in sys.argv and "timeout=10000" in sys.argv\n'
            + (' sys.exit(22)\n' if fail else ' print(json.dumps({"delay": 123}))\n')
        )
        curl.chmod(0o755)

    def test_vpn_probe(self):
        proxies = {"proxy": {"type": "Selector", "now": "test vpn"}, "test vpn": {"type": "Socks5"}}
        self.mock_probe(proxies)
        result = self.nu('sb-test | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["latency_ms"], 123)
        result = self.nu('sb-test "test vpn" | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.mock_probe(proxies, fail=True)
        result = self.nu('sb-test')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VPN check failed", result.stderr)

    def test_probe_rejects_direct_and_unknown(self):
        self.mock_probe({"proxy": {"now": "bypass"}, "bypass": {"type": "Direct"}})
        result = self.nu('sb-test')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a VPN", result.stderr)
        result = self.nu('sb-test missing')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown outbound", result.stderr)

    def test_completions(self):
        result = self.nu('sb-actions | to json')
        self.assertIn("apply", json.loads(result.stdout))
        result = self.nu('sb-arguments "sb apply " | to json')
        self.assertEqual(json.loads(result.stdout)[0]["value"], "config1.json")
        self.profile("Dropbox/env/config1.json")
        result = self.nu('sb-arguments "sb apply " | to json')
        self.assertEqual({r["value"] for r in json.loads(result.stdout)}, {
            str(self.home / ".local/share/config1.json"),
            str(self.home / "Dropbox/env/config1.json"),
        })
        self.mock_probe({"proxy": {"all": ["test vpn", "direct"]}, "test vpn": {"type": "Socks5"}})
        result = self.nu('sb-arguments "sb use " | to json')
        self.assertEqual(json.loads(result.stdout), ["test vpn", "direct"])

    def test_apply_runs_probe(self):
        proxies = {"proxy": {"now": "test vpn"}, "test vpn": {"type": "Socks5"}}
        self.mock_probe(proxies)
        result = self.nu('sb-apply config1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HTTPS probe passed", result.stdout)
        self.mock_probe(proxies, fail=True)
        result = self.nu('sb-apply config1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VPN check failed", result.stderr)
        self.assertTrue((self.home / "installed.json").exists())

    def test_picker_empty_list(self):
        result = self.nu('$env.SB_CONFIG_DIRS = []; sb-apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No configs found", result.stderr)
        self.assertFalse((self.home / "installed.json").exists())

    def test_discovery(self):
        self.profile("Dropbox/env/config2.json")
        (self.home / ".local/share/unrelated.json").write_text('{}')
        (self.home / ".local/share/broken.json").write_text('{')
        result = self.nu("sb-configs | to json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({r["name"] for r in json.loads(result.stdout)}, {"config1.json", "config2.json"})

    def test_apply_stem(self):
        result = self.nu('install-sing-box-config config1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "installed.json").exists())

    def test_apply(self):
        result = self.nu('install-sing-box-config config1.json --restart')
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads((self.home / "installed.json").read_text())
        self.assertEqual([i["type"] for i in config["inbounds"]], ["mixed"])
        self.assertEqual(config["inbounds"][0]["listen_port"], 12334)
        self.assertIn("proxy", [o["tag"] for o in config["outbounds"]])
        self.assertIn("restart sing-box.service", (self.home / "service-calls").read_text())

    def test_ambiguous_and_invalid_do_not_install(self):
        self.profile("Dropbox/env/config1.json")
        result = self.nu('install-sing-box-config config1.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous", result.stderr)
        broken = self.home / ".local/share/invalid.json"
        broken.write_text('{"outbounds":[{"type":"unknown","tag":"bad"}]}')
        result = self.nu(f'install-sing-box-config "{broken}"')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "installed.json").exists())

    def test_override_and_missing_directory(self):
        result = self.nu('$env.SB_CONFIG_DIRS = ["/nonexistent"]; sb-configs | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
