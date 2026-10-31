#!/usr/bin/env python3
"""Use a selected inventory's Vault key through a short-lived, isolated SSH agent."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def connect(inventory, host, password_file, ssh_options, copyid=False):
    command = ['ansible-inventory', '-i', str(inventory), '--host', host]
    if not password_file:
        candidate = Path(inventory).expanduser().absolute().parent / '.ansible_pass'
        if candidate.is_file():
            password_file = str(candidate)
    vault_options = ['--vault-password-file', str(Path(password_file).expanduser())] if password_file else []
    command += vault_options
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        # Never echo inventory stdout/stderr: either may contain decrypted credentials.
        raise RuntimeError('Cannot decrypt the selected host. Supply --vault-password-file or configure Ansible Vault credentials.')
    record = json.loads(result.stdout)
    private = record.get('ansible_private_key') or record.get('ansible_ssh_private_key')
    # New Ansible versions export Vault values as tagged JSON instead of decrypting.
    ciphertext = private.get('__ansible_vault') if isinstance(private, dict) else None
    if ciphertext:
        decrypted = subprocess.run(['ansible-vault', 'decrypt', '--output', '-', *vault_options],
                                   input=ciphertext, capture_output=True, text=True)
        if decrypted.returncode:
            raise RuntimeError('Cannot decrypt the selected identity. Check --vault-password-file or Ansible Vault configuration.')
        private = decrypted.stdout
    if not isinstance(private, str) or not private.startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
        raise RuntimeError('The selected host has no usable OpenSSH private key.')
    # Limit key lifetime even if the selector is killed before its cleanup runs.
    agent = subprocess.run(['ssh-agent', '-s', '-t', '3600'], capture_output=True, text=True, check=True)
    socket = re.search(r'SSH_AUTH_SOCK=([^;]+);', agent.stdout).group(1)
    pid = re.search(r'SSH_AGENT_PID=(\d+);', agent.stdout).group(1)
    environment = {**os.environ, 'SSH_AUTH_SOCK': socket, 'SSH_AGENT_PID': pid, 'TERM': 'xterm'}
    try:
        added = subprocess.run(['ssh-add', '-'], input=private, env=environment, capture_output=True, text=True)
        if added.returncode:
            raise RuntimeError('Cannot load the inventory identity into the temporary SSH agent.')
        public = subprocess.run(['ssh-add', '-L'], env=environment, capture_output=True, text=True, check=True).stdout
        with tempfile.TemporaryDirectory(prefix='ssh-sel-') as directory:
            # OpenSSH accepts a PUBLIC IdentityFile when the matching private key is in the agent.
            identity = Path(directory) / 'identity.pub'
            identity.write_text(public)
            identity.chmod(0o600)
            options = ['-o', f'IdentityFile={identity}', '-o', 'IdentitiesOnly=yes', *ssh_options]
            command = ['ssh-copy-id', '-i', str(identity), *options] if copyid else ['ssh', *options]
            return subprocess.call(command, env=environment)
    finally:
        subprocess.run(['ssh-agent', '-k'], env=environment, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--vault-password-file', default='')
    parser.add_argument('--copyid', action='store_true')
    parser.add_argument('ssh_options', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        return connect(args.inventory, args.host, args.vault_password_file,
                       args.ssh_options[1:], args.copyid)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Cannot use the inventory identity. Check --vault-password-file, ansible-inventory, ansible-vault, ssh-agent and ssh-add. No private key was written to disk.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
