# dotfiles

Collections of my config files.

## Nushell setup (desktop or minimal server)

Install Nushell first (`sudo pacman -S --needed nushell`), then run as your normal
user from the repo root:

```sh
nu --no-config-file update.nu
nu
```

If your normal shell will not start, launch `nu --no-config-file` (for example
as your terminal's command), then run:

```sh
sh ~/Documents/dotfiles/install.sh
```

You can also run that script from Bash/sh. It starts the updater without loading
`config.nu` or `env.nu`; a working interactive Nu session is not required.
Repo module imports resolve beside the real config file, so newly pulled modules
work before setup creates their individual links. This does not hide syntax
errors: use the config-free shell to repair those.

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
  local directory; `~/Dropbox` is the separate local sync folder.
  After initialization, use `--schedule 30s` for autosync and `--check` for status.
  For setup and SSH browser authorization, see `dot_local/bin/dropbox-sync.md`.

## SSH inventory selector

```sh
ssh-sel.nu ~/Documents/ansible-playbooks/hosts --host dyn1
```

Omit `--host` to choose with fzf. Requires Nushell, Python 3 and OpenSSH.
The selector reads the inventory on each run and uses the host's port (default
22), dedicated `ansible_ssh_private_key_file`, and `ansible_ssh_args`,
`ansible_ssh_common_args`, `ansible_ssh_extra_args`. Quoted options such as
`ProxyCommand` and strict `UserKnownHostsFile` pins are passed through to SSH.
`--printcmd` copies the complete shell-quoted command using `wl-copy`;
`--copyid` uses the same connection options with `ssh-copy-id`.
This is a flat YAML inventory selector, not Ansible's group-variable/template
resolver. Server replacement must still refresh the inventory and trusted pins;
the Cherry deployment in ansible-playbooks now updates its managed `dyn1` block.

## Yazi

All shared Yazi settings live in `dot_config/yazi`; Hyprconf owns only the desktop
portal configuration that launches it. Setup also replaces old Hyprconf Yazi
symlinks (confirm when prompted).

When `ya` is installed, setup installs the pinned official Git plugin if missing
(requires Git and network access on first install). After installing Yazi later,
rerun setup. Restart Yazi to load changes.

File sizes remain visible, with Git markers inside repositories:
`M` modified/unstaged, `S` staged, `A` added, `D` deleted, `U` updated/conflicted,
`?` untracked, `!` ignored. Clean files and non-repository files have no marker;
directories reflect changes inside them.

The same config supports the portal picker: Esc cancels and double-click submits
a file only in chooser mode (`--chooser-file`); normal Yazi behavior is preserved.

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
For a complete config served over HTTPS, `sb setup [url]` accepts its URL or prompts
when omitted, downloads it and enables hourly automatic updates; `sb pull` refreshes manually. `sb current` explicitly
shows whether the config came from a file or URL; `sb active [outbound-tag]` shows
the selected outbound and protocol via the local API. See
[sing-box usage and safety details](dot_config/sing-box/README.md).
The shared desktop template's local proxy uses port `12334`.

## zapret: direct Discord / YouTube

The ISP-tested configuration, pinned-source installer, sing-box coexistence
rules, Vesktop WebRTC setting, verification notes, and rollback are saved in
[`etc/zapret`](etc/zapret/README.md). Installation is explicit and is not run by
`update.nu`; the setup preserves proxy routing for other sites.
