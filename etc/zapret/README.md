# zapret: direct Discord and YouTube

Working Arch Linux setup, tested on the wired ISP on 2026-10-28. YouTube playback
and Discord voice were confirmed by the user with the baseline; intermittent voice
reconnects were later reported. The current UDP repeat reduction is an unverified
stability trial. Longer-term ISP behavior can change.
No remote proxy is used for these services. Existing sing-box routing for other
sites is preserved.

## Reproduce

This is opt-in system setup, **not** part of `update.nu`. Review the configs first:

- `config`: upstream defaults plus the tested strategies/ports; uplink `enp12s0`,
  IPv4 only. Change `IFACE_WAN` if the uplink name differs.
- `hosts-*.txt`: targets, including subdomains.
- `sing-box.conf`: systemd drop-in keeping generated packets out of sing-box's TUN.
- `sing-box/*.json`: credential-free routing overlays for the existing sing-box setup.
- `vesktop-settings.json`: **one setting to merge**, not a complete app config.

Install build/runtime dependencies, then run the installer **as your normal user**:

```sh
sudo pacman -S --needed base-devel git curl nftables libnetfilter_queue zlib
sh etc/zapret/install.sh
```

The installer builds bol-van/zapret at pinned commit
`c4d0b1990129dce2b28095277173ee0d7702d304`, installs root-owned files under
`/opt/zapret`, installs the upstream systemd service plus our drop-in, and enables
startup at boot. Build code runs without sudo. Fetching upstream may temporarily
need a working proxy; the installed bypass does not. Back up local changes before
rerunning: upstream files and the saved zapret config are replaced. The installer
does not edit private VPN configs or start/stop sing-box.

### Coexist with the existing sing-box setup

Skip this section on a machine without sing-box. These overlays assume the base
config has an outbound tagged `direct` and the service loads `-C /etc/sing-box`.
They do not contain VPN credentials or replace `/etc/sing-box/config.json`.

`00-local-udp.json` is the existing transparent UDP overlay: UID **1000**, interface
`sing-udp`, address `172.19.0.1/30`. Adjust UID/address if necessary; do not install
a duplicate TUN overlay if one already exists. It preserves the existing Steam,
TCP/ICMP, DNS, and private-network bypass rules. `00-00-zapret.json` sorts first
and exempts Discord/Vesktop plus the target domains from remote proxy routing.
Only UDP 443 is sniffed here; unrelated UDP is not delayed by extra sniffing.

```sh
# Back up existing versions before replacement, if present.
sudo install -m 640 -o root -g sing-box etc/zapret/sing-box/*.json /etc/sing-box/
sudo sing-box check -C /etc/sing-box
sudo systemctl restart sing-box
```

These separate overlay files survive subscription updates. Other proxy traffic
keeps its original routing. Even an app explicitly using the local HTTP proxy
gets a direct upstream connection for the listed domains.

### Vesktop

Use normal `vesktop`, not a Wi-Fi VPN namespace launcher. The tracked Nushell
`hdiscord` helper strips proxy environment variables and uses `--no-proxy-server`.
For an explicit launch from any shell:

```sh
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  vesktop --no-proxy-server
```

In **Vesktop Settings → WebRTC IP Handling Policy**, select **Default Public
Interface Only**, then leave and rejoin voice. This is the native setting that
worked; a Chromium `--force-webrtc-ip-handling-policy` command-line flag was
ineffective because Vesktop overrides it. Docker/libvirt/TUN interfaces otherwise
became ICE candidates, and the active voice socket was observed bound to a Docker
bridge address.

For file-based reproduction, **quit Vesktop first**, then merge only the saved
preference, preserving login and other settings (run from the repository root):

```sh
python - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'vesktop/settings.json'
p.parent.mkdir(parents=True, exist_ok=True)
settings = json.loads(p.read_text()) if p.exists() else {}
settings.update(json.loads(Path('etc/zapret/vesktop-settings.json').read_text()))
p.write_text(json.dumps(settings, indent=4) + '\n')
PY
```

Do not replace/symlink the whole app settings file with this fragment.

## Tested strategies and pitfalls

Discord TCP ports: **443,2053,2083,2087,2096,8443**. Profile:

```text
--dpi-desync=fake,multisplit --dpi-desync-split-pos=1
--dpi-desync-fooling=badseq --dpi-desync-repeats=6
--dpi-desync-fake-tls-mod=rnd,dupsid,sni=www.google.com
```

The fixed fake SNI is essential here. Random fake names passed the TLS handshake
and WebSocket HELLO tests but froze after a few messages. The fixed SNI sustained
85 successive WebSocket ping/pong exchanges and the real authenticated client.
Voice signaling was observed on **TCP 2087** and **2053**, not just 443.

YouTube TCP: fake + multisplit at 1, badseq, six repeats. YouTube QUIC: fake,
six repeats, hostlist-limited. Discord discovery/STUN: fake on
**UDP 443,19294-19344,50000-50100**; actual voice streams used **19320/19305**.
The original six-repeat voice profile connected successfully but the user later
reported RTC reconnects. The current trial reduces **only discovery/STUN repeats
to two**, reducing fake bursts during ongoing checks without changing TCP or QUIC.
This is a hypothesis, not a confirmed fix: validate over a long call and several
leave/rejoin cycles. Fewer repeats may weaken the bypass; restore six in the last
`--filter-l7=discord,stun` profile if connection setup or stability gets worse.

The dedicated voice ranges are queued throughout calls so later STUN/ICE checks
are processed too; RTP/audio is not deliberately modified. CPU cost scales with
packet rate; narrow to endpoint firewall sets if throughput becomes an issue.

The systemd drop-in adds policy rule **101**, mark **0x40000000/0x40000000**, lookup
`main`; otherwise sing-box's catch-all rule could route generated packets into
the TUN. Zapret must not OR its bits into conntrack marks because sing-box tests
its conntrack marks exactly, so TTL-expired filtering is disabled. No TTL-based
tricks are used in this setup.

Verified: 45/45 fresh direct requests across resolved addresses, TLS 1.2/1.3,
Chrome-style TLS, and repeated YouTube HTTP/3; a real 10 MiB YouTube media range
at about 10 MB/s; Discord WebSocket and live voice. Without zapret processing,
Discord/YouTube TLS stalled while Google TLS worked. One tested media edge did
not answer HTTP/3; media TCP worked, so HTTP/3 is not promised on every edge.
A final concurrent sweep had two transient Discord timeouts (43/45); both
addresses then passed three sequential retries. The setup is empirical, not a
guarantee against every route or later ISP change. No account tokens, browser
cookies, or voice payloads were read for testing.

## Check / rollback

For a config-only update (no rebuild), back up and validate before restarting.
Restarting can briefly interrupt connections; rejoin voice afterwards:

```sh
sudo cp -a /opt/zapret/config /opt/zapret/config.before-voice-tuning
sh -n etc/zapret/config
sh -c '. ./etc/zapret/config; /opt/zapret/nfq/nfqws --dry-run --qnum=200 $NFQWS_OPT' &&
  sudo install -m 644 etc/zapret/config /opt/zapret/config &&
  sudo systemctl restart zapret
sudo install -m 644 etc/zapret/README.md /opt/zapret/README.local.md
```

To undo that trial (before replacing the backup with another update):

```sh
sudo cp -a /opt/zapret/config.before-voice-tuning /opt/zapret/config
sudo systemctl restart zapret
```

Service and reachability checks (these do **not** prove voice stability):

```sh
sudo systemctl status zapret --no-pager
sudo journalctl -u zapret -n 40 --no-pager
sudo systemctl restart zapret
sudo sing-box check -C /etc/sing-box
curl --noproxy '*' --max-time 8 https://discord.com/api/v10/gateway
curl --noproxy '*' --http3-only --max-time 8 -o /dev/null https://www.youtube.com/
```

To restore the old proxy behavior, disable the **new target-exception overlay**
first, leaving the pre-existing local UDP overlay in place:

```sh
sudo mv /etc/sing-box/00-00-zapret.json /etc/sing-box/00-00-zapret.disabled
sudo sing-box check -C /etc/sing-box
sudo systemctl restart sing-box
sudo systemctl disable --now zapret
```

If installed without sing-box, only the last command is needed. Stopping zapret
removes its hooks/policy rule without flushing Docker, libvirt, or sing-box rules.
Revert the native WebRTC policy through Vesktop Settings if desired. To restore
`hdiscord`'s previous behavior, use `with-proxy { gui vesktop ...$args }` instead.

## Retired failed setup

Removed from this machine: `discord-vpn.service`, `/usr/local/bin/discord-vpn`,
`/usr/share/applications/discord-vpn.desktop` ("Vesktop (Wi-Fi VPN)"),
`/etc/sing-box-discord`, `/etc/netns/discord-vpn`, the unused namespace, and the
ineffective `~/.config/vesktop-flags.conf` experiment. The normal Vesktop/Discord
launchers and main sing-box service remain.

Private backup of those retired files:
`/var/backups/discord-vpn-retired-20261028T141606/files.tar.gz` (root-only, **not**
committed; contains private VPN configuration). Diagnostic scans/results remain
in `~/Projects/zapret-tests` on this machine, not in the shared repository.
