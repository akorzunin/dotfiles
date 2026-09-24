"""Bootstrap checks on a fresh HOME: python -m unittest tests/test_bootstrap.py."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTest(unittest.TestCase):
    def test_update_prepares_shell_init_before_linking_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hook = home / "Documents/hyprconf/_postinstall/yazi_file_picker.sh"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\nexit 0\n")
            env = dict(os.environ, HOME=str(home), XDG_CACHE_HOME=str(home / ".cache"))
            result = subprocess.run(["nu", "--no-config-file", "update.nu"], cwd=ROOT,
                                    env=env, text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((home / ".zoxide.nu").is_file())
            carapace = home / ".cache/nushell/carapace.nu"
            self.assertTrue(carapace.is_file())
            self.assertIn("carapace", carapace.read_text())
            self.assertTrue((home / ".config/nushell/config.nu").is_symlink())
            # Re-applying setup must not overwrite user-modified generated init.
            (home / ".zoxide.nu").write_text("# custom zoxide init\n")
            carapace.write_text("# custom carapace init\n")
            again = subprocess.run(["nu", "--no-config-file", "update.nu"], cwd=ROOT,
                                   env=env, text=True, capture_output=True, timeout=120)
            self.assertEqual(again.returncode, 0, again.stderr + again.stdout)
            self.assertEqual((home / ".zoxide.nu").read_text(), "# custom zoxide init\n")
            self.assertEqual(carapace.read_text(), "# custom carapace init\n")

    def test_install_entrypoint_runs_the_bootstrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            hook = home / "Documents/hyprconf/_postinstall/yazi_file_picker.sh"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\nexit 0\n")
            env = dict(os.environ, HOME=str(home), XDG_CACHE_HOME=str(home / ".cache"))
            result = subprocess.run(["sh", "install.sh"], cwd=ROOT, env=env,
                                    text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((home / ".zoxide.nu").is_file())

    def test_setup_explains_remote_name_and_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            rclone = bin_dir / "rclone"
            rclone.write_text('#!/bin/sh\nif [ "$1" = listremotes ]; then exit 0; fi\n'
                              'if [ "$1" = config ]; then exit 0; fi\nexit 2\n')
            rclone.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=f"{bin_dir}:{os.environ['PATH']}")
            result = subprocess.run(["nu", "--no-config-file", "dot_local/bin/dropbox-sync", "--setup"],
                                    cwd=ROOT, env=env, text=True, capture_output=True)
            self.assertIn("name> dropbox", result.stdout)
            self.assertIn("Storage> dropbox", result.stdout)
            self.assertIn("rclone authorize dropbox", result.stdout)
            self.assertIn("ssh -L 53682:localhost:53682", result.stdout)


if __name__ == "__main__":
    unittest.main()
