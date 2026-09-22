# sing-box

## Config files

`config-all-proxy.json` supplies the shared listener and routing. Private JSON
files supply VPN outbounds; they are not committed.

`sb` / `sb list` lists JSON files containing outbounds in these directories
(non-recursively):

- `~/.local/share` — e.g. `config1.json`, `config2.json`
- `~/.config/sing-box`
- `~/Dropbox/env`

Override the directories in Nushell when needed:

```nu
$env.SB_CONFIG_DIRS = [($env.HOME | path join ".local/share") "/path/to/configs"]
```

A private file needs an `outbounds` array with uniquely tagged VPN outbounds.
Complete Hiddify/sing-box JSON files are also accepted: only proxy/group
outbounds are retained, not their DNS, inbound or routing settings. Provider
specific outbound dependencies must still pass `sing-box check`.

```json
{
  "outbounds": [{
    "type": "vless",
    "tag": "vpn-nt1",
    "server": "YOUR_SERVER",
    "server_port": 443,
    "uuid": "YOUR_UUID"
  }]
}
```

Include the TLS/Reality and transport fields required by your provider.
Protect private files with `chmod 600`; never commit credentials.

## Install and use

Run `desktop-sync -u`, then open a new Nushell session to load the commands.
Setup preserves an existing installed config. On first installation it installs
an available config automatically only when there is exactly one candidate.

```nu
sb                         # list available configs (works while stopped)
sb apply                   # searchable config picker
sb apply config1.json       # validate, install, restart, then test VPN
sb apply ~/.local/share/config2.json
sb on                      # also enable startup at boot
sb status
sb test                    # HTTPS connectivity + latency via the selected VPN
sb test vpn-nt1             # test a server without changing selection
sb outbounds               # show live outbound selectors
sb use vpn-nt1             # select an outbound without restarting
sb use direct
sb logs
sb off                     # stop and disable startup at boot
```

Press Tab after `sb ` for actions, after `sb apply ` for config files, and after
`sb use ` / `sb select ` / `sb test ` for live outbound tags. Outbound completion
requires the service to be running. Duplicate config names complete to full paths.
The picker uses full paths too; canceling it leaves the service unchanged.

`sb apply config1` also accepts the filename without `.json`. Config filenames
and outbound tags are different: `sb apply nt1-ssh` loads `nt1-ssh.json`, while
`sb use nt1-SSH` selects that exact, case-sensitive tag in the running config.
`sb use` / `sb select` cannot load a config file or start a stopped service.

Use a full path when filenames occur in multiple directories. `sb apply` uses
one file at a time, merges it with the shared config, checks it before replacing
`/etc/sing-box/config.json`, then restarts the service. A failed validation leaves
the installed config untouched. A restart failure is reported; inspect `sb logs`.
After a successful restart, `sb apply` waits briefly for the API and runs `sb test`
automatically. A failed connectivity test reports an error but leaves the newly
installed config active; it does not roll back.

If the private file has no `proxy` selector, one is generated from ordinary VPN
outbounds plus `direct`. Outbound selection is persisted by sing-box's cache.

## Check VPN connectivity

`sb test` resolves the current selector and uses sing-box's Clash API to make
an HTTPS probe to `https://www.gstatic.com/generate_204` through that outbound.
It reports the outbound and latency in milliseconds, or returns an error on
failure (10-second probe timeout). Direct mode is rejected, so a working direct
connection is not reported as a working VPN. No selector changes are made.

This checks outbound connectivity, not just whether the service is running.
It does not test app proxy settings or the local port 12334 listener. A failure
can also mean the test site is unavailable; use `sb logs` to investigate.

## Proxy mode (no TUN)

The HTTP/SOCKS mixed proxy listens at **127.0.0.1:12334**, matching Hiddify.
Apps already using that endpoint need no changes. Only proxy-configured apps
are affected; this does not set desktop proxy preferences or capture all traffic.
UDP uses the selected outbound; non-UDP Russian domains/IPs go direct, and
other traffic uses the selected outbound.

Stop Hiddify before applying a config so it releases port 12334. If applicable:

```bash
systemctl --user disable --now hiddify-mail-vpn.service
```

Do not run the shared JSON alone: its `proxy` outbound comes from a private file.
To validate the installed config:

```bash
sudo sing-box check -c /etc/sing-box/config.json
```
