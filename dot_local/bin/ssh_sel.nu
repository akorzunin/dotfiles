#!/usr/bin/env nu

def main [file: string = "hosts"] {
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
    let sel_host = ($hosts | columns | str join "\n" | fzf)
    print $"Selected host: (ansi green)($sel_host)(ansi reset)"
    let h = ($hosts | select $sel_host | flatten | first)
    let ssh_cmd = $"($h.ansible_user)@($h.ansible_host) -p ($h.ansible_port)"
    print $"Connecting: ($ssh_cmd)"
    ssh ($h.ansible_user)@($h.ansible_host) -p ($h.ansible_port)
}
