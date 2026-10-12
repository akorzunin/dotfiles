# Dropbox local sync

Requires Nushell, rclone (with bisync `--recover` support), and `flock`.
Scheduling and `--check` require a running systemd user manager.
Mount mode and its `--unmount`, `--force`, and `--tray` commands have been removed.

## Nushell completions

The dotfiles Nushell config loads native completions for all flags and suggested
`--schedule` intervals (custom intervals still work). No Carapace is needed.
Restart Nushell after updating, then type `dropbox-sync --` and press Tab.
For the current shell, load them with:

```nu
use /path/to/dotfiles/dot_config/nushell/dropbox-sync-completions.nu *
```

## First-time connection

Run `dropbox-sync --setup`. In rclone's menu choose `n` (New remote),
use `dropbox` for the remote name, and choose **Dropbox** for **Storage**
(type `dropbox` or select its listed number). Follow the browser authorization,
confirm the remote, and quit. The remote name is not a local path:
`~/Dropbox` is the separate local folder this script syncs. If you already
have exactly one Dropbox remote under another name, the script uses it too.

Over SSH with no browser on the VM, answer `n` to rclone's browser-auth
question. On your computer with a browser and rclone installed run
`rclone authorize dropbox`, then paste the returned token at the VM's
`config_token>` prompt. Keep that token private. Alternatively, start the
SSH session from your computer with `ssh -L 53682:localhost:53682 archlinux`,
answer `y` to browser auth, and open the printed `127.0.0.1:53682` URL in
your computer's browser. The port forward must be active throughout auth.

Setup only configures the connection: it does not sync or enable autosync.
`--init` requires `--sync`; `--setup --init` is not valid. Follow the two-way
synchronization steps below to initialize, then enable the schedule.
All local transfers still refuse a mounted folder as a safety precaution.

## Explicit transfers

```
dropbox-sync --pull --dry-run
dropbox-sync --pull
dropbox-sync --push --dry-run
dropbox-sync --push
```

These copy without deleting destination files and skip newer destination files.
They are not a two-way conflict detector. Replacements are backed up under
`$XDG_STATE_HOME/rclone/backups` (default `~/.local/state/rclone/backups`) for
pulls, and `.dropbox-sync-backups` on Dropbox for pushes. That remote backup
folder is excluded from transfers. Backups are not automatically pruned.
Local Dropbox desktop-client metadata (`.dropbox`, `.dropbox.attr`, `.dropbox.cache`)
and `.Trash-*` folders at the Dropbox root are excluded from all transfers:
Dropbox rejects some of these names, and the cache/trash are not user data.

## Two-way synchronization

Back up both sides before initialization. Initialization merges both trees,
but **Dropbox wins when a path exists on both sides**. Review the dry run first.

```
dropbox-sync --sync --init --dry-run
dropbox-sync --sync --init
dropbox-sync --sync
dropbox-sync --schedule 30s
```

Initialize separately on each machine. Thereafter use `--sync`, not pull/push:
one-way copying would interfere with bisync change tracking. Regular bisync
propagates deletions. When both sides change a file, the newer modification time
wins and keeps the original filename; the losing version is preserved as a
numbered `.conflict` copy. Equal timestamps can still leave both versions renamed
for manual resolution. Keep device clocks accurate: newer does not necessarily
mean correct. It is not application-level state merging.

This policy only applies to future conflicts. For files already renamed by the
old policy, restore the desired conflict copy to its original filename once,
then run `--sync` (not `--init`). Apply the updated script on every syncing machine.

The timer runs 30 seconds after user-manager startup, then at the selected
interval after each run finishes. Transfers do not overlap on the same machine.
Offline attempts fail; the next timer invocation retries. Bisync listings live
in `$XDG_STATE_HOME/rclone/bisync`, not the disposable cache directory. Some
errors still require manual recovery: inspect logs and back up both sides before
considering `--sync --init --dry-run`, then `--sync --init` to rebuild tracking.
Never automatically reinitialize after a failure. On this machine, a failed
initialization involving `path/disallowed_name` can be retried with those
commands: the desktop-client files are now excluded. If the error persists,
inspect rclone's verbose output for another rejected path rather than repeatedly
retrying.

## Autosync status

```
dropbox-sync --check        # or -c; no arguments also shows status
journalctl --user -u dropbox-sync.service -n 50 --no-pager
journalctl --user -u dropbox-sync.service -f  # follow live logs
dropbox-sync --unschedule  # disable autosync and stop any running transfer
```

`--check` reports initialization, whether the timer is active and enabled for
future user-manager startups, whether a sync is running, and the last scheduled
sync's result/exit code. The timer table shows the next and previous triggers.
An inactive service between runs is normal; `Last result: success (exit 0)`
indicates the last scheduled transfer succeeded. `Autosync: ON` means the timer
is active, not that transfers are necessarily succeeding: check the last result
and logs. Status does not perform a sync or contact Dropbox, and does not need
rclone installed. Manual `--sync` output is not recorded in the service's status.

Scheduling uses the current script's absolute path; rerun `--schedule` if it moves.
The timer normally runs only while your user manager is running (enable user
lingering separately if needed). Stop the schedule before changing rclone remotes.

Scheduled sync is not instantaneous: remote changes can take multiple sync intervals
to reach another machine. Sync after closing an application and before opening
it on another device. Do not sync live databases/WAL files or concurrently written
application state; use application-native export/sync instead. Files remain
readable locally without internet.
