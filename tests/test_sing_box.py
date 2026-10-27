"""Run with python -m unittest discover -s tests -p test_sing_box.py.

Uses real nu/sing-box validation, but mocks sudo: no system config is changed.
"""
import fcntl
import json
import os
import pty
from pathlib import Path
import select
import subprocess
import time
import tempfile
import termios
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "dot_config/nushell/sing-box.nu"
# Exercise the actual dispatcher without loading unrelated shell config.
DISPATCHER = 'def sb [' + (ROOT / 'dot_config/nushell/config.nu').read_text().split(
    'def sb [', 1)[1].split('\n}', 1)[0] + '\n}'


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

    def nu(self, command, prelude=""):
        return subprocess.run(["nu", "--no-config-file", "-c", f'{prelude}; use "{MODULE}" *; $env.SB_CONFIG_DIRS = [($env.HOME | path join ".local/share") ($env.HOME | path join "Dropbox/env")]; {command}'],
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
            ' assert sys.argv[sys.argv.index("--max-time") + 1] == "35" and "timeout=30000" in sys.argv\n'
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

    def test_all_probes_continue_after_failures(self):
        proxies = {
            'proxy': {'type': 'Selector', 'now': 'good vpn', 'all': ['good vpn', 'timeout']},
            'auto': {'type': 'URLTest', 'now': 'good vpn'},
            'bypass': {'type': 'Direct'},
            'reject': {'type': 'Reject'},
            'block': {'type': 'Block'},
            'dns': {'type': 'DNS'},
            'good vpn': {'type': 'Socks5'},
            'workstation-hop': {'type': 'SSH'},
            'ssh-via-workstation': {'type': 'SSH'},
            'cherry-ssh-via-workstation': {'type': 'SSH'},
            'timeout': {'type': 'VLESS'},
            'failed': {'type': 'Trojan'},
            'malformed': {'type': 'Shadowsocks'},
        }
        curl = self.home / 'bin/curl'
        curl.write_text(
            '#!/usr/bin/env python3\nimport json, os, sys\nfrom urllib.parse import unquote\n'
            f'proxies = {proxies!r}\n'
            'if sys.argv[-1].endswith("/proxies"):\n'
            ' print(json.dumps({"proxies": proxies}))\n'
            'else:\n'
            ' assert sys.argv[sys.argv.index("--max-time") + 1] == "35" and "timeout=30000" in sys.argv\n'
            ' assert "--request" not in sys.argv\n'
            ' tag = unquote(sys.argv[-1].split("/")[-2])\n'
            ' with open(os.path.join(os.environ["HOME"], "probe-calls"), "a") as log:\n'
            '  log.write(tag + "\\n")\n'
            ' if tag == "timeout": sys.exit(28)\n'
            ' if tag == "failed": sys.exit(22)\n'
            ' print("not json" if tag == "malformed" else json.dumps({"delay": 123}))\n'
        )
        curl.chmod(0o755)
        result = self.nu(f'{DISPATCHER}; sb test-all --json | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        expected = ['cherry-ssh-via-workstation', 'failed', 'good vpn', 'malformed', 'ssh-via-workstation', 'timeout']
        self.assertCountEqual([row['outbound'] for row in rows], expected)
        for row in rows:
            if row['outbound'] in ['good vpn', 'ssh-via-workstation', 'cherry-ssh-via-workstation']:
                self.assertEqual(row['status'], 'HTTPS probe passed')
                self.assertEqual(row['latency_ms'], 123)
            else:
                self.assertEqual(row['status'], 'failed or timed out')
                self.assertIsNone(row['latency_ms'])
        self.assertCountEqual((self.home / 'probe-calls').read_text().splitlines(), expected)

    def test_all_streams_before_slow_probe_finishes(self):
        curl = self.home / 'bin/curl'
        curl.write_text(
            '#!/usr/bin/env python3\nimport json, sys, time\n'
            'if sys.argv[-1].endswith("/proxies"):\n'
            ' print(json.dumps({"proxies": {"slow": {"type": "VLESS"}, "fast": {"type": "Trojan"}}}))\n'
            'else:\n'
            ' if "/slow/" in sys.argv[-1]: time.sleep(4)\n'
            ' print(json.dumps({"delay": 123}))\n'
        )
        curl.chmod(0o755)
        for suffix in ['| metadata set {|| merge {sb_test: true}} | sb-display', '--json | each {|row| print ($row | to json --raw)}']:
            with self.subTest(suffix=suffix):
                process = subprocess.Popen(
                    ['nu', '--no-config-file', '-c', f'use "{MODULE}" *; sb-test-all {suffix}'],
                    env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    start = time.monotonic()
                    ready, _, _ = select.select([process.stdout], [], [], 3)
                    self.assertTrue(ready, 'no result until all workers completed')
                    first = os.read(process.stdout.fileno(), 65536).decode()
                    self.assertTrue(first)
                    self.assertLess(time.monotonic() - start, 3)
                    self.assertIsNone(process.poll())
                    rest, stderr = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn('fast', first + rest)
                    self.assertIn('slow', rest)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_deep_dispatch_and_fixed_privileged_config_read(self):
        self.mock_probe({'proxy': {'now': 'test vpn'}, 'test vpn': {'type': 'Socks5'}})
        # Only the config reader runs under sudo; the helper's sing-box is unprivileged.
        sudo = self.home / 'bin/sudo'
        sudo.write_text('#!/usr/bin/env python3\nimport json, sys\n'
                        'assert sys.argv[1:4] == ["/usr/bin/python3", "-I", "-c"], sys.argv\n'
                        'assert "\\"/etc/sing-box/config.json\\"" in sys.argv[4]\n'
                        'print(json.dumps({"outbounds": []}))\n')
        fake = self.home / 'bin/sing-box'
        fake.write_text('#!/bin/sh\necho "intentional startup failure" >&2\nexit 1\n')
        fake.chmod(0o755)
        for command in ['test "test vpn"', 'test-all']:
            result = self.nu(f'{DISPATCHER}; sb {command} --mode full --attempts 2 --bytes 10 --threads 1 --json | to json')
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            row = data[0] if command == 'test-all' else data
            self.assertEqual(row['mode'], 'full')
            self.assertIn('intentional startup failure', row['error'])
            # No flag is needed to collect the full result, including nested failures.
            captured = self.nu(f'{DISPATCHER}; let result = (sb {command} --mode full); $result | to json')
            self.assertEqual(captured.returncode, 0, captured.stderr)
            self.assertEqual(json.loads(captured.stdout), data)
        for flags in ['--mode invalid', '--attempts 0', '--attempts -1', '--bytes -1', '--threads -1']:
            result = self.nu(f'{DISPATCHER}; sb test-all {flags}')
            self.assertNotEqual(result.returncode, 0, flags)

    def test_report_exposes_nested_measurements_and_errors(self):
        row = {
            'outbound': 'test vpn', 'mode': 'full', 'status': 'failed',
            'udp': {'status': 'degraded', 'received': 3, 'sent': 6, 'loss_percent': 50,
                    'rtt_spread_ms': 12, 'samples': [{'target': 'stun.example:3478', 'error': 'timed out'}] * 3},
            'stability': {'status': 'unstable', 'successes': 2, 'attempts': 20,
                          'min_latency_ms': 45, 'median_latency_ms': 84, 'max_latency_ms': 123,
                          'samples': [{'target': 'https://example.com', 'error': 'late timeout'}]},
            'bandwidth': {'download': {'status': 'passed', 'mbps': 12.4, 'bytes': 5000000},
                          'upload': {'status': 'failed', 'error': 'upload timeout'}},
        }
        literal = json.dumps(json.dumps(row))
        result = self.nu(f'{literal} | from json | metadata set {{|| merge {{sb_test: true}} }} | sb-display')
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ['FAIL', 'test vpn', '3/6 replies, 50% loss', 'RTT spread', '12 ms',
                     'timed out [3 failed samples]', '2/20 connections succeeded', 'late timeout',
                     'HTTPS min', '45 ms', 'HTTPS median', '84 ms', 'HTTPS max', '123 ms',
                     'Download', '12.4 Mbps', 'Upload', 'upload timeout']:
            self.assertIn(text, result.stdout)
        self.assertIn('│', result.stdout)
        self.assertNotIn('[FAIL]', result.stdout)
        self.assertNotIn('{record', result.stdout)
        # A projection keeps metadata but must still display without formatter errors.
        result = self.nu(f'{literal} | from json | metadata set {{|| merge {{sb_test: true}} }} | get status | sb-display')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('failed', result.stdout)

    def test_report_marks_timing_unavailable_when_all_connections_fail(self):
        row = {'outbound': 'test vpn', 'mode': 'stability', 'status': 'failed',
               'stability': {'status': 'failed', 'successes': 0, 'attempts': 3,
                             'min_latency_ms': None, 'median_latency_ms': None, 'max_latency_ms': None}}
        literal = json.dumps(json.dumps(row))
        result = self.nu(f'sb-format-result ({literal} | from json)')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('0/3 connections succeeded', result.stdout)
        self.assertIn('n/a (no successful requests)', result.stdout)
        self.assertNotIn('HTTPS median', result.stdout)

    def test_interactive_report_streams_and_ans_keeps_records(self):
        curl = self.home / 'bin/curl'
        curl.write_text(
            '#!/usr/bin/env python3\nimport json, sys, time\n'
            'if sys.argv[-1].endswith("/proxies"):\n'
            ' print(json.dumps({"proxies": {"slow": {"type": "VLESS"}, "fast": {"type": "Trojan"}}}))\n'
            'else:\n'
            ' if "/slow/" in sys.argv[-1]: time.sleep(4)\n'
            ' print(json.dumps({"delay": 123}))\n'
        )
        curl.chmod(0o755)
        master, slave = pty.openpty()
        termios.tcsetwinsize(slave, (24, 80))

        def session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        # Use the actual configured hook and dispatcher, without unrelated startup tools.
        config = (ROOT / 'dot_config/nushell/config.nu').read_text()
        hook = next(line for line in config.splitlines() if line.startswith('$env.config.hooks.display_output ='))
        setup = (f'use "{MODULE}" *; {DISPATCHER}; {hook}; '
                 '$env.config.show_banner = false; $env.config.max_last_result_size = 100mb; '
                 '$env.PROMPT_COMMAND = {|| "SB_READY> "}; $env.PROMPT_INDICATOR = ""')
        process = subprocess.Popen(['nu', '--no-config-file', '--no-history', '-e', setup],
                                   env=dict(self.env, TERM='dumb'), stdin=slave, stdout=slave, stderr=slave,
                                   preexec_fn=session)
        os.close(slave)

        def until(marker, timeout=5):
            output = b''
            deadline = time.monotonic() + timeout
            while marker not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    output += chunk
                    if b'\x1b[6n' in chunk:
                        os.write(master, b'\x1b[1;1R')
            self.assertIn(marker, output)
            return output

        try:
            until(b'SB_READY> ')
            os.write(master, b'sb test-all\r')
            first = until(b'123 ms', timeout=3)
            self.assertIn(b'fast', first)
            self.assertIn('│'.encode(), first)
            self.assertNotIn(b'slow', first)
            rest = until(b'slow')
            if b'SB_READY> ' not in rest:
                rest += until(b'SB_READY> ')
            self.assertEqual((first + rest).count(b'fast'), 1)
            self.assertEqual((first + rest).count(b'slow'), 1)
            os.write(master, b'$ans.last | to json --raw\r')
            saved = until(b'"latency_ms":123')
            self.assertIn(b'"outbound":"fast"', saved)
            self.assertIn(b'"outbound":"slow"', saved)
        finally:
            process.terminate()
            process.wait(timeout=5)
            os.close(master)

    def test_all_empty_and_api_unavailable(self):
        self.mock_probe({'proxy': {'type': 'Selector'}, 'bypass': {'type': 'Direct'}})
        result = self.nu('sb-test-all --json | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])
        curl = self.home / 'bin/curl'
        curl.write_text('#!/bin/sh\nexit 7\n')
        result = self.nu('sb-test-all')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot reach the sing-box API', result.stderr)

    def test_probe_rejects_direct_and_unknown(self):
        self.mock_probe({"proxy": {"now": "bypass"}, "bypass": {"type": "Direct"}})
        result = self.nu('sb-test')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a VPN", result.stderr)
        result = self.nu('sb-test missing')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown outbound", result.stderr)

    def test_active_protocol(self):
        self.mock_probe({
            'proxy': {'type': 'Selector', 'now': 'auto'},
            'auto': {'type': 'URLTest', 'now': 'vpn.vless'},
            'vpn.vless': {'type': 'VLESS'},
        })
        result = self.nu(f'{DISPATCHER}; sb active | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'chain': 'proxy → auto → vpn.vless',
            'outbound': 'vpn.vless', 'protocol': 'VLESS',
        })
        result = self.nu(f'{DISPATCHER}; sb active "vpn.vless" | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['chain'], 'vpn.vless')
        self.mock_probe({'proxy': {'now': 'bypass'}, 'bypass': {'type': 'Direct'}})
        result = self.nu('sb-active | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['protocol'], 'Direct')

    def test_active_errors(self):
        for proxies, error in [
            ({'proxy': {'now': 'auto'}, 'auto': {'now': 'proxy'}}, 'cycle detected'),
            ({'proxy': {'now': 'missing'}}, 'Unknown outbound: missing'),
        ]:
            with self.subTest(error=error):
                self.mock_probe(proxies)
                for command in ['sb-active', 'sb-test']:
                    result = self.nu(command)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)
        curl = self.home / 'bin/curl'
        curl.write_text('#!/bin/sh\nexit 7\n')
        result = self.nu('sb-active')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot reach the sing-box API', result.stderr)

    def test_current(self):
        systemctl = self.home / "bin/systemctl"
        systemctl.write_text('#!/bin/sh\necho inactive\nexit 3\n')
        systemctl.chmod(0o755)
        result = self.nu('sb-current | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["path"])
        result = self.nu('install-sing-box-config config1')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.nu('sb-current | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "name": "config1.json",
            "source": "file",
            "url": None,
            "auto_updates": "disabled",
            "path": str(self.home / ".local/share/config1.json"),
            "installed_path": "/etc/sing-box/config.json",
            "service": "inactive",
        })
        self.profile('.local/share/second.json')
        result = self.nu('install-sing-box-config second')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.nu('install-sing-box-config missing')
        self.assertNotEqual(result.returncode, 0)
        result = self.nu('sb-current | to json')
        self.assertEqual(json.loads(result.stdout)["name"], "second.json")

    def test_url_current_and_local_apply_disables_timer(self):
        state = self.home / '.local/state/sing-box/current.json'
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({'source': 'url', 'url': 'https://example.invalid/linux.json'}))
        systemctl = self.home / 'bin/systemctl'
        systemctl.write_text('#!/bin/sh\necho enabled\n')
        systemctl.chmod(0o755)
        result = self.nu('sb-current | to json')
        self.assertEqual(result.returncode, 0, result.stderr)
        current = json.loads(result.stdout)
        self.assertEqual(current['source'], 'url')
        self.assertEqual(current['url'], 'https://example.invalid/linux.json')
        self.assertIsNone(current['path'])
        self.assertIn('hourly', current['auto_updates'])
        result = self.nu('install-sing-box-config config1')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = (self.home / 'service-calls').read_text()
        self.assertIn('disable --now sing-box-update.timer', calls)
        self.assertIn('stop sing-box-update.service', calls)
        result = self.nu('sb-current | to json')
        self.assertEqual(json.loads(result.stdout)['source'], 'file')

    def test_url_setup(self):
        sudo = self.home / 'bin/sudo'
        sudo.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
home = pathlib.Path(os.environ['HOME'])
with (home / 'service-calls').open('a') as log:
    log.write(' '.join(sys.argv[1:]) + '\\n')
if 'setup' in sys.argv:
    url = json.load(sys.stdin)['url']
    print(json.dumps({'source': 'url', 'url': url, 'status': 'Updated'}))
''')
        sudo.chmod(0o755)
        state_dir = self.home / '.local/state/sing-box'
        state_dir.mkdir(parents=True)
        # Mirror the interactive config's mkdir wrapper; the module must bypass it.
        prelude = '''
def --env mkdir [...args: string] { error make {msg: "shell mkdir wrapper called"} }
def input [--suppress-output, prompt: string] {
    if not $suppress_output { error make {msg: "URL input must be hidden"} }
    $prompt | save --append ($env.HOME | path join input-calls)
    "https://example.invalid/linux.json"
}
'''
        result = self.nu(f'{DISPATCHER}; sb setup; sb setup', prelude=prelude)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / 'input-calls').read_text().count('Config URL: '), 2)
        self.assertNotIn('https://example.invalid', result.stdout)
        calls = (self.home / 'service-calls').read_text()
        self.assertIn('enable --now sing-box-update.timer', calls)
        self.assertIn('/usr/bin/python3 -I /usr/local/libexec/sing-box-subscription.py setup --json', calls)
        state = self.home / '.local/state/sing-box/current.json'
        self.assertEqual(json.loads(state.read_text())['source'], 'url')
        self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(state.parent.stat().st_mode & 0o777, 0o700)

        prelude = 'def input [--suppress-output, prompt: string] { error make {msg: "Unexpected URL prompt"} }'
        for argument in ['https://example.invalid/direct.json', '"  https://example.invalid/direct.json  "']:
            with self.subTest(argument=argument):
                result = self.nu(f'{DISPATCHER}; sb setup {argument}', prelude=prelude)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(state.read_text())['url'], 'https://example.invalid/direct.json')
                self.assertNotIn('https://example.invalid', result.stdout)
        self.assertNotIn('https://example.invalid', (self.home / 'service-calls').read_text())

    def test_setup_empty_input_cancels_without_sudo(self):
        for command in ['sb-setup', 'sb-setup ""', 'sb-setup "  "']:
            with self.subTest(command=command):
                result = self.nu(command, prelude='def input [--suppress-output, prompt: string] { "  " }')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Setup cancelled', result.stdout)
                self.assertFalse((self.home / 'service-calls').exists())
                self.assertFalse((self.home / '.local/state/sing-box/current.json').exists())

    def test_local_apply_bypasses_mkdir_wrapper(self):
        (self.home / '.local/state/sing-box').mkdir(parents=True)
        result = self.nu('install-sing-box-config config1; install-sing-box-config config1',
                         prelude='def --env mkdir [...args: string] { error make {msg: "shell mkdir wrapper called"} }')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / '.local/state/sing-box/current.json').exists())

    def test_completions(self):
        result = self.nu('sb-actions | to json')
        self.assertIn("apply", json.loads(result.stdout))
        self.assertIn("current", json.loads(result.stdout))
        self.assertIn("active", json.loads(result.stdout))
        self.assertIn("setup", json.loads(result.stdout))
        self.assertIn("pull", json.loads(result.stdout))
        self.assertIn("test-all", json.loads(result.stdout))
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
        result = self.nu('sb-arguments "sb active " | to json')
        self.assertEqual(json.loads(result.stdout), ["proxy", "test vpn"])

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
