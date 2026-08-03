---
name: commit
description: Generate a one-line Conventional Commit message from git changes, then on the next user confirmation run git commit. Use for /commit or when the user asks to commit changes.
model: omniroute/oc/deepseek-v4-flash-free
---

# Commit

## Turn 1: generate and commit in one turn

1. Run `git rev-parse --show-toplevel` and work from that repo root.
2. Run `git status --short`; if there are no changes, say `No git changes to commit.` and stop.
3. If staged changes exist, read only staged changes with `git diff --cached --stat` and `git diff --cached --`.
4. If nothing is staged, read unstaged/untracked changes with `git diff --stat`, `git diff --`, and file names from `git status --short`. Tell the user the commit will run `git add -A` first.
5. Commit template:

```text
<type>(<scope>): <subject>

Reply `commit` to run: git commit -m "<same message>"
```
6. Commit without asking user to proceed

Message rules:
- Use Conventional Commits: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, or `revert`.
- Add a short scope when obvious from touched files; omit it when not obvious.
- One line, lowercase subject, imperative mood, no period, max 72 chars if possible.
- Prefer the main user-facing change over mechanical details.
- `git add -A && git commit -m "<message>"`.
- Otherwise run `git commit -m "<message>"`.
