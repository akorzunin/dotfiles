alias ll = ls -as
alias - = cd -
alias l = lazygit
alias n = nvim
alias f = fzf
alias c = clear
alias p = python
alias he = hyprctl dispatch exit
def hc [] {
  hyprctl clients -j |
  from json |
  select class title xwayland size floating pseudo fullscreen fullscreenClient |
  to json |
  jq
}
def hm [] {
  hyprctl monitors all -j |
  from json |
  select id name description width height refreshRate |
  to json |
  jq
}
alias lsgpu = lspci -d ::03xx
def tiktok [] {
  let addr = "192.168.1.126"
  print Scannin ports for adb
  print "rustscan -r 34000-47000 --scan-order random -a 192.168.1.126 -g -t 400"
  let out = (rustscan -r 34000-47000 --scan-order random -a 192.168.1.126 -g -t 400)
  print $out
  let p = ($out | parse $"($addr) -> [{port}]" | get port | first)
  let user_input = (input --default Y $"Connect to port ($p)? \(Y/n)")
  if ($user_input | str trim | str starts-with "n") {
    print "Aborting"
    return
  }
  adb connect $"($addr):($p)"
  scrcpy --no-video --audio-buffer=400
}

$env.EDITOR = "nvim"
$env.PAGER = "/usr/bin/less"
$env.LESS = "--mouse --wheel-lines=3"
$env.SYSTEMD_PAGER = "/usr/bin/less"
$env.SYSTEMD_LESS = "--mouse --wheel-lines=3 -R"
$env.PATH = ($env.PATH | append '~/.local/bin')

# oh-my-posh init nu
oh-my-posh init nu --config ~/.config/oh-my-posh/base.yaml
source ~/.zoxide.nu
alias cd = z
