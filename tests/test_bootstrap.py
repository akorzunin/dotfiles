"""Fresh-home and restricted-PATH checks: python -m unittest tests/test_bootstrap.py."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTest(unittest.TestCase):
    def server_env(self, home):
        """Expose only bootstrap tools, not the host's optional packages."""
        bin_dir = home / "bin"
        bin_dir.mkdir()
        for name, executable in (("nu", shutil.which("nu")),
                                 ("python", sys.executable), ("sh", shutil.which("sh")),
                                 ("dirname", shutil.which("dirname"))):
            (bin_dir / name).symlink_to(executable)
        env = dict(os.environ, HOME=str(home), PATH=str(bin_dir),
                   XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_CACHE_HOME=str(home / ".cache"),
                   XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_STATE_HOME=str(home / ".local/state"))
        for name in ("WAYLAND_DISPLAY", "DISPLAY", "NIRI_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE"):
            env.pop(name, None)
        return env

    def run_nu(self, env, *args):
        result = subprocess.run([str(Path(env["PATH"]) / "nu"), *args], cwd=ROOT,
                                env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, "", result.stderr)
        return result

    def start_shell(self, home, env, command):
        empty_env = home / "empty-env.nu"
        empty_env.write_text("")
        return self.run_nu(env, "--config", str(home / ".config/nushell/config.nu"),
                          "--env-config", str(empty_env), "-c", command)

    def install_optional_stubs(self, home):
        scripts = {
            "zoxide": '#!/bin/sh\nprintf \'%s\\n\' \'def --env audit-z [dir: directory = "~"] { cd $dir }\' \'alias z = audit-z\'\n',
            "carapace": '#!/bin/sh\nprintf \'%s\\n\' \'$env.AUDIT_CARAPACE = true\'\n',
            "oh-my-posh": "#!/bin/sh\nexit 0\n",
        }
        for name, content in scripts.items():
            script = home / "bin" / name
            script.write_text(content)
            script.chmod(0o755)

    def test_minimal_server_setup_and_shell_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            self.run_nu(env, "--no-config-file", "update.nu")
            self.assertTrue((home / ".config/nushell/config.nu").is_symlink())
            self.assertTrue((home / ".config/nushell/sing-box.nu").is_symlink())
            self.assertFalse((home / ".zoxide.nu").exists())
            self.assertFalse((home / ".cache/nushell/carapace.nu").exists())
            result = self.start_shell(home, env,
                                      'cd /; cd -; print $env.PWD; c; print "STARTUP_OK"')
            self.assertIn(str(ROOT), result.stdout)
            self.assertIn("Carapace is not installed", result.stdout)
            self.assertIn("STARTUP_OK", result.stdout)
            # Idempotent without installing packages or requiring Hyprconf.
            self.run_nu(env, "--no-config-file", "update.nu")

    def test_missing_python_installs_only_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            (home / "bin/python").unlink()
            sudo = home / "bin/sudo"
            sudo.write_text(f"#!{sys.executable}\nimport os, pathlib, sys\n"
                            "assert sys.argv[1:] == ['pacman', '-S', '--needed', 'python']\n"
                            "os.symlink(sys.executable, pathlib.Path(__file__).parent / 'python')\n")
            sudo.chmod(0o755)
            self.run_nu(env, "--no-config-file", "update.nu")
            self.start_shell(home, env, 'print "STARTUP_OK"')

    def test_headless_setup_skips_existing_desktop_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            hook = home / "Documents/hyprconf/_postinstall/yazi_file_picker.sh"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\necho 'Desktop hook must not run' >&2\nexit 1\n")
            yay = home / "bin/yay"
            yay.write_text("#!/bin/sh\nexit 1\n")
            yay.chmod(0o755)
            self.run_nu(env, "--no-config-file", "update.nu")

    def test_optional_init_is_generated_and_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            self.install_optional_stubs(home)
            self.run_nu(env, "--no-config-file", "update.nu")
            zoxide = home / ".zoxide.nu"
            carapace = home / ".cache/nushell/carapace.nu"
            self.assertTrue(zoxide.is_file())
            self.assertTrue(carapace.is_file())
            result = self.start_shell(home, env,
                                      'cd /; print $env.PWD; c; print $env.AUDIT_CARAPACE')
            self.assertIn("true", result.stdout)
            zoxide.write_text("# custom zoxide init\n")
            carapace.write_text("# custom carapace init\n")
            self.run_nu(env, "--no-config-file", "update.nu")
            self.assertEqual(zoxide.read_text(), "# custom zoxide init\n")
            self.assertEqual(carapace.read_text(), "# custom carapace init\n")

    def test_deleted_init_files_do_not_break_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            self.install_optional_stubs(home)
            self.run_nu(env, "--no-config-file", "update.nu")
            (home / ".zoxide.nu").unlink()
            (home / ".cache/nushell/carapace.nu").unlink()
            result = self.start_shell(home, env, 'cd /; c; print "STARTUP_OK"')
            self.assertIn("restart Nu", result.stdout)
            self.assertIn("STARTUP_OK", result.stdout)
            self.run_nu(env, "--no-config-file", "update.nu")
            result = self.start_shell(home, env, "c; print $env.AUDIT_CARAPACE")
            self.assertIn("true", result.stdout)

    def test_install_entrypoint_runs_the_bootstrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            result = subprocess.run([str(home / "bin/sh"), "install.sh"], cwd=ROOT,
                                    env=env, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((home / ".config/nushell/config.nu").is_symlink())
            self.start_shell(home, env, 'print "STARTUP_OK"')

    def test_setup_explains_remote_name_and_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            rclone = home / "bin/rclone"
            rclone.write_text('#!/bin/sh\nif [ "$1" = listremotes ]; then exit 0; fi\n'
                              'if [ "$1" = config ]; then exit 0; fi\nexit 2\n')
            rclone.chmod(0o755)
            result = subprocess.run([str(home / "bin/nu"), "--no-config-file",
                                     "dot_local/bin/dropbox-sync", "--setup"],
                                    cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
            self.assertIn("name> dropbox", result.stdout)
            self.assertIn("Storage> dropbox", result.stdout)
            self.assertIn("rclone authorize dropbox", result.stdout)
            self.assertIn("ssh -L 53682:localhost:53682", result.stdout)


if __name__ == "__main__":
    unittest.main()
