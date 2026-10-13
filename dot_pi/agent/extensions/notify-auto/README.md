# Automatic Pi notifications

`pi-mode` loads this adapter instead of the upstream npm package directly, in
all presets. It preserves `@pi-unipi/notify` lifecycle notifications and
`/unipi:notify-*` commands, but does not register `notify_user` or advertise the
`notify` / `configure-notify` skills. The dependency's resources are not loaded
as a separate Pi package.

Install dependencies after cloning (Pi does not install local-package dependencies):

```sh
cd ~/.pi/agent/extensions/notify-auto
npm ci --ignore-scripts --legacy-peer-deps
npm test
```

`~/.unipi/config/notify/config.json` enables `agent_settled`, not `agent_end`, so
completion notifications wait for retries, compaction and queued work to finish.
`../notify-sound.ts` plays the configured WAV after a successful, unsuppressed
native notification. Failed/aborted assistant runs keep the existing sound
suppression behavior.

Use `/unipi:notify-settings` to configure channels and events, or
`/unipi:notify-test` for an explicit notification/sound test. Start a new
`pi-mode` process after changing the launcher's extension list; `/reload` in an
older process retains its original npm extension arguments.

To update upstream, change the pinned dependency, reinstall with
`npm install --ignore-scripts --legacy-peer-deps`, and run the tests.
