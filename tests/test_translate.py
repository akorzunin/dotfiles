"""Nushell translation UX and backend arguments, without contacting Google."""
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/translate"
NU = shutil.which("nu")


@unittest.skipUnless(NU, "Nushell is required")
class TranslateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.capture = root / "args.json"
        trans = root / "trans"
        trans.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
            "if '-list-all' in sys.argv:\n"
            "    print('en         English                        English\\n'\n"
            "          'ru         Russian                        Русский\\n'\n"
            "          'de         German                         Deutsch')\n"
            "else:\n"
            "    print(os.environ.get('TRANS_OUTPUT', 'translated'), end='')\n"
            "    print(os.environ.get('TRANS_ERROR', ''), file=sys.stderr)\n"
            "    sys.exit(int(os.environ.get('TRANS_EXIT', '0')))\n"
        )
        trans.chmod(0o700)
        self.env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "CAPTURE": str(self.capture), "TERM": "xterm-256color"}

    def invoke(self, *args, text=""):
        return subprocess.run([NU, "--no-config-file", str(SCRIPT), *args], input=text,
                              text=True, capture_output=True, env=self.env, timeout=10)

    def backend_args(self):
        return json.loads(self.capture.read_text())

    def test_automatic_direction(self):
        for text, target in [("Hello world", "ru"), ("Привет, мир", "en"),
                             ("ЁЖ", "en"), ("hello мир", "ru"), ("123", "ru")]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "translated\n")
                self.assertEqual(result.stderr, "")
                args = self.backend_args()
                self.assertEqual(args[args.index("-t") + 1], target)
                self.assertEqual(args[args.index("-s") + 1], "auto")
                self.assertEqual(args[args.index("-engine") + 1], "google")
                self.assertIn("-no-init", args)

    def test_full_dictionary_output_is_preserved(self):
        output = "cat\n/kat/\n\nкот\n(kot)\n\nDefinitions of cat\n[ English -> Русский ]\n\n    кошка\n        cat, grapnel\n"
        self.env["TRANS_OUTPUT"] = output
        result = self.invoke("cat")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, output)
        self.assertIn("-verbose", self.backend_args())
        self.assertNotIn("-brief", self.backend_args())

    def test_manual_languages_and_joined_words(self):
        result = self.invoke("--from", "en", "--to", "de", "hello", "world")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.backend_args()[-6:], ["-s", "en", "-t", "de", "--", "hello world"])

    def test_explicit_source_controls_automatic_target(self):
        result = self.invoke("--from", "ru", "mir")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.backend_args()
        self.assertEqual(args[args.index("-t") + 1], "en")

    def test_multiline_pipe_is_one_request(self):
        text = "hello\nworld\n"
        result = self.invoke(text=text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.backend_args()[-1], text)

    def test_literal_options_and_shell_metacharacters(self):
        text = "-help :ru $(touch /tmp/not-executed) 'quoted'"
        result = self.invoke("--", text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.backend_args()[-2:], ["--", text])

    def test_empty_input_and_bad_options(self):
        for args, text in [((), "  \n"), (("--to", "--help"), "hello"),
                           (("--to", "bad+code", "hello"), "")]:
            with self.subTest(args=args):
                result = self.invoke(*args, text=text)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.capture.exists())

    def test_backend_error_empty_response_warning_and_timeout(self):
        for output, error, status, expected in [
            ("", "network failed", "1", "network failed"),
            ("\n", "", "0", "no translation"),
            ("original text", "Unknown target language code", "0", "Unknown target"),
            ("", "", "124", "timed out"),
        ]:
            with self.subTest(status=status, error=error):
                self.env.update(TRANS_OUTPUT=output, TRANS_ERROR=error, TRANS_EXIT=status)
                result = self.invoke("hello")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn(expected, result.stderr)

    def test_help_works_without_trans(self):
        self.env["PATH"] = self.temp.name + "/missing"
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0)
        result = self.invoke("hello")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sudo pacman -S translate-shell", result.stderr)

    def terminal(self, command, steps):
        """Drive Nu's real Reedline/TUI, answering cursor-position queries."""
        master, slave = pty.openpty()
        process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=self.env)
        os.close(slave)
        output = b""
        pending = b""
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    output += data
                    pending += data
                    if b"\x1b[6n" in data:
                        os.write(master, b"\x1b[1;1R")
                    if steps and steps[0][0].encode() in pending:
                        marker, response = steps.pop(0)
                        pending = pending.split(marker.encode(), 1)[1]
                        os.write(master, response)
                if process.poll() is not None:
                    break
            self.assertFalse(steps, output.decode(errors="replace"))
            self.assertEqual(process.wait(timeout=2), 0, output.decode(errors="replace"))
            return output.decode(errors="replace")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def test_reedline_commands_and_error_recovery(self):
        output = self.terminal([NU, "--no-config-file", str(SCRIPT)], [
            ("[EN ↔ RU] > ", b"hello\r"),
            ("[EN ↔ RU] > ", b":to de\r"),
            ("[auto → de] > ", b":to invalid!\r"),
            ("[auto → de] > ", b"hallo\r"),
            ("[auto → de] > ", b":auto\r"),
            ("[EN ↔ RU] > ", b":q\r"),
        ])
        self.assertIn("translated", output)
        self.assertIn("Use a language code", output)
        self.assertEqual(self.backend_args()[-3:], ["de", "--", "hallo"])

    def test_ctrl_d_exits(self):
        self.terminal([NU, "--no-config-file", str(SCRIPT)], [("[EN ↔ RU] > ", b"\x04")])

    def test_fuzzy_language_picker(self):
        code = f"source {json.dumps(str(SCRIPT))}; translate-pick-language | print"
        output = self.terminal([NU, "--no-config-file", "-c", code], [
            ("Language", b"german\r"),
        ])
        self.assertTrue(output.rstrip().endswith("de"), output)


if __name__ == "__main__":
    unittest.main()
