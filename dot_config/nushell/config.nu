alias ll = ls -as
alias - = cd -
alias l = lazygit
alias n = nvim
alias f = fzf
alias c = clear
alias py = python
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

alias nc = config nu

$env.ANI_CLI_HIST_DIR = $env.HOME + "/Dropbox/ani-cli"
$env.BAT_STYLE = "plain"
$env.BAT_THEME = "ansi"
def lsblk [] {
    ^lsblk -o NAME,FSTYPE,TYPE,SIZE,MOUNTPOINTS,UUID
    | bat -l conf
}
alias pf = sudo systemctl poweroff
alias sus = systemctl suspend
alias rb = reboot
def я [] {
  print ((
    [71 111 108 111 118 107 97 32 111 116 32 104 121 97]
    | each { char --integer $in }
    | str join
  ))
  hyprctl switchxkblayout all 0
  __zoxide_z
}
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
          print "Swapping layout: " -n
          hyprctl switchxkblayout all 0
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

def desktop-sync [] {
  def check_repo [repo_path: path, name: string] {
    print -n $"(ansi green)($name) config:(ansi reset)"
    git -C $repo_path fetch | ignore
    print -n $" (git -C $repo_path rev-parse --abbrev-ref HEAD) "
    print -n $"(git -C $repo_path status --porcelain=v2 -b |
      find branch.ab | parse '{a} {branch} {ab}' | get ab | to text
    )"
    git -C $repo_path status -s
    print ""
  }
  check_repo ~/.config/nvim/ "Neovim"
  check_repo ~/Documents/hyprconf/ "Hyprland"
  check_repo ~/Documents/dotfiles/ "Dotfiles"
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

# Open recent project
def po [
  --editor (-e): string = "code"
  --projectsdir (-p): path = "~/Documents"
] {
  let projects_dir = ($projectsdir | path expand)
  let selected_project = ($projects_dir + "/" + (
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
      | select name last_git_commit_date
      | update name {$in | split column '/' | get ($in | columns | last) | last }
      | update last_git_commit_date {$in | date humanize }
      | to csv -n -s '|'
      | ^column -s '|' -t -o ' | '
      | fzf
    )
  )
  let projects_path = (
    $selected_project
      | split column ' | '
      | get ($in | columns |first)
      | first
      | path expand
  )
  ^$editor $projects_path
}
alias pre-commit = uvx prek
alias pd = pnpm dev
alias pt = pnpm tsc
