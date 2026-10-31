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
                            "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
                            "if os.environ.get('CAPTURE_IDENTITY'):\n"
                            "    import subprocess\n"
                            "    identity = next(a.split('=', 1)[1] for a in sys.argv if a.startswith('IdentityFile='))\n"
                            "    details = {'path': identity, 'public': Path(identity).read_text(),\n"
                            "               'socket': os.environ['SSH_AUTH_SOCK'],\n"
                            "               'agent_keys': subprocess.check_output(['ssh-add', '-L'], text=True)}\n"
                            "    Path(os.environ['CAPTURE_IDENTITY']).write_text(json.dumps(details))\n"
                            "sys.exit(int(os.environ.get('SSH_EXIT_CODE', '0')))\n")
            tool.chmod(0o700)
        clipboard = self.root / "wl-copy"
        clipboard.write_text("#!/usr/bin/env python3\nimport os, sys\n"
                             "from pathlib import Path\n"
                             "Path(os.environ['CAPTURE']).write_text(sys.stdin.read())\n")
        clipboard.chmod(0o700)
        self.inventory = self.root / "hosts"
        self.environment = {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                            "CAPTURE": str(self.capture)}

    def invoke(self, host, *options, expected_returncode=0):
        # Include an unrelated Vault tag; selecting a host must not decrypt others.
        block = "unrelated:\n  hosts:\n    old:\n      ansible_password: !vault |\n        ciphertext\nbootstrap_dyn1:\n  hosts:\n    dyn1:\n"
        for key, value in host.items():
            if key == 'ansible_private_key':
                block += '      ansible_private_key: !vault |\n' + ''.join('        ' + line + '\n' for line in value.splitlines())
            else:
                block += f'      {key}: {json.dumps(value)}\n'
        self.inventory.write_text(block)
        result = subprocess.run(["nu", "--no-config-file", str(SCRIPT), str(self.inventory),
                                 "--host", "dyn1", *options], env=self.environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected_returncode, result.stdout + result.stderr)
        self.last_result = result
        if hasattr(self, 'private_key'):
            self.assertNotIn(self.private_key, result.stdout + result.stderr)
            self.assertNotIn('BEGIN OPENSSH PRIVATE KEY', result.stdout + result.stderr)
        return self.capture.read_text() if self.capture.exists() else ''

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

    def vaulted_host(self):
        from ansible.parsing.vault import VaultLib, VaultSecret
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        self.private_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                             serialization.NoEncryption()).decode()
        self.public_key = key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                        serialization.PublicFormat.OpenSSH).decode()
        self.password_file = self.root / '.ansible_pass'
        self.password_file.write_text('SELECTOR_TEST_SECRET\n')
        self.details = self.root / 'identity.json'
        self.environment['CAPTURE_IDENTITY'] = str(self.details)
        vault = VaultLib([('default', VaultSecret(b'SELECTOR_TEST_SECRET'))])
        return {'ansible_user': 'admin', 'ansible_host': '192.0.2.1',
                'ansible_private_key': vault.encrypt(self.private_key).decode()}

    @unittest.skipUnless(shutil.which('ansible-inventory') and shutil.which('ssh-agent'), 'Ansible and ssh-agent are required')
    def test_vault_identity_is_used_without_plaintext_key_files_and_cleaned_up(self):
        host = self.vaulted_host()
        # Stale controller paths must not override the portable identity.
        host['ansible_ssh_private_key_file'] = '/missing/old-controller-key'
        args = json.loads(self.invoke(host))
        self.assertNotIn('/missing/old-controller-key', ' '.join(args))
        self.assertIn('IdentitiesOnly=yes', args)
        details = json.loads(self.details.read_text())
        self.assertTrue(details['public'].startswith(self.public_key))
        self.assertTrue(details['agent_keys'].startswith(self.public_key))
        self.assertFalse(Path(details['path']).exists())
        self.assertFalse(Path(details['socket']).exists())
        for path in self.root.iterdir():
            if path.is_file():
                self.assertNotIn(self.private_key.encode(), path.read_bytes())

    @unittest.skipUnless(shutil.which('ansible-inventory') and shutil.which('ssh-agent'), 'Ansible and ssh-agent are required')
    def test_vault_identity_cleanup_also_runs_when_ssh_fails(self):
        host = self.vaulted_host()
        self.environment['SSH_EXIT_CODE'] = '7'
        self.invoke(host, '--vault-password-file', str(self.password_file), expected_returncode=7)
        details = json.loads(self.details.read_text())
        self.assertFalse(Path(details['path']).exists())
        self.assertFalse(Path(details['socket']).exists())

    @unittest.skipUnless(shutil.which('ansible-inventory') and shutil.which('ssh-agent'), 'Ansible and ssh-agent are required')
    def test_copyid_uses_the_dedicated_public_key_and_temporary_agent(self):
        host = self.vaulted_host()
        args = json.loads(self.invoke(host, '--copyid'))
        details = json.loads(self.details.read_text())
        self.assertEqual(args[:2], ['-i', details['path']])
        self.assertTrue(details['public'].startswith(self.public_key))
        self.assertFalse(Path(details['path']).exists())
        self.assertFalse(Path(details['socket']).exists())

    @unittest.skipUnless(shutil.which('ansible-inventory'), 'Ansible is required')
    def test_wrong_vault_password_never_starts_ssh(self):
        host = self.vaulted_host()
        self.password_file.write_text('WRONG_SECRET\n')
        self.invoke(host, expected_returncode=1)
        self.assertFalse(self.capture.exists())
        self.assertFalse(self.details.exists())

    @unittest.skipUnless(shutil.which('ansible-inventory'), 'Ansible is required')
    def test_print_vault_command_reinvokes_selector_without_decrypting(self):
        host = self.vaulted_host()
        command = shlex.split(self.invoke(host, '--printcmd', '--vault-password-file', str(self.password_file)))
        self.assertEqual(command, ['ssh-sel.nu', str(self.inventory), '--host', 'dyn1',
                                   '--vault-password-file', str(self.password_file)])
        self.assertFalse(self.details.exists())

    def test_option_parsing_does_not_execute_shell_expressions(self):
        marker = self.root / "must-not-exist"
        host = {"ansible_user": "admin", "ansible_host": "192.0.2.1",
                "ansible_ssh_common_args": f'-o "ProxyCommand=$(touch {marker})"'}
        self.assertIn(f"ProxyCommand=$(touch {marker})", json.loads(self.invoke(host)))
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
