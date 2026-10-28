"""Exercise the installed selector entry point with fake SSH, never a real server."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "dot_local/bin/ssh-sel.nu"


@unittest.skipUnless(shutil.which("nu"), "Nushell is required")
class SshSelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / "args.json"
        for name in ("ssh", "ssh-copy-id"):
            tool = self.root / name
            tool.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                            "from pathlib import Path\n"
                            "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n")
            tool.chmod(0o700)
        clipboard = self.root / "wl-copy"
        clipboard.write_text("#!/usr/bin/env python3\nimport os, sys\n"
                             "from pathlib import Path\n"
                             "Path(os.environ['CAPTURE']).write_text(sys.stdin.read())\n")
        clipboard.chmod(0o700)
        self.inventory = self.root / "hosts"
        self.environment = {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                            "CAPTURE": str(self.capture)}

    def invoke(self, host, *options):
        # JSON is also YAML; include a Vault tag to exercise the real inventory loader.
        self.inventory.write_text("unrelated:\n  hosts:\n    old:\n      ansible_password: !vault |\n        ciphertext\n"
                                  + "bootstrap_dyn1:\n  hosts:\n    dyn1: " + json.dumps(host) + "\n")
        result = subprocess.run(["nu", "--no-config-file", str(SCRIPT), str(self.inventory),
                                 "--host", "dyn1", *options], env=self.environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.capture.read_text()

    def test_legacy_inventory_and_default_port(self):
        host = {"ansible_user": "admin", "ansible_host": "192.0.2.1"}
        self.assertEqual(json.loads(self.invoke(host)), ["-p", "22", "admin@192.0.2.1"])
        host["ansible_port"] = 2222
        self.assertEqual(json.loads(self.invoke(host)), ["-p", "2222", "admin@192.0.2.1"])

    def test_dedicated_identity_pins_proxy_and_replacement(self):
        for address, key in [("192.0.2.1", "/old/admin"), ("192.0.2.2", "/new key/admin")]:
            with self.subTest(address=address):
                host = {"ansible_host": address, "ansible_user": "vpnadmin", "ansible_port": 22,
                        "ansible_ssh_private_key_file": key,
                        "ansible_ssh_common_args": "-o IdentitiesOnly=yes -o StrictHostKeyChecking=yes "
                        '-o \'UserKnownHostsFile="/private path/known_hosts"\' '
                        "-o 'ProxyCommand=nc -X connect -x 127.0.0.1:12334 %h %p'",
                        "ansible_ssh_extra_args": "-o BatchMode=yes"}
                args = json.loads(self.invoke(host))
                self.assertIn("IdentityFile=" + json.dumps(key), args)
                self.assertIn("StrictHostKeyChecking=yes", args)
                self.assertIn('UserKnownHostsFile="/private path/known_hosts"', args)
                self.assertIn("ProxyCommand=nc -X connect -x 127.0.0.1:12334 %h %p", args)
                self.assertIn("BatchMode=yes", args)
                self.assertEqual(args[-1], "vpnadmin@" + address)
                if shutil.which("ssh"):
                    config = subprocess.run([shutil.which("ssh"), "-F", "/dev/null", "-G", *args],
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(config.returncode, 0, config.stderr)
                    self.assertIn("identityfile " + key + "\n", config.stdout)
                    self.assertIn("userknownhostsfile /private path/known_hosts\n", config.stdout)
                self.assertEqual(shlex.split(self.invoke(host, "--printcmd")), ["ssh", *args])
                self.assertEqual(json.loads(self.invoke(host, "--copyid")), args)

    def test_option_parsing_does_not_execute_shell_expressions(self):
        marker = self.root / "must-not-exist"
        host = {"ansible_user": "admin", "ansible_host": "192.0.2.1",
                "ansible_ssh_common_args": f'-o "ProxyCommand=$(touch {marker})"'}
        self.assertIn(f"ProxyCommand=$(touch {marker})", json.loads(self.invoke(host)))
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
