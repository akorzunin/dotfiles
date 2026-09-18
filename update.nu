# Run from the dotfiles repository root: nu --no-config-file update.nu
# Add required packages here as configs gain dependencies.
let packages = [git-delta]
let missing = ($packages | where {|package|
  (^pacman -Q $package | complete).exit_code != 0
})
if not ($missing | is-empty) {
  ^yay -S --needed ...$missing
  if $env.LAST_EXIT_CODE != 0 {
    error make {msg: "Dependency installation failed"}
  }
}

# Keep individual config links: linking all of .config would replace unrelated files.
let configs = [
  .config/yazi/yazi.toml
  .config/yazi/theme.toml
  .config/nushell/config.nu
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

# Hyprconf owns the picker package variant, config links, and portal services.
^sh ($env.HOME | path join Documents/hyprconf/_postinstall/yazi_file_picker.sh)
if $env.LAST_EXIT_CODE != 0 {
  error make {msg: "Hyprconf Yazi file picker setup failed"}
}
