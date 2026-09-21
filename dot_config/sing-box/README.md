# sing-box

## Config files

- `config-all-proxy.json` is the shared, non-secret configuration tracked in this repo.
- `~/Dropbox/env/vpn.json` is the private configuration shared between machines. `~/.config/sing-box/vpn.json` is also accepted as a local-only fallback.

The private file only needs an `outbounds` array. Keep every VPN profile in that array and give each profile a unique `tag`:

```json
{
  "outbounds": [
    {
      "type": "vless",
      "tag": "vpn-nt1",
      "server": "YOUR_SERVER",
      "server_port": 443,
      "uuid": "YOUR_UUID"
    },
    {
      "type": "vless",
      "tag": "vpn-pl1",
      "server": "ANOTHER_SERVER",
      "server_port": 443,
      "uuid": "ANOTHER_UUID"
    }
  ]
}
```

Include the TLS/Reality and transport fields required by the provider. A complete Hiddify/sing-box JSON file also works: setup keeps its proxy/group outbounds and drops app-specific DNS, direct, block, inbound, and route settings.

`desktop-sync -u` builds `/etc/sing-box/config.json` from the shared file and the private file. If the private file does not already contain a selector tagged `proxy`, setup creates one from all ordinary private outbounds and adds `direct`. The selected outbound is persisted in sing-box's cache.

The Dropbox file contains credentials, so keep it private and set restrictive permissions:

```bash
chmod 600 ~/Dropbox/env/vpn.json
```

## Install and use

Run this from a Nushell session after the private file has synced:

```nu
desktop-sync -u
sb on
sb status
sb outbounds
sb use vpn-nt1
sb use direct
sb off
```

`sb on` and `sb off` enable/disable the system `sing-box.service`. `sb use` changes the `proxy` selector through the local Clash API; it does not restart the tunnel. The TUN inbound requires the capabilities supplied by the packaged system service.

Validate the generated configuration with:

```bash
sudo sing-box check -c /etc/sing-box/config.json
```

The local mixed proxy is `127.0.0.1:1080`; UDP uses the selected outbound, while non-UDP Russian domains/IPs go direct and other traffic uses the selected outbound. Do not start `config-all-proxy.json` by itself: its `proxy` outbound is generated from the private file during setup.

If Hiddify is no longer needed, stop its old user service separately:

```bash
systemctl --user disable --now hiddify-mail-vpn.service
```

Do not commit the private file or provider credentials. If credentials were previously committed publicly, rotate them; deleting them from the current config does not remove Git history.
