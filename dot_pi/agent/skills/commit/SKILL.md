---
name: commit
description: Generate a one-line Conventional Commit message from git changes, then on the next user confirmation run git commit. Use for /commit or when the user asks to commit changes.
---

# Commit

Two-turn protocol only:

## Turn 1: generate

1. Run `git rev-parse --show-toplevel` and work from that repo root.
2. Run `git status --short`; if there are no changes, say `No git changes to commit.` and stop.
3. If staged changes exist, read only staged changes with `git diff --cached --stat` and `git diff --cached --`.
4. If nothing is staged, read unstaged/untracked changes with `git diff --stat`, `git diff --`, and file names from `git status --short`. Tell the user the commit will run `git add -A` first.
5. Output exactly:

```text
<type>(<scope>): <subject>

Reply `commit` to run: git commit -m "<same message>"
```

Message rules:
- Use Conventional Commits: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, or `revert`.
- Add a short scope when obvious from touched files; omit it when not obvious.
- One line, lowercase subject, imperative mood, no period, max 72 chars if possible.
- Prefer the main user-facing change over mechanical details.

Do not commit in turn 1.

## Turn 2: commit

If the previous assistant message was a commit message and the user confirms with `commit`, `yes`, `y`, or `ok`:

- If turn 1 said nothing was staged, run `git add -A && git commit -m "<message>"`.
- Otherwise run `git commit -m "<message>"`.
- Return the git output only.

If the user supplies a different commit message, run the same command with their message instead.
