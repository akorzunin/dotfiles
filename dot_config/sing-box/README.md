# sing-box

## Config files

- `config-all-proxy.json`: shared logging, inbounds, direct outbound, and routing. Safe to keep in the repo.
- `~/.config/sing-box/vpn.json`: private VPN outbound settings. Keep outside the repo and do not add it to chezmoi.

sing-box merges the files passed with repeated `-c` flags. The private file must contain an `outbounds` array with an outbound tagged `vpn`; shared routes refer to that tag.

On this machine the existing VPN settings have already been moved to the private file. On another machine, securely copy that file or create it using your provider's outbound settings:

```json
{
  "outbounds": [
    {
      "type": "vless",
      "tag": "vpn",
      "server": "YOUR_SERVER",
      "server_port": 443,
      "uuid": "YOUR_UUID"
    }
  ]
}
```

This example is only a skeleton: include your provider's required TLS/Reality and other transport settings.

```bash
chmod 600 ~/.config/sing-box/vpn.json
```

## Validate and run

Install sing-box first. From this repository directory:

```bash
sing-box check \
  -c "$PWD/config-all-proxy.json" \
  -c "$HOME/.config/sing-box/vpn.json"

sudo sing-box run \
  -c "$PWD/config-all-proxy.json" \
  -c "$HOME/.config/sing-box/vpn.json"
```

The TUN inbound needs elevated networking privileges, hence `sudo`. The shell expands `$HOME` before sudo runs, so the private file is read from your user's home directory.

If deployed via chezmoi, replace `$PWD/config-all-proxy.json` with `$HOME/.config/sing-box/config-all-proxy.json` in both commands. Any service launching sing-box must likewise load both files with `-c`, using absolute paths.

Do not launch the shared file alone: it references the private `vpn` outbound.

## Current routing

- UDP goes through the VPN.
- Remaining traffic to `.ru`, `.su`, `.рф` and IPs in the `geoip-ru` rule set goes direct.
- Other traffic goes through the VPN.
- Local mixed proxy: `127.0.0.1:1080`; system proxy configuration is enabled.

## Secrets

Do not commit `vpn.json`. If credentials were previously committed publicly, rotate them; deleting them from the current config does not remove Git history.
