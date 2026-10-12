def "nu-complete dropbox-sync interval" [] {
  [
    {value: "30s", description: "30 seconds after each sync finishes"}
    {value: "1min", description: "1 minute after each sync finishes"}
    {value: "5min", description: "5 minutes after each sync finishes"}
    {value: "1h", description: "1 hour after each sync finishes"}
  ]
}

# Keep this signature aligned with dot_local/bin/dropbox-sync; execution stays external.
export extern "dropbox-sync" [
  --pull        # Download without deleting; skip newer local files, back up replacements
  --push        # Upload without deleting; skip newer remote files, back up replacements
  --sync        # Run two-way sync, including deletions
  --init        # Initialize/rebuild sync tracking; requires --sync
  --dry-run     # Preview a transfer without changing files
  --schedule: string@"nu-complete dropbox-sync interval" # Enable autosync, e.g. 30s or 5min
  --unschedule  # Disable autosync and stop its running transfer
  --setup (-s)  # Configure the Dropbox connection; does not sync
  --check (-c)  # Show autosync status, next run, and last scheduled sync result
  --help (-h)   # Show command help
]
