# Run from the dotfiles repository root: nu --no-config-file update.nu
# Add required packages here as configs gain dependencies.
let packages = [git-delta sing-box curl]
let missing = ($packages | where {|package|
  (^pacman -Q $package | complete).exit_code != 0
})
if not ($missing | is-empty) {
  ^yay -S --needed ...$missing
  if $env.LAST_EXIT_CODE != 0 {
    error make {msg: "Dependency installation failed"}
  }
}

use dot_config/nushell/sing-box.nu *

# Keep individual config links: linking all of .config would replace unrelated files.
let configs = [
  .config/sing-box/config-all-proxy.json
  .config/yazi/yazi.toml
  .config/yazi/theme.toml
  .config/nushell/config.nu
  .config/nushell/sing-box.nu
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

# Hyprconf owns the picker package variant, config links, and portal services.
^sh ($env.HOME | path join Documents/hyprconf/_postinstall/yazi_file_picker.sh)
if $env.LAST_EXIT_CODE != 0 {
  error make {msg: "Hyprconf Yazi file picker setup failed"}
}
