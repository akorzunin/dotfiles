def ll [a: path = "."] {
  ls --long $a | select name type size modified mode user group
}
alias - = cd -
alias l = lazygit
alias ld = lazydocker
alias n = nvim
alias f = fzf
alias y = yazi
def cl [] { clear; reset }
alias py = python
alias p = python
alias h = htop
alias o = opencode
alias oh = with-env { http_proxy: "localhost:12334" https_proxy: "localhost:12334" } { opencode }
alias he = hyprctl dispatch exit
def hc [] {
  hyprctl clients -j |
  from json |
  select pid class initialClass title initialTitle xwayland pinned size floating fullscreen fullscreenClient |
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
$env.PATH = ($env.PATH | append '~/.npm-global/bin')
$env.PATH = ($env.PATH | append '~/go/bin')
$env.PATH = ($env.PATH | append '~/.local/share/pnpm')
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
alias nn = nvim ~/.config/niri/config.kdl

alias nc = config nu

$env.ANI_CLI_HIST_DIR = $env.HOME + "/Dropbox/ani-cli"
$env.BAT_STYLE = "plain"
$env.BAT_THEME = "ansi"
def lsblk [] {
    ^lsblk -o NAME,FSTYPE,TYPE,SIZE,MOUNTPOINTS,UUID
    | bat -l conf
}
def pf [] {
  let reply = (input --default "y" "Do you want to continue? (Y/n): ")
  if $reply in ["yes" "Y" "y"] {
      sudo systemctl poweroff
  } else {
      print "Aborted."
  }
}
alias sus = systemctl suspend
alias rb = reboot
alias sv = sudo v2raya
alias ts = timeshift-launcher
alias record-selection = zsh -c 'wf-recorder -g "$(slurp)" -f a.mp4'
# TODO: make code less cringe
def screenshot [
  --delay (-d)
] {
  if ($delay) {
    zsh -c 'grim -g "$(slurp -d; sleep 10; notify-send Screenshot-saved)" - | wl-copy'
  } else {
    zsh -c 'grim -g "$(slurp -d; hyprctl dispatch movecursortocorner 1 > /dev/null)" - | wl-copy'
  }
}
alias gp = git pull
alias gpr = git pull --rebase
alias gf = git fetch
alias gl = git log --oneline --graph --all --decorate --color
alias upd = sudo pacman -Syyu
alias task = go-task
let ru_en_mapping = {
    'й': 'q' 'ц': 'w' 'у': 'e' 'к': 'r' 'е': 't' 'н': 'y' 'г': 'u' 'ш': 'i'
    'щ': 'o' 'з': 'p' 'х': '[' 'ъ': ']' 'ф': 'a' 'ы': 's' 'в': 'd' 'а': 'f'
    'п': 'g' 'р': 'h' 'о': 'j' 'л': 'k' 'д': 'l' 'ж': ';' 'э': "'" 'я': 'z'
    'ч': 'x' 'с': 'c' 'м': 'v' 'и': 'b' 'т': 'n' 'ь': 'm' 'б': ',' 'ю': '.'
    'ё': '`'
    'Й': 'Q' 'Ц': 'W' 'У': 'E' 'К': 'R' 'Е': 'T' 'Н': 'Y' 'Г': 'U'
    'Ш': 'I' 'Щ': 'O' 'З': 'P' 'Х': '{' 'Ъ': '}' 'Ф': 'A' 'Ы': 'S' 'В': 'D'
    'А': 'F' 'П': 'G' 'Р': 'H' 'О': 'J' 'Л': 'K' 'Д': 'L' 'Ж': ':' 'Э': '"'
    'Я': 'Z' 'Ч': 'X' 'С': 'C' 'М': 'V' 'И': 'B' 'Т': 'N' 'Ь': 'M' 'Б': '<'
    'Ю': '>' 'Ё': '~'
}
$env.config = (
    $env.config
    | upsert hooks.pre_execution [ {||
        $env.repl_commandline = (commandline)
        if ($env.repl_commandline =~ '^\P{ascii}') {
          let wm = if ('NIRI_SOCKET' in $env) {
            'niri'
          } else if ('HYPRLAND_INSTANCE_SIGNATURE' in $env) {
            'hyprland'
          } else {
            'unknown'
          }
          if $wm == 'unknown' {
            print "Error: unsupported or undetected window manager"
            return
          }
          print $"Swapping layout for ($wm): " -n
          if $wm == 'niri' {
            niri msg action switch-layout 0
          } else {
            hyprctl switchxkblayout all 0
          }
          let fixed_cmd = ($env.repl_commandline
            | split chars
            | each {|c|
              $ru_en_mapping
              | get -o $c
              | default $c
            } | str join
          )
          exec nu -e $"$env.config.show_banner = false; ($fixed_cmd)"
        }
    } ]
)

def desktop-sync [
  --pull (-p)
] {
  def check_repo [repo_path: path, name: string, pull: bool] {
    print -n $"(ansi green)($name) config:(ansi reset)"
    if $pull {
      git -C $repo_path pull --rebase --autostash | ignore
    } else {
      git -C $repo_path fetch | ignore
    }
    print -n $" (git -C $repo_path rev-parse --abbrev-ref HEAD) "
    print -n $"(git -C $repo_path status --porcelain=v2 -b |
      find branch.ab | parse '{a} {branch} {ab}' | get ab | to text
    )"
    git -C $repo_path status -s
    print ""
  }
  check_repo ~/.config/nvim/ "Neovim" $pull
  check_repo ~/Documents/hyprconf/ "Hyprland" $pull
  check_repo ~/Documents/dotfiles/ "Dotfiles" $pull
}

def ff-compress [file: path, out?: string, --crf (-c): int = 23] {
  print $"Compressing ($file) to ($out | default $"($file).out.mp4")"
  ffpb -i $file -vcodec libx264 -crf $crf ($out | default $"($file).out.mp4")
}

def fl [] {
  do --ignore-errors {
    nautilus . e> /dev/null
  }
}

# History search
def hs [
  --execute (-e)  # Execute the command instead of copying it
] {
  let command = history
      | get command
      | reverse
      | to text
      | fzf
      | str trim --right
  if ($command | is-empty) {
    return
  }
  $command | wl-copy
  if $execute {
    print $"Executing: ($command)"
    nu -c $command
  } else {
    print $"Copying: ($command)"
  }
}
alias mpv = mpv --ao=pulse

def vesktop-release-audio [] {
  pactl --format=json list sink-inputs
  | from json
  | where {|stream| (($stream.properties | get -o "application.name") == "Chromium") and (($stream.properties | get -o "application.process.binary") == "electron") }
  | get index
  | each {|id| ^pactl kill-sink-input $id }
  | ignore
}
alias vra = vesktop-release-audio

# Open recent project
def po [
  --editor (-e): string = "code"
  --projectsdir (-p): path = "~/Documents"
] {
  let projects_dir = ($projectsdir | path expand)
  let selected_project = (
      ls $projects_dir
      | each {|e|
        let git_date = do --ignore-errors {
          git -C $e.name log -1 --format=%cI e> /dev/null | into datetime
        }
        return {
          ...$e,
          last_git_commit_date: ($git_date | default $e.modified),
        }
      }
      | sort-by last_git_commit_date -r
      | update name {$in | split column '/' | get ($in | columns | last) | last }
      | update last_git_commit_date {$in | date humanize }
      | each { |row| $"($row.name)\t($row.last_git_commit_date)" }
      | to text
      | fzf --delimiter '\t' --with-nth 1
      | str trim
  )
  if ($selected_project | is-empty) {
    return
  }
  let project_name = ($selected_project | split row "\t" | get 0)
  let projects_path = ($projects_dir | path join $project_name | path expand)
  if ($editor in ["code", "zeditor"]) {
    ^$editor $projects_path
    return
  }
  if ($editor == "kitty") {
    ^kitty --detach $projects_path
    return
  }
  # for terminal editors
  nu -e ($editor + " " + $projects_path + "; exit 0")
  return
}
alias pre-commit = uvx prek
alias pin = uvx prek install
alias pu = uvx prek uninstall
alias pa = uvx prek run --all-files
alias pd = pnpm dev
alias pt = pnpm tsc
alias logs = journalctl -xb --reverse
$env.config.history = {
    file_format: sqlite
    max_size: 1000000
    sync_on_enter: true
    isolation: true
}
def nt [msg: string = 'Done!'] {
    notify-send $msg
}
def nt-hist [] {
    dunstctl history | from json | get data | select message.data | get 'message.data' | first | each {|e| $e | str replace -a -r '<.+?>' ""} | reverse
}
def type [q: string, --all(-a)] {
    if $all {
      which -a $q | to yaml | bat -l yaml
      return
    }
    which $q | to yaml | bat -l yaml
}

# Initialize carapace lazily with `c`.
def --env enable-carapace [] {
  $env.CARAPACE_BRIDGES = 'zsh,fish,bash,inshellisense'
  let cache = $"($nu.cache-dir)/carapace.nu"
  if not ($cache | path exists) {
    mkdir $nu.cache-dir
    carapace _carapace nushell | save --force $cache
  }
  source $"($nu.cache-dir)/carapace.nu"
}
alias c = enable-carapace

# run gui app from terminal and then close it
def --wrapped gui [...cmd: string] {
  if ($cmd | is-empty) {
    error make { msg: "Usage: gui <command> [args...]" }
  }
  ^sh -c 'nohup setsid "$@" >/dev/null 2>&1 &' sh ...$cmd
  sleep 100ms
  if ("KITTY_WINDOW_ID" in $env) {
    ^kitty @ close-window --self
  } else {
    exit
  }
}
def with-proxy [cmd: closure, proxy: string = "http://localhost:12334"] {
  with-env {
    http_proxy: $proxy
    https_proxy: $proxy
    no_proxy: ($env.no_proxy? | default "localhost,127.0.0.1,::1")
  } $cmd
}
def --wrapped hpi [...args: string] {
  with-proxy { pi-mode --default ...$args }
}
def --wrapped hpie [...args: string] {
  with-proxy { pi-mode --edit ...$args }
}
def --wrapped hpis [...args: string] {
  with-proxy { pi-mode --subagent ...$args }
}
def --wrapped hdiscord [...args: string] {
  with-proxy { gui vesktop ...$args }
}
def --wrapped htg [...args: string] {
  with-proxy { gui Telegram ...$args }
}
def --wrapped hspotify [...args: string] {
  with-proxy { DISPLAY="" gui spotify-launcher ...$args }
}
def --env mkdir [...args: string] {
  ^mkdir ...$args
  let dirs = ($args | where {|a| not ($a | str starts-with "-") })
  if $env.LAST_EXIT_CODE == 0 and not ($dirs | is-empty) {
    load-env { _: (($dirs | last) | path expand) }
  }
}
def --env mkcd [...dirs: path] {
  mkdir ...$dirs
  cd ($dirs | last)
}
