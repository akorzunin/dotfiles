# dotfiles

Collections of my config files.

## Desktop sync (Nushell)

- `desktop-sync -pu`: pull, then apply the newly pulled setup.
- For first setup, from the repo root run `nu --no-config-file update.nu`.
  This installs required packages and generates the zoxide and carapace init files
  before linking Nushell config. Existing init files are kept.
- `dropbox-sync --setup`: create an rclone remote named `dropbox` with
  **Storage** set to **Dropbox**. The name identifies the connection, not a
  local directory; `~/Dropbox` is the separate local mount/sync folder.
  For SSH browser authorization, see `dot_local/bin/dropbox-sync.md`.

## sing-box

Put private VPN configs in `~/.local/share/*.json`, `~/.config/sing-box/*.json`.
Use `sb list` to discover them and `sb apply <name-or-path>` to activate one.
The local proxy uses port `12334`
