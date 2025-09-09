alias ll = ls -as
alias - = cd -
alias l = lazygit
alias n = nvim
alias f = fzf
alias c = clear
alias p = python
alias h = htop
alias he = hyprctl dispatch exit
def hc [] {
  hyprctl clients -j |
  from json |
  select class title xwayland size floating pseudo fullscreen fullscreenClient |
  to json |
  jq
}
def batt [] {
  upower -i /org/freedesktop/UPower/devices/battery_BAT0
  | grep -E "state|to full|percentage"
}
alias battery = batt
alias b = batt
def hm [] {
  hyprctl monitors all -j |
  from json |
  select id name description width height refreshRate |
  to json |
  jq
}
alias lsgpu = lspci -d ::03xx

$env.EDITOR = "nvim"
$env.PAGER = "/usr/bin/less"
$env.LESS = "-R --mouse --wheel-lines=3"
$env.SYSTEMD_PAGER = $env.PAGER
$env.SYSTEMD_LESS = $env.LESS
$env.PATH = ($env.PATH | append '~/.local/bin')

# oh-my-posh init nu
oh-my-posh init nu --config ~/.config/oh-my-posh/base.yaml
source ~/.zoxide.nu
alias cd = z
alias dt = zsh -c date

alias nhh = nvim ~/.config/hypr/hyprland.conf
alias nhm = nvim ~/.config/hypr/monitors.conf
alias nhr = nvim ~/.config/hypr/windowrules.conf
alias nhw = nvim ~/.config/hypr/windowrules.conf
alias nhs = nvim ~/.config/hypr/startup.conf
alias nhb = nvim ~/.config/hypr/binds.conf

alias nc = config nu

$env.ANI_CLI_HIST_DIR = $env.HOME + "/Dropbox/ani-cli"
$env.BAT_STYLE = "plain"
$env.BAT_THEME = "ansi"
def lsblk [] {
    ^lsblk -o NAME,FSTYPE,TYPE,SIZE,MOUNTPOINTS,UUID
    | bat -l conf
}
alias pf = poweroff
alias rb = reboot

