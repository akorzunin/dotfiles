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

def sing-box-private-config [] {
  let candidates = [
    ($env.HOME | path join "Dropbox/env/vpn.json")
    ($env.HOME | path join ".config/sing-box/vpn.json")
  ]
  let available = ($candidates | where {|path| $path | path exists})
  if ($available | is-empty) {
    error make {msg: "sing-box private config not found; sync ~/Dropbox/env/vpn.json or create ~/.config/sing-box/vpn.json"}
  }
  $available | first
}

def install-sing-box-config [] {
  let shared = ($env.PWD | path join "dot_config/sing-box/config-all-proxy.json")
  let private = (sing-box-private-config)
  let private_config = (open $private)
  let private_outbounds = ($private_config.outbounds? | default [] | where {|outbound|
    let type = ($outbound.type? | default "")
    ($outbound.tag? | default "") != "direct" and $type not-in ["direct" "block" "dns"]
  })
  if ($private_outbounds | is-empty) {
    error make {msg: $"No outbounds found in ($private); add at least one VPN outbound"}
  }

  # Normalize complete Hiddify configs to their outbounds before merging.
  let private_only = ($nu.temp-dir | path join "sing-box-private.json")
  {outbounds: $private_outbounds} | to json | save --force $private_only
  chmod 600 $private_only

  let proxy = ($private_outbounds | where {|outbound|
    ($outbound.tag? | default "") == "proxy" and ($outbound.type? | default "") == "selector"
  })
  let has_proxy = not ($proxy | is-empty)
  let vpn_tags = ($private_outbounds | where {|outbound|
    let type = ($outbound.type? | default "")
    let tag = ($outbound.tag? | default "")
    $tag != "" and $tag != "proxy" and $type not-in ["selector" "urltest" "direct" "block" "dns"]
  } | get tag)

  let selector = ($nu.temp-dir | path join "sing-box-selector.json")
  if not $has_proxy {
    if ($vpn_tags | is-empty) {
      error make {msg: "Private sing-box config has no selectable VPN outbounds"}
    }
    {
      outbounds: [{
        type: "selector"
        tag: "proxy"
        outbounds: ($vpn_tags | append "direct")
        default: ($vpn_tags | first)
      }]
    } | to json | save --force $selector
  }

  let merged = ($nu.temp-dir | path join "sing-box-config.json")
  if $has_proxy {
    ^sing-box merge $merged -c $shared -c $private_only
  } else {
    ^sing-box merge $merged -c $shared -c $private_only -c $selector
  }
  if $env.LAST_EXIT_CODE != 0 {
    error make {msg: "sing-box configuration merge failed"}
  }
  chmod 600 $merged

  let checked = (^sing-box check -c $merged | complete)
  if $checked.exit_code != 0 {
    print ($checked.stderr | str trim)
    error make {msg: "Generated sing-box configuration is invalid"}
  }

  let installed = (^sudo install -D -o root -g sing-box -m 640 $merged /etc/sing-box/config.json | complete)
  if $installed.exit_code != 0 {
    print ($installed.stderr | str trim)
    error make {msg: "Could not install /etc/sing-box/config.json"}
  }
  ^sudo systemctl daemon-reload
  rm -f $private_only $selector $merged
  print $"Installed sing-box config from ($private)"
}

# Keep individual config links: linking all of .config would replace unrelated files.
let configs = [
  .config/sing-box/config-all-proxy.json
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

install-sing-box-config

# Hyprconf owns the picker package variant, config links, and portal services.
^sh ($env.HOME | path join Documents/hyprconf/_postinstall/yazi_file_picker.sh)
if $env.LAST_EXIT_CODE != 0 {
  error make {msg: "Hyprconf Yazi file picker setup failed"}
}
