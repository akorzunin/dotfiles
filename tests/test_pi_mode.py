"""Check mode arguments without starting Pi or contacting npm."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "dot_local/bin/pi-mode"


@unittest.skipUnless(shutil.which("nu"), "Nushell is required")
class PiModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.capture = root / "args.json"
        shutil.copy2(SCRIPT.parents[2] / "dot_pi/agent/extensions.json", root / "extensions.json")
        pi = root / "pi"
        pi.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                      "from pathlib import Path\n"
                      "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n")
        pi.chmod(0o700)
        self.environment = {
            **os.environ,
            "PATH": str(root) + os.pathsep + os.environ["PATH"],
            "CAPTURE": str(self.capture),
            "PI_CODING_AGENT_DIR": str(root),
            "PI_SUBAGENT_CHILD": "",
        }

    def invoke(self, *args):
        result = subprocess.run(
            ["nu", "--no-config-file", str(SCRIPT), *args],
            env=self.environment, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(self.capture.read_text())

    def test_npm_extensions_are_exactly_pinned_in_every_mode(self):
        for mode in ("--default", "--edit", "--explore", "--subagent"):
            with self.subTest(mode=mode):
                args = self.invoke(mode)
                sources = [args[i + 1] for i, arg in enumerate(args) if arg == "-e"]
                npm_sources = [source for source in sources if source.startswith("npm:")]
                self.assertEqual(len(npm_sources), 4 if mode == "--subagent" else 3)
                for source in npm_sources:
                    self.assertRegex(source, r"^npm:(?:@[^/]+/)?[^@]+@\d+\.\d+\.\d+$")
                self.assertNotIn("--offline", args)

    def test_omniroute_is_opt_in_and_pinned(self):
        self.assertFalse(any("omniroute" in arg for arg in self.invoke()))
        args = self.invoke("-e", "npm:omniroute-pi-ext-integration", "--model", "cx/gpt-6.1-sol-high")
        self.assertEqual(args[-4:], ["-e", "npm:omniroute-pi-ext-integration@2.0.1",
                                    "--model", "cx/gpt-6.1-sol-high"])
        self.assertNotIn("--provider", args)
        custom = self.invoke("-e", "npm:custom-extension@1.0.0")
        self.assertEqual(custom[-2:], ["-e", "npm:custom-extension@1.0.0"])

    def test_direct_codex_arguments_are_preserved(self):
        args = self.invoke("--provider", "openai-codex", "--model", "gpt-5.6-sol")
        self.assertEqual(args[-4:], ["--provider", "openai-codex", "--model", "gpt-5.6-sol"])
        self.assertFalse(any("omniroute" in arg for arg in args))

    def test_no_extensions_skips_explicit_extensions(self):
        for flag in ("--no-extensions", "-ne"):
            with self.subTest(flag=flag):
                args = self.invoke("--subagent", flag)
                self.assertNotIn("-e", args)
                self.assertIn(flag, args)

    def test_explore_restrictions_and_user_arguments_are_preserved(self):
        args = self.invoke("--explore", "--offline", "a question with spaces")
        for flag in ("--no-session", "--no-builtin-tools", "--no-context-files", "--no-mcp"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--system-prompt") + 1], "")
        self.assertEqual(args[-2:], ["--offline", "a question with spaces"])

    def test_subagent_child_does_not_load_subagent_extension(self):
        self.environment["PI_SUBAGENT_CHILD"] = "1"
        args = self.invoke("--subagent")
        self.assertFalse(any("pi-subagents-lite" in arg for arg in args))
        self.assertIn("--system-prompt", args)


if __name__ == "__main__":
    unittest.main()
