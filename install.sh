./dot_local/bin/sync.py link .local/bin/sync.py
zoxide init nushell | save -f ~/.zoxide.nu
sync.py link .config/yazi/yazi.toml
sync.py link .config/nushell/config.nu
sync.py link .config/lazygit/config.yml
sync.py link .config/oh-my-posh/base.yaml
sync.py link .local/bin/ssh-sel.nu
sync.py link .local/bin/dropbox-sync
sync.py link .local/bin/tiktok.nu
sync.py link .config/opencode/opencode.jsonc

cp -r ~/Documents/dotfiles/dot_config/zellij ~/.config/

# copy vscode config
zsh -c 'mkdir -p ~/.config/Code/User'
cp -r dot_config/Code/User ~/.config/Code
# sync (symlinks not gonna work)
sync.py get ~/.config/Code/User/keybindings.json
sync.py put ~/.config/Code/User/keybindings.json

sync.py get ~/.config/Code/User/settings.json
sync.py put ~/.config/Code/User/settings.json

# pi
sync.py link .pi/agent
sync.py link .unipi/config/notify
bash ~/.pi/agent/install.sh
