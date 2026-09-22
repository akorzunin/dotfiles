# Dropbox local sync

Requires Nushell, rclone (with bisync `--recover` support), and `flock`.
Scheduling requires a running systemd user manager.

## Move from the mount

Close applications and terminals using Dropbox, then run
`dropbox-sync --unmount` (or `-u`). It refuses to unmount while uploads are
queued/active or the cache reports errors. If refused, run `--check` and resolve
the issue before retrying. Do not force-unmount pending uploads. All local transfers refuse a mounted folder.
No-argument invocation still mounts, but refuses nonempty or bisync-initialized
local folders. `--check`, `--force`, and `--tray` remain mount-only operations.

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
propagates deletions and preserves concurrent conflicts as renamed files for
manual resolution. It is not application-level state merging.

The timer runs 30 seconds after user-manager startup, then at the selected
interval after each run finishes. Transfers do not overlap on the same machine.
Offline attempts fail; the next timer invocation retries. Bisync listings live
in `$XDG_STATE_HOME/rclone/bisync`, not the disposable cache directory. Some
errors still require manual recovery: inspect logs and back up both sides before
considering `--init` again. Never automatically reinitialize after a failure.

```
systemctl --user status dropbox-sync.timer dropbox-sync.service
journalctl --user -u dropbox-sync.service
dropbox-sync --unschedule
```

Scheduling uses the current script's absolute path; rerun `--schedule` if it moves.
The timer normally runs only while your user manager is running (enable user
lingering separately if needed). Stop the schedule before changing rclone remotes.

Polling is not instantaneous: remote changes can take multiple polling intervals
to reach another machine. Sync after closing an application and before opening
it on another device. Do not sync live databases/WAL files or concurrently written
application state; use application-native export/sync instead. Files remain
readable locally without internet.
