# dotfiles

Collections of my config files.

## Desktop sync (Nushell)

- `desktop-sync -pu`: pull, then apply the newly pulled setup.
- `desktop-sync -u`: install declared packages, link configs, and install the merged sing-box config.

The shared sing-box config is tracked at `dot_config/sing-box/config-all-proxy.json`. Put private VPN outbounds in `~/Dropbox/env/vpn.json` so the same profiles can be used on another machine; `~/.config/sing-box/vpn.json` is supported as a local fallback. See [`dot_config/sing-box/README.md`](dot_config/sing-box/README.md).
