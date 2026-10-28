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

## URL config with automatic updates

For a provider that serves a **complete sing-box JSON config** over HTTPS:

```nu
sb setup    # prompts for URL, downloads now, enables hourly updates
sb setup https://example.com/linux.json  # or pass the URL directly
sb pull     # refresh manually, even while stopped
sb current  # explicitly shows source: url and its URL
```

Without an argument, `sb setup` asks for the URL with hidden input, keeping it
out of shell history. Press Enter without a URL to cancel without changing anything.
`sb setup <url>` skips the prompt, but the URL may be saved in shell history.
URL paths often contain credentials: do not commit them or share
`sb current` output publicly. Settings are stored privately in
`/var/lib/sing-box-subscription/source.json` and the user's source-tracking file.

Setup requires sudo and installs a root-owned updater and systemd service/timer.
The timer never executes writable repo scripts and requires no passwordless-sudo
rule. Rerun `sb setup` after pulling changes to the updater itself.

The URL config is used **in full**, without merging the shared desktop template.
Existing `urltest` groups and their automatic outbound switching are preserved.
Only use a trusted provider: its config controls listeners, routing and outbounds.
Downloads go directly, bypassing application proxy environment variables.
Each download is validated with `sing-box check` before atomic replacement.
Unchanged JSON does not trigger a restart; download/validation failures keep the
working config. A failed restart restores the old config; the last replaced
config is also retained privately as `previous.json` alongside `source.json`.
This checks service startup, not VPN connectivity; use `sb test` for that.

Updates run about hourly, starting five minutes after boot, while sing-box is
running. `sb off` therefore pauses updates; `sb on` resumes them. Manual `sb pull`
can start a stopped service. Restarting retains outbound selection when the
provider enables sing-box's cache; selection is not forced to a different tag.

```nu
sudo systemctl status sing-box-update.timer --no-pager
sudo journalctl -u sing-box-update.service -e --no-pager
sudo systemctl disable --now sing-box-update.timer  # turn off automatic updates
```

`sb apply <local-file>` disables URL updates so they cannot overwrite that local
config. `sb pull` switches back to the stored URL manually; run `sb setup` again
if you also want to re-enable the timer. There is one machine-wide URL, not a
separate subscription for each user or `sing-box@` instance.

## Install and use

Install `sing-box` and `curl` first (`sudo pacman -S --needed sing-box curl`).
Run `nu --no-config-file update.nu` from the dotfiles repo (or `desktop-sync -u`
on a configured desktop), then open a new Nushell session to load the commands.
Setup preserves an existing installed config. On first installation it installs
an available config automatically only when there is exactly one candidate.

```nu
sb                         # list available configs (works while stopped)
sb apply                   # searchable config picker
sb apply config1.json       # validate, install, restart, then test VPN
sb apply ~/.local/share/config2.json
sb on                      # also enable startup at boot
sb status
sb current                 # config name, source path, installed path, service state
sb active                  # selected group chain, outbound and protocol
sb active auto             # inspect a differently named group
sb test                    # fast Clash HTTPS delay check (not a reliability test)
sb test vpn-nt1 --mode full # UDP + stability + bandwidth, without changing selection
sb test-all --mode udp      # test every VPN outbound, printing results as they finish
sb outbounds               # show live outbound selectors
sb use vpn-nt1             # select an outbound without restarting
sb use direct
sb logs
sb off                     # stop and disable startup at boot
```

Press Tab after `sb ` for actions, after `sb apply ` for config files, and after
`sb use ` / `sb select ` / `sb test ` / `sb active ` for live outbound tags. Outbound completion
requires the service to be running. Duplicate config names complete to full paths.
The picker uses full paths too; canceling it leaves the service unchanged.

`sb current` shows the last config installed by this user, even while stopped,
including `source: file` and its path, or `source: url`, its URL and timer state.
Source tracking starts with the next installation via `sb apply`, `sb setup`,
`sb pull` or initial dotfiles setup; older installations show an unknown source.
Changes made outside these commands (or setup by another user) are not tracked.
The service state is not a VPN connectivity check; use `sb test`.

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

### Browser / desktop proxy settings

```bash
gsettings set org.gnome.system.proxy.http host '127.0.0.1'
gsettings set org.gnome.system.proxy.http port 12334
gsettings set org.gnome.system.proxy.https host '127.0.0.1'
gsettings set org.gnome.system.proxy.https port 12334
gsettings set org.gnome.system.proxy mode 'manual'
```

```bash
gsettings set org.gnome.system.proxy mode 'none'
```

### Direct Discord / YouTube with zapret

The optional [zapret setup](../../etc/zapret/README.md) saves the tested strategies
and separate `00-00-zapret.json` / `00-local-udp.json` overlays. It keeps those
services direct, including requests to the local HTTP proxy, while preserving
other proxy routing. The overlays do not contain private VPN outbounds and
survive subscription refreshes. Install explicitly; general dotfiles setup does
not change system-wide DPI bypass rules.

## Active outbound and protocol

`sb active [outbound-tag]` follows the current selection through nested selector
and `urltest` groups and reports the final outbound's protocol (e.g. VLESS or
Trojan), without a connectivity probe. It defaults to the `proxy` group; use
`sb outbounds` to find tags if your provider uses another group name.
Direct mode is displayed too. This is a snapshot of group selection, not a list
of live connections: routing rules or existing connections can use other outbounds.
The protocol field does not describe TLS/Reality or transport settings.

Like `sb outbounds` and `sb test`, this requires the Clash API at
`127.0.0.1:9091`. URL configs must enable it themselves; they are not modified
to add it. `sb current` instead shows the installed config source, even offline.

## Check VPN connectivity

Both commands support `--mode quick|udp|bandwidth|stability|full`:

| Mode | What it checks |
| --- | --- |
| `quick` (default) | One Clash API HTTPS delay probe to gstatic. Fast screening only: a pass does **not** establish UDP support or sustained reliability. The probe timeout is 30 seconds, with a 35-second API request limit. |
| `udp` | Six independent SOCKS5 UDP/STUN binding probes: three each to Google (19302) and Cloudflare (3478), with a 4-second receive timeout. Reports replies, loss, RTT spread and per-sample errors, including unsupported UDP. |
| `stability` | Exactly `--attempts` fresh HTTPS connections (default 20), alternating gstatic and Cloudflare, with a 1-second pause between attempts. Failures and timeouts count as attempts; testing continues after them. No retries or connection reuse hide late timeouts. Reports successes/attempts, min/median/max HTTPS request times from successful attempts, and individual samples. These are complete request times, not network RTT; timing is unavailable if every attempt fails. Each request has a 15-second limit, so slower connections make the test take longer—not reduce the attempt count. |
| `bandwidth` | Bounded Cloudflare download **and** upload. `--bytes` sets the payload in each direction (default 5,000,000: ~10 MB total per outbound). Reports Mbps and transfer failures; each transfer has a 15-second limit. This is a short throughput sample, not a maximum line-speed measurement. |
| `full` | UDP, stability, then bandwidth. |

```nu
sb test --mode stability --attempts 30
sb test vpn-nt1 --mode udp
sb test-all --mode full --attempts 30 --bytes 10000000
sb test-all --mode stability --threads 2
sb test-all --mode bandwidth | to json       # collect complete structured results
sb test-all | sort-by outbound                # opt into a final sorted table
```

`sb test` resolves the current selector to its concrete outbound. Direct mode is
rejected. `sb test-all` tests each concrete VPN outbound, skipping selector and
URL-test groups, direct, reject/block, DNS, and `workstation-hop` (an intermediate
transport which only permits SSH destinations). The complete
`ssh-via-workstation` and `cherry-ssh-via-workstation` exits are still tested.

**Interactive reports show a native two-column Nushell table for each outbound
as it finishes**, including UDP loss, connection counts, speeds and failure
reasons as flat, wrapping cells—not collapsed nested records. Repeated errors are grouped by target with their sample count.

The commands **always return structured data**: a record for `sb test`, and a
stream of records for `sb test-all`. The display hook only formats the view, so
`$ans.last` retains the complete result (with this config's result capture enabled).
No `--json` flag is needed to pipe, save or inspect results; it remains available
to opt out of the readable report. Pipelines and variable assignments do not
print live reports. `| to json` naturally waits to collect all results.

```nu
sb test --mode full
$ans.last.udp.samples | table --expand  # inspect the preceding test's raw samples

let results = (sb test-all --mode full)
$results | where status != passed | to json
```

Detailed modes keep failures in the result records, including for a single
outbound; inspect `status` in scripts. The original single-outbound quick check
still raises an error on failure.

Deep modes read `/etc/sing-box/config.json` (prompting for `sudo` read access if
needed), then run temporary **unprivileged** sing-box instances with private
loopback SOCKS listeners. Production inbounds, controllers, cache, services and
routing rules are not started; the probe is forced through the requested exit,
retaining its configured detours and DNS. The running service and selectors are
not changed. Temporary configs, listeners and processes are cleaned up; Ctrl-C
cleanup can wait for the current bounded request. Configs requiring privileged
endpoints, files unavailable to your user, or DNS policies referencing removed
route rule sets can fail startup; the error is shown.
`quick` needs only the live Clash API and does not read the config.

`--threads` defaults to four workers, or **one for bandwidth/full** to avoid
competing bandwidth samples. Override it to trade accuracy for speed. Public
probe endpoints see your exit address; bandwidth consumes the stated data for
each tested outbound. A failed endpoint alone is not proof the VPN is broken.

UDP/STUN is a WebRTC reachability check, **not a Discord voice guarantee**: it
does not test Discord's media servers, ICE negotiation, long-lived media streams,
or application routing. RTT spread is not RTP media jitter. These tests also do
not check app proxy settings or the production port 12334 listener. In particular,
Discord UDP must actually enter sing-box (e.g. via TUN or a UDP-capable app proxy);
setting only a desktop HTTP proxy does not capture it. Use `sb logs` to investigate.

## Proxy mode (no TUN)

The HTTP/SOCKS mixed proxy listens at **127.0.0.1:12334**, matching Hiddify.
Apps already using that endpoint need no changes. Only proxy-configured apps
are affected; this does not set desktop proxy preferences or capture all traffic.
UDP uses the selected outbound; non-UDP Russian domains/IPs go direct, and
other traffic uses the selected outbound.

To validate the installed config:

```bash
sudo sing-box check -c /etc/sing-box/config.json
```
