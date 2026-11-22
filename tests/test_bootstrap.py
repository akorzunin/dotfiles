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
        # Exercise updater integration without installing Pi or mutating shared repo caches.
        (bin_dir / "python").unlink()
        wrapper = (f"#!{sys.executable}\nimport os, sys\n"
                   "if sys.argv[1:2] == ['./dot_pi/agent/setup.py']: sys.exit(0)\n"
                   f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n")
        for name in ("python", "python-bootstrap"):
            (bin_dir / name).write_text(wrapper)
            (bin_dir / name).chmod(0o755)
        delta = bin_dir / "delta"
        delta.write_text("#!/bin/sh\nexit 0\n")
        delta.chmod(0o755)
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
            self.assertTrue((home / ".config/nushell/dropbox-sync-completions.nu").is_symlink())
            for relative in ("init.lua", "keymap.toml", "package.toml",
                             "plugins/picker-escape.yazi/main.lua"):
                self.assertEqual((home / ".config/yazi" / relative).resolve(),
                                 ROOT / "dot_config/yazi" / relative)
            self.assertFalse((home / ".zoxide.nu").exists())
            self.assertFalse((home / ".cache/nushell/carapace.nu").exists())
            result = self.start_shell(home, env,
                                      'cd /; cd -; print $env.PWD; c; print "STARTUP_OK"')
            self.assertIn(str(ROOT), result.stdout)
            self.assertIn("Carapace is not installed", result.stdout)
            self.assertIn("STARTUP_OK", result.stdout)
            # Idempotent without installing packages or requiring Hyprconf.
            self.run_nu(env, "--no-config-file", "update.nu")

    def test_desktop_sync_delegates_to_fresh_updater(self):
        for mode in ("success", "failure", "sync-failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                env = self.server_env(home)
                config_dir = home / ".config/nushell"
                config_dir.mkdir(parents=True)
                (config_dir / "config.nu").symlink_to(ROOT / "dot_config/nushell/config.nu")
                checkout = home / "Documents/dotfiles"
                checkout.mkdir(parents=True)
                (checkout / "update.nu").write_text(
                    'def main [--desktop] {\n'
                    '  if not $desktop { error make {msg: "missing desktop flag"} }\n'
                    + ('  error make {msg: "dependency failure"}\n' if mode == "failure"
                       else '  print "UPDATED"\n') + '}\n')
                git = home / "bin/git"
                git.write_text(f"#!{sys.executable}\nimport sys\n"
                               "if 'rev-parse' in sys.argv: print('main')\n"
                               "if '--porcelain=v2' in sys.argv: print('# branch.ab +0 -0')\n"
                               f"if 'pull' in sys.argv: sys.exit({1 if mode == 'sync-failure' else 0})\n")
                git.chmod(0o755)
                result = subprocess.run(
                    [str(home / "bin/nu"), "--no-config-file", "-c",
                     f'source "{config_dir / "config.nu"}"; desktop-sync -pu'],
                    cwd=ROOT, env=env, text=True, capture_output=True, timeout=30,
                )
                if mode in ("failure", "sync-failure"):
                    self.assertNotEqual(result.returncode, 0)
                    expected = "Failed to sync Neovim" if mode == "sync-failure" else "Dotfiles update failed"
                    self.assertIn(expected, result.stderr)
                    self.assertNotIn("UPDATED", result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertIn("UPDATED", result.stdout)

    def test_manifest_installs_missing_packages_and_stops_on_failure(self):
        for mode in ("common", "desktop", "installed", "failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                env = self.server_env(home)
                if mode != "installed":
                    (home / "bin/delta").unlink()
                marker = home / "installed"
                packages = ["git-delta"]
                if mode == "desktop":
                    packages.append("translate-shell")
                sudo = home / "bin/sudo"
                sudo.write_text(
                    f"#!{sys.executable}\nimport pathlib, sys\n"
                    f"assert sys.argv[1:] == {['pacman', '-S', '--needed', *packages]!r}\n"
                    f"pathlib.Path({str(marker)!r}).write_text('called')\n"
                    f"sys.exit({1 if mode == 'failure' else 0})\n")
                sudo.chmod(0o755)
                args = ["--desktop"] if mode == "desktop" else []
                result = subprocess.run(
                    [str(home / "bin/nu"), "--no-config-file", "update.nu", *args],
                    cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
                self.assertEqual(marker.exists(), mode != "installed", result.stderr + result.stdout)
                if mode == "failure":
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Dependency installation failed: git-delta", result.stderr)
                    self.assertFalse((home / ".config/nushell/config.nu").exists())
                else:
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertTrue((home / ".config/nushell/config.nu").is_symlink())

    def test_config_only_link_loads_repo_modules_before_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            config_dir = home / ".config/nushell"
            config_dir.mkdir(parents=True)
            (config_dir / "config.nu").symlink_to(ROOT / "dot_config/nushell/config.nu")
            # Simulate a pull introducing modules not yet linked by update.nu.
            result = self.start_shell(home, env,
                                      'help sb | ignore; help push-check | ignore; help dropbox-sync | ignore; print "STARTUP_OK"')
            self.assertIn("STARTUP_OK", result.stdout)
            self.assertFalse((config_dir / "push-check.nu").exists())
            self.assertFalse((config_dir / "sing-box.nu").exists())
            self.assertFalse((config_dir / "dropbox-sync-completions.nu").exists())

    def test_missing_python_installs_only_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            (home / "bin/python").unlink()
            sudo = home / "bin/sudo"
            sudo.write_text(f"#!{sys.executable}\nimport os, pathlib, sys\n"
                            "assert sys.argv[1:] == ['pacman', '-S', '--needed', 'python']\n"
                            "os.symlink(pathlib.Path(__file__).parent / 'python-bootstrap', pathlib.Path(__file__).parent / 'python')\n")
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

    def test_carapace_positional_input_is_migrated(self):
        legacy = ('let carapace_completer = {|spans| $spans }\n'
                  '$env.config.completions.external.completer = $carapace_completer\n')
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            self.install_optional_stubs(home)
            stub = home / "bin/carapace"
            stub.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.write({legacy!r})\n")
            self.run_nu(env, "--no-config-file", "update.nu")
            cache = home / ".cache/nushell/carapace.nu"
            migrated = cache.read_text()
            self.assertIn("{|place|", migrated)
            self.assertIn("let spans = $place.command", migrated)
            result = self.start_shell(
                home, env,
                'c; do $env.config.completions.external.completer '
                '{command: [git status]} | to json --raw')
            self.assertIn('["git","status"]', result.stdout)
            # An already-generated cache is patched even if Carapace is absent.
            stub.unlink()
            cache.write_text("# custom settings\n" + legacy)
            self.run_nu(env, "--no-config-file", "update.nu")
            self.assertEqual(cache.read_text(), "# custom settings\n" + migrated)
            self.run_nu(env, "--no-config-file", "update.nu")
            self.assertEqual(cache.read_text(), "# custom settings\n" + migrated)

    def test_yazi_plugin_installed_only_when_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = self.server_env(home)
            ya = home / "bin/ya"
            ya.write_text(f"#!{sys.executable}\nimport os, pathlib, sys\n"
                          "assert sys.argv[1:] == ['pkg', 'install']\n"
                          "config = pathlib.Path(os.environ['YAZI_CONFIG_HOME'])\n"
                          "assert (config / 'package.toml').is_symlink()\n"
                          "plugin = config / 'plugins/git.yazi/main.lua'\n"
                          "plugin.parent.mkdir(parents=True)\n"
                          "plugin.write_text('-- installed')\n")
            ya.chmod(0o755)
            self.run_nu(env, "--no-config-file", "update.nu")
            # The stub would fail on a second call because the directory exists.
            self.run_nu(env, "--no-config-file", "update.nu")
            self.assertTrue((home / ".config/yazi/plugins/git.yazi/main.lua").is_file())

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
            config_dir = home / ".config/nushell"
            config_dir.mkdir(parents=True)
            (config_dir / "env.nu").write_text('error make {msg: "broken env"}\n')
            (config_dir / "config.nu").symlink_to(home / "broken.nu")
            (home / "broken.nu").write_text('use nonexistent-module.nu *\n')
            # Bootstrap must run even when the current shell config cannot parse.
            result = subprocess.run([str(home / "bin/sh"), "install.sh"], cwd=ROOT,
                                    env=env, text=True, input="y\n", capture_output=True, timeout=30)
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
