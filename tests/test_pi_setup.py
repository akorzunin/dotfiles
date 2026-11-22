"""Pi bootstrap tests without network access or changes to the real agent directory."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pi_setup", ROOT / "dot_pi/agent/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class PiSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.agent = self.home / ".pi/agent"
        self.agent.mkdir(parents=True)
        self.manifest = json.loads((ROOT / "dot_pi/agent/extensions.json").read_text())
        (self.agent / "extensions.json").write_text(json.dumps(self.manifest))
        self.home_patch = patch.object(setup.Path, "home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def test_settings_migrate_conflicts_preserve_auth_and_models(self):
        settings = {"defaultProvider": "openai-codex", "defaultModel": "personal-model",
                    "enabledModels": ["openai-codex/*"], "packages": [
                        "npm:@pi-unipi/unipi", "npm:@pi-unipi/notify@2.1.1",
                        {"source": "npm:pi-subagents@0.32.0", "skills": []},
                        "npm:pi-intercom@0.6.0", "npm:pi-web-access@0.13.0",
                        "npm:omniroute-pi-ext-integration", "npm:personal-tool@1.0.0"]}
        path = self.agent / "settings.json"
        original = json.dumps(settings)
        path.write_text(original)
        for name in ("auth.json", "models.json"):
            (self.agent / name).write_text("machine-local")
        setup.reconcile_settings(self.agent, self.manifest)
        updated = json.loads(path.read_text())
        self.assertEqual(updated["defaultProvider"], "openai-codex")
        self.assertEqual(updated["defaultModel"], "personal-model")
        self.assertEqual(updated["enabledModels"], settings["enabledModels"])
        self.assertEqual(updated["packages"], ["npm:personal-tool@1.0.0"] + [
            x for x in self.manifest["always"] if x.startswith("npm:")])
        self.assertEqual((self.agent / "settings.json.before-dotfiles").read_text(), original)
        setup.reconcile_settings(self.agent, self.manifest)
        self.assertEqual(json.loads(path.read_text()), updated)
        self.assertEqual((self.agent / "settings.json.before-dotfiles").read_text(), original)
        for name in ("auth.json", "models.json"):
            self.assertEqual((self.agent / name).read_text(), "machine-local")

    def test_fresh_settings_do_not_force_a_provider(self):
        setup.reconcile_settings(self.agent, self.manifest)
        settings = json.loads((self.agent / "settings.json").read_text())
        self.assertEqual(set(settings), {"packages"})
        self.assertFalse(any("omni" in source for source in settings["packages"]))

    def test_existing_install_dependencies_and_prefetch(self):
        for name in ("bash-scoring", "notify-auto"):
            package = self.agent / "extensions" / name
            package.mkdir(parents=True)
            (package / "package-lock.json").write_text("{}")
        with patch.object(setup.shutil, "which", side_effect=["/bin/pi", "/bin/npm"]), \
             patch.object(setup, "run") as run, \
             patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as warm, \
             patch.object(setup.urllib.request, "urlopen") as download:
            setup.main()
        download.assert_not_called()
        for call in run.call_args_list[:2]:
            self.assertEqual(call.args[0], ["/bin/npm", "ci", "--omit=dev", "--legacy-peer-deps", "--no-audit", "--no-fund"])
        self.assertEqual(run.call_args_list[2].args[0], ["/bin/pi", "update", "--extensions"])
        args = warm.call_args.args[0]
        self.assertIn("npm:omniroute-pi-ext-integration@2.0.1", args)
        self.assertIn("--no-extensions", args)
        self.assertEqual(args[-1], "--help")
        self.assertEqual(warm.call_args.kwargs["env"]["PI_CODING_AGENT_DIR"], str(self.agent))

    def test_missing_pi_uses_downloaded_official_installer(self):
        success = subprocess.CompletedProcess([], 0, "installed\n", "")
        with patch.object(setup.shutil, "which", side_effect=[None, "/bin/pi", "/bin/npm"]), \
             patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(b"#!/bin/sh\n")) as download, \
             patch.object(setup, "run"), \
             patch.object(setup.subprocess, "run", side_effect=[success, success]) as run:
            setup.main()
        download.assert_called_once_with("https://pi.dev/install.sh", timeout=60)
        self.assertEqual(run.call_args_list[0].args[0][0], "sh")
        self.assertEqual(run.call_args_list[0].kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args_list[0].kwargs["stdout"], subprocess.PIPE)

    def test_download_failure_does_not_execute_partial_script(self):
        with patch.object(setup.shutil, "which", return_value=None), \
             patch.object(setup.urllib.request, "urlopen", side_effect=OSError("offline")), \
             patch.object(setup.subprocess, "run") as run:
            with self.assertRaisesRegex(OSError, "offline"):
                setup.main()
        run.assert_not_called()

    def test_extension_load_errors_fail_even_when_pi_exits_zero(self):
        with patch.object(setup.shutil, "which", side_effect=["/bin/pi", "/bin/npm"]), \
             patch.object(setup, "run"), \
             patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess(
                 [], 0, "help", "Error: Failed to load extension: missing dependency")):
            with self.assertRaisesRegex(RuntimeError, "Failed to load extension"):
                setup.main()


if __name__ == "__main__":
    unittest.main()
