# dotfiles

Collections of my config files.

## Nushell setup (desktop or minimal server)

Install Nushell first (`sudo pacman -S --needed nushell`), then run as your normal
user from the repo root:

```sh
nu --no-config-file update.nu
nu
```

Setup links the configs and scripts. Python is the only additional required
package; if absent, setup installs it with `sudo pacman`. No AUR helper, desktop
checkout, or desktop packages are required on a server.

- oh-my-posh, zoxide and Carapace are optional. Without them, Nu keeps its default
  prompt/completions and `cd` works normally.
- For installed zoxide/Carapace, setup generates missing init files and preserves
  existing ones. After installing either tool, rerun setup and restart Nu.
- `c` enables installed Carapace. If its cache is deleted, Nu still starts; rerun
  setup and restart Nu to restore completions.
- Other aliases require their tools only when invoked; setup does not install them.
- The Hyprconf picker hook runs only with a Wayland session, its checkout and `yay`.
- `desktop-sync -pu`: pull, then apply the newly pulled setup. This desktop helper
  requires the Neovim, Hyprconf and dotfiles repositories; servers can run
  `update.nu` directly.
- `dropbox-sync --setup`: create an rclone remote named `dropbox` with
  **Storage** set to **Dropbox**. The name identifies the connection, not a
  local directory; `~/Dropbox` is the separate local mount/sync folder.
  For SSH browser authorization, see `dot_local/bin/dropbox-sync.md`.

## Forgotten Git pushes

Run `push-check` in Nushell to check only immediate repositories/worktrees in
`~/Documents`, and only their current branch. No recursive scanning.

```nu
push-check                     # Offline: cached remote refs
push-check --fetch             # Fetch all remotes for a fresh comparison
push-check ~/Documents/project # Check just this repository
```

Compact plain-text output avoids Nushell table truncation; repo names are bold
cyan in terminals (or when Nushell's `use_ansi_coloring` is `true`):

```text
ansible-playbooks  main  ↑2
aurora  main  ↑1 ↓3 ±1
```

- `↑N` / `↓N`: commits ahead / behind the tracked upstream. Both means diverged;
  reconcile before pushing.
- `±N`: uncommitted status entries, including untracked files.
- `?upstream` / `!upstream`: no upstream / missing upstream ref.
- `no commits yet`, `↔local`: no initial commit, local-only upstream. E.g. `a master no commits yet ±14` is repo `a`, branch
  `master`, with no committed history and 14 uncommitted entries.
- `!fetch` / `!git`: fetch / Git error; details go to stderr.

Clean, synced repos and detached HEADs (even with uncommitted changes) are
omitted; `✓ N repos` means nothing to report.
This compares upstreams, not custom push refspecs; server permissions/protected
branches can still reject a push. Nothing is committed, pulled, or pushed, and
network access happens only with `--fetch`. Symlinked directories and bare repos
are skipped.

After setup, restart Nu to load the command. In the separate Hyprconf repo,
`niri/config.kdl` binds **Mod+Shift+G** to open Kitty with `push-check`, leaving an
interactive shell open without the welcome banner for reviewing results or
manually pushing. Run
`push-check --fetch` there if you want refreshed remote state.

## sing-box

Install `sing-box` and `curl` separately if needed; setup does not install VPN tools.
Put private VPN configs in `~/.local/share/*.json`, `~/.config/sing-box/*.json`.
Use `sb list` to discover them and `sb apply <name-or-path>` to activate one.
The local proxy uses port `12334`
