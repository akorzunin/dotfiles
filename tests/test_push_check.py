"""Run with python -m unittest discover -s tests -p test_push_check.py.

Uses temporary local Git remotes; never accesses the network or user repositories.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "dot_config/nushell/push-check.nu"


class PushCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.documents = self.home / "Documents"
        self.documents.mkdir()
        self.remote = self.home / "remote.git"
        self.repo = self.documents / "repo with spaces"
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", COLUMNS="32")
        self.git(self.home, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.home, "clone", str(self.remote), str(self.repo))
        self.commit(self.repo, "initial")
        self.git(self.repo, "push", "-u", "origin", "main")

    def git(self, repo, *args):
        result = subprocess.run(["git", "-C", str(repo), *args], env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, repo, text):
        (repo / "file").write_text(text)
        self.git(repo, "add", "file")
        self.git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-m", text)

    def scan(self, fetch=False, root=None, color=None):
        # JSON quoting also handles spaces in paths passed to Nushell.
        config = "" if color is None else f'$env.config.use_ansi_coloring = {str(color).lower()}; '
        command = f'use {json.dumps(str(MODULE))}; {config}push-check {json.dumps(str(root or self.documents))}'
        if fetch:
            command += " --fetch"
        result = subprocess.run(["nu", "--no-config-file", "-c", command],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_clean_repository_is_omitted(self):
        self.assertEqual(self.scan(), ["✓  1 repos"])

    def test_ahead_and_uncommitted_without_pushing(self):
        remote_head = self.git(self.remote, "rev-parse", "main")
        self.commit(self.repo, "unpushed")
        (self.repo / "untracked").write_text("not committed")
        before = self.git(self.repo, "status", "--porcelain")
        self.assertEqual(self.scan(), ["repo with spaces  main  ↑1 ±1"])
        self.assertEqual(self.git(self.remote, "rev-parse", "main"), remote_head)
        self.assertEqual(self.git(self.repo, "status", "--porcelain"), before)

    def test_only_repo_name_is_colored_when_enabled(self):
        self.commit(self.repo, "unpushed")
        self.assertEqual(self.scan(color=True), ["\x1b[1;36mrepo with spaces\x1b[0m  main  ↑1"])

    def test_color_can_be_disabled(self):
        self.commit(self.repo, "unpushed")
        self.assertEqual(self.scan(color=False), ["repo with spaces  main  ↑1"])

    def test_non_current_branch_is_ignored(self):
        self.git(self.repo, "switch", "-c", "feature")
        self.git(self.repo, "push", "-u", "origin", "feature")
        self.commit(self.repo, "feature change")
        self.git(self.repo, "switch", "main")
        self.assertEqual(self.scan(), ["✓  1 repos"])

    def test_tag_named_like_branch_does_not_hide_changes(self):
        self.git(self.repo, "tag", "main")
        self.commit(self.repo, "unpushed")
        (self.repo / "untracked").write_text("change")
        self.assertEqual(self.scan(), ["repo with spaces  main  ↑1 ±1"])

    def test_missing_upstream(self):
        self.git(self.repo, "switch", "-c", "unpublished")
        self.assertEqual(self.scan(), ["repo with spaces  unpublished  ?upstream"])

    def test_deleted_tracking_ref(self):
        self.git(self.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self.scan(), ["repo with spaces  main  !upstream"])

    def advance_remote(self):
        other = self.home / "other"
        self.git(self.home, "clone", str(self.remote), str(other))
        self.commit(other, "remote change")
        self.git(other, "push")

    def test_fetch_is_opt_in_and_reports_behind(self):
        self.advance_remote()
        self.assertEqual(self.scan(), ["✓  1 repos"])
        self.assertEqual(self.scan(fetch=True), ["repo with spaces  main  ↓1"])

    def test_diverged_shows_both_arrows(self):
        self.advance_remote()
        self.commit(self.repo, "local change")
        self.assertEqual(self.scan(fetch=True), ["repo with spaces  main  ↑1 ↓1"])

    def test_fetch_failure_is_visible_even_when_cached_state_is_clean(self):
        self.git(self.repo, "remote", "set-url", "origin", str(self.home / "missing.git"))
        self.assertEqual(self.scan(fetch=True), ["repo with spaces  main  !fetch"])

    def test_nested_worktree_is_ignored(self):
        worktree = self.documents / "nested" / "worktree"
        worktree.parent.mkdir()
        self.git(self.repo, "worktree", "add", "-b", "work", str(worktree))
        (worktree / "untracked").write_text("change")
        self.assertEqual(self.scan(), ["✓  1 repos"])

    def test_immediate_worktree_is_checked(self):
        worktree = self.documents / "worktree"
        self.git(self.repo, "worktree", "add", "-b", "work", str(worktree))
        (worktree / "untracked").write_text("change")
        self.assertEqual(self.scan(), ["worktree  work  ?upstream ±1"])

    def test_explicit_repo_root_is_checked_without_recursing(self):
        nested = self.repo / "nested"
        self.git(self.home, "init", str(nested))
        self.assertEqual(self.scan(root=self.repo), ["repo with spaces  main  ±1"])

    def test_detached_head_is_omitted(self):
        self.git(self.repo, "switch", "--detach")
        self.assertEqual(self.scan(), ["✓  1 repos"])

    def test_dirty_detached_head_is_also_omitted(self):
        self.git(self.repo, "switch", "--detach")
        (self.repo / "untracked").write_text("change")
        self.assertEqual(self.scan(), ["✓  1 repos"])

    def test_empty_repository(self):
        empty = self.documents / "empty"
        self.git(self.home, "init", "--initial-branch=main", str(empty))
        self.assertEqual(self.scan(), ["empty  main  no commits yet"])

    def test_empty_directory(self):
        empty = self.home / "empty"
        empty.mkdir()
        self.assertEqual(self.scan(root=empty), ["✓  0 repos"])

    def test_invalid_repository_does_not_abort_scan(self):
        broken = self.documents / "broken"
        broken.mkdir()
        (broken / ".git").write_text("invalid git file")
        self.commit(self.repo, "unpushed")
        self.assertEqual(self.scan(), ["broken  !git", "repo with spaces  main  ↑1"])

    def test_nested_checkout_is_ignored(self):
        dependency = self.documents / "node_modules" / "dependency"
        dependency.mkdir(parents=True)
        self.git(self.home, "init", str(dependency))
        self.assertEqual(self.scan(), ["✓  1 repos"])

    def test_local_upstream_is_not_cloud(self):
        self.git(self.repo, "branch", "base")
        self.git(self.repo, "branch", "--set-upstream-to=base", "main")
        self.assertEqual(self.scan(), ["repo with spaces  main  ↔local"])

    def test_long_names_and_many_rows_are_not_truncated(self):
        branch = "a-very-long-current-branch-name-that-must-not-be-truncated"
        expected = []
        for i in range(35):
            name = f"repository-{i:02d}-with-a-name-wider-than-the-terminal"
            self.git(self.home, "init", f"--initial-branch={branch}", str(self.documents / name))
            expected.append(f"{name}  {branch}  no commits yet")
        self.assertEqual(self.scan(), expected)


if __name__ == "__main__":
    unittest.main()
