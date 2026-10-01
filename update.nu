# Run from the dotfiles repository root: nu --no-config-file update.nu
# Python is the only linking dependency; optional shell/desktop tools are not installed.
if (which python | is-empty) {
  ^sudo pacman -S --needed python
  if $env.LAST_EXIT_CODE != 0 {
    error make {msg: "Dependency installation failed"}
  }
}

# Generate init only for installed integrations; config.nu tolerates absent files.
let zoxide = ($env.HOME | path join .zoxide.nu)
if not (which zoxide | is-empty) and not ($zoxide | path exists) {
  let generated = (^zoxide init nushell | complete)
  if $generated.exit_code != 0 { error make {msg: "zoxide initialization failed"} }
  $generated.stdout | save --force $zoxide
}
let carapace = ($nu.cache-dir | path join carapace.nu)
if not (which carapace | is-empty) and not ($carapace | path exists) {
  mkdir $nu.cache-dir
  let generated = (^carapace _carapace nushell | complete)
  if $generated.exit_code != 0 { error make {msg: "carapace initialization failed"} }
  $generated.stdout | save --force $carapace
}

use dot_config/nushell/sing-box.nu *

# Keep individual config links: linking all of .config would replace unrelated files.
let configs = [
  .config/sing-box/config-all-proxy.json
  .config/yazi/yazi.toml
  .config/yazi/theme.toml
  .config/nushell/config.nu
  .config/nushell/sing-box.nu
  .config/nushell/push-check.nu
  .config/lazygit/config.yml
  .config/oh-my-posh/base.yaml
  .config/opencode/opencode.jsonc
  .pi/agent
  .unipi/config/notify
]
let scripts = (glob dot_local/bin/* | each {|file| $".local/bin/($file | path basename)"})
for relative in ($configs | append $scripts) {
  let source = ($relative | str replace '.' 'dot_' | path expand)
  let target = ($env.HOME | path join $relative)
  # Already-correct links need no confirmation; conflicts use sync.py's existing prompt.
  if ($target | path type) == 'symlink' {
    if ($target | path expand) == $source {
      continue
    }
  }
  ^python ./dot_local/bin/sync.py link $relative
  if $env.LAST_EXIT_CODE != 0 {
    error make {msg: $"Failed to link ($relative)"}
  }
}

if not (which sing-box | is-empty) {
  if not ("/etc/sing-box/config.json" | path exists) {
    let available = (sb-configs)
    if ($available | length) == 1 {
      install-sing-box-config ($available | first | get path)
    } else {
      print "Run sb list, then sb apply <name-or-path> to choose a sing-box config."
    }
  } else {
    print "Keeping the installed sing-box config; use sb apply <name-or-path> to update it."
  }
}

# Hyprconf owns desktop picker setup; headless servers need neither it nor yay.
let picker = ($env.HOME | path join Documents/hyprconf/_postinstall/yazi_file_picker.sh)
if ("WAYLAND_DISPLAY" in $env) and ($picker | path exists) and not (which yay | is-empty) {
  ^sh $picker
  if $env.LAST_EXIT_CODE != 0 {
    error make {msg: "Hyprconf Yazi file picker setup failed"}
  }
}
