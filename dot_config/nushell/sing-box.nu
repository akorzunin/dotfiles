export def sb-actions [] {
  [list configs apply test on off enable disable restart status logs outbounds use select change]
}

export def sb-arguments [context: string] {
  let action = ($context | str trim --left | split row --regex '\s+' | get --optional 1 | default "")
  if $action == "apply" {
    let configs = (sb-configs)
    return ($configs | each {|file|
      let duplicates = ($configs | where name == $file.name | length)
      {value: (if $duplicates > 1 { $file.path } else { $file.name }), description: $file.path}
    })
  }
  if $action in [use select change test] {
    # Completion must remain quiet and bounded when the service is stopped.
    return (try {
      let response = (^curl --fail --silent --noproxy "*" --max-time 1 http://127.0.0.1:9091/proxies | complete)
      if $response.exit_code != 0 { return [] }
      let proxies = ($response.stdout | from json | get proxies)
      if $action == "test" {
        $proxies | columns
      } else {
        $proxies | get proxy.all
      }
    } catch { [] })
  }
  []
}

export def sb-apply [config?: string] {
  let selected = if ($config | is-empty) {
    let configs = (sb-configs)
    if ($configs | is-empty) {
      error make {msg: "No configs found; add a private JSON config to ~/.local/share or set SB_CONFIG_DIRS"}
    }
    $configs | get path | input list --fuzzy "Choose a sing-box config"
  } else {
    $config
  }
  if ($selected | is-empty) { return }
  install-sing-box-config $selected --restart
  print "Testing VPN connectivity…"
  sb-test --wait
}

# Test the outbound itself, so routing rules cannot silently bypass the VPN.
export def sb-test [outbound: string = "proxy", --wait] {
  let api = "http://127.0.0.1:9091"
  let retries = if $wait { [--retry 5 --retry-connrefused --retry-delay 1 --retry-max-time 5] } else { [] }
  let response = (^curl --fail-with-body --silent --show-error --noproxy "*" --max-time 5 ...$retries $"($api)/proxies" | complete)
  if $response.exit_code != 0 {
    error make {msg: "Cannot reach the sing-box API; run sb status or sb on"}
  }
  let proxies = ($response.stdout | from json | get proxies)
  mut tag = $outbound
  mut visited = []
  loop {
    if $tag in $visited {
      error make {msg: "Outbound selector cycle detected"}
    }
    $visited = ($visited | append $tag)
    let proxy = ($proxies | get --optional $tag)
    if $proxy == null {
      error make {msg: $"Unknown outbound: ($tag); see sb outbounds"}
    }
    if ($proxy.type? | default "" | str lowercase) == "direct" or $tag == "direct" {
      error make {msg: "Direct mode is selected, not a VPN; use sb use <VPN-tag> first"}
    }
    let selected = ($proxy.now? | default "")
    if $selected == "" { break }
    $tag = $selected
  }
  let target = "https://www.gstatic.com/generate_204"
  let encoded = ($tag | url encode --all)
  let result = (^curl --fail-with-body --silent --show-error --noproxy "*" --max-time 15 --get --data-urlencode $"url=($target)" --data-urlencode "timeout=10000" $"($api)/proxies/($encoded)/delay" | complete)
  if $result.exit_code != 0 {
    error make {msg: $"VPN check failed for ($tag): HTTPS probe failed or timed out. The server or test site may be unavailable; see sb logs."}
  }
  let delay = ($result.stdout | from json | get delay)
  {outbound: $tag, status: "HTTPS probe passed", latency_ms: $delay, target: $target}
}

# Override with a list of directories in $env.SB_CONFIG_DIRS.
export def sb-configs [] {
  let dirs = ($env.SB_CONFIG_DIRS? | default [
    ($env.HOME | path join ".local/share")
    ($env.HOME | path join ".config/sing-box")
    # ($env.HOME | path join "Dropbox/env")
  ])
  $dirs | each {|dir|
    glob (($dir | path expand | str replace --all '[' '[[]') + "/*.json")
  } | flatten | uniq | sort | where {|file|
    ($file | path basename) != "config-all-proxy.json" and (try {
      let config = (open $file)
      ($config.outbounds? | default [] | length) > 0
    } catch { false })
  } | each {|file| {name: ($file | path basename), path: $file}}
}

export def install-sing-box-config [config: string, --restart] {
  let shared = ($env.HOME | path join ".config/sing-box/config-all-proxy.json")
  let matches = (sb-configs | where {|file|
    $file.name == $config or $file.name == $"($config).json"
  })
  let private = if ($config | path expand | path exists) {
    $config | path expand
  } else if ($matches | length) == 1 {
    $matches | first | get path
  } else {
    error make {msg: "Config not found or name is ambiguous; use sb list and pass a full path"}
  }
  let private_config = (open $private)
  let private_outbounds = ($private_config.outbounds? | default [] | where {|outbound|
    let type = ($outbound.type? | default "")
    ($outbound.tag? | default "") != "direct" and $type not-in ["direct" "block" "dns"]
  })
  if ($private_outbounds | is-empty) {
    error make {msg: $"No outbounds found in ($private); add at least one VPN outbound"}
  }

  # mktemp creates a private directory before any credentials are written.
  let temp = (^mktemp -d | str trim)
  try {
  # Normalize complete Hiddify configs to their outbounds before merging.
  let private_only = ($temp | path join "private.json")
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

  let selector = ($temp | path join "selector.json")
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

  let merged = ($temp | path join "config.json")
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
  if $restart {
    ^sudo systemctl restart sing-box.service
    if $env.LAST_EXIT_CODE != 0 {
      error make {msg: "Config installed but sing-box failed to restart; run sb logs"}
    }
  }
  print $"Installed sing-box config from ($private)"
  } catch {|err|
    rm -rf $temp
    error make {msg: $err.msg}
  }
  rm -rf $temp
}

