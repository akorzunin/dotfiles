#!/usr/bin/env nu

def main [
    file: path = "/etc/ansible/hosts"
    --host (-h): string = ""
    --copyid (-c)
] {
    let inv  = (open -r $file | from yaml)
    print $"Loaded inventory from ($file)"
    let hosts = (
        $inv
        | transpose group hosts
        | get hosts
        | flatten
        | reduce {|a, b| $a | merge $b}
    )
    print ($hosts | columns)
    mut sel_host = ""
    if ($host | str length) > 0 {
        $sel_host = $host
    } else {
        $sel_host = ($hosts | columns | str join "\n" | fzf)
    }
    print $"Selected host: (ansi green)($sel_host)(ansi reset)"
    let h = ($hosts | select $sel_host | flatten | first)
    let ssh_cmd = $"($h.ansible_user)@($h.ansible_host) -p ($h.ansible_port)"
    print $"Connecting: ($ssh_cmd)"
    match $copyid {
        true => {
            ssh-copy-id -p ($h.ansible_port) ($h.ansible_user)@($h.ansible_host)
        }
        false => {
            TERM=xterm ssh ($h.ansible_user)@($h.ansible_host) -p ($h.ansible_port)
        }
    }
}
