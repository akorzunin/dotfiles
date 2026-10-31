#!/usr/bin/env nu

def main [
    file: path = "/etc/ansible/hosts"
    --host (-h): string = ""
    --copyid (-c)
    --printcmd (-p)
    --vault-password-file: path = ""
] {
    let inv  = (open -r $file | from yaml --ignore-tags)
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
    let inventory_key = (($h.ansible_private_key? | is-not-empty) or ($h.ansible_ssh_private_key? | is-not-empty))
    mut ssh_options = [-p (($h.ansible_port? | default 22) | into string)]
    if (not $inventory_key) and ($h.ansible_ssh_private_key_file? | is-not-empty) {
        $ssh_options = ($ssh_options | append [-o $"IdentityFile=($h.ansible_ssh_private_key_file | to json -r)"])
    }
    # SSH options contain shell quoting (notably ProxyCommand); split without executing it.
    for field in [ansible_ssh_args ansible_ssh_common_args ansible_ssh_extra_args] {
        let value = ($h | get -o $field | default "")
        let options = (^python3 -c 'import json, shlex, sys; print(json.dumps(shlex.split(sys.argv[1])))' $value | from json)
        $ssh_options = ($ssh_options | append $options)
    }
    let ssh_options = $ssh_options
    let destination = $"($h.ansible_user)@($h.ansible_host)"
    if $inventory_key {
        if $printcmd {
            # A raw ssh command cannot recreate an ephemeral decrypted identity.
            mut command = [ssh-sel.nu $file --host $sel_host]
            if ($vault_password_file | is-not-empty) {
                $command = ($command | append [--vault-password-file $vault_password_file])
            }
            if $copyid { $command = ($command | append '--copyid') }
            $command | to json -r
                | ^python3 -c 'import json, shlex, sys; print(shlex.join(json.load(sys.stdin)))'
                | tee { wl-copy }
            return
        }
        let helper = ($env.CURRENT_FILE | path expand | path dirname | path join ssh-sel-key.py)
        mut arguments = [--inventory $file --host $sel_host --vault-password-file $vault_password_file]
        if $copyid { $arguments = ($arguments | append '--copyid') }
        print "Connecting with Vault-backed inventory identity"
        ^python3 $helper ...$arguments -- ...$ssh_options $destination
        exit $env.LAST_EXIT_CODE
    }
    let ssh_cmd = ([ssh] | append $ssh_options | append $destination | to json -r
        | ^python3 -c 'import json, shlex, sys; print(shlex.join(json.load(sys.stdin)))')
    match $printcmd {
        true => {
            echo $ssh_cmd | tee { wl-copy }
            return
        }
        false => {
            null
        }
    }
    print $"Connecting: ($ssh_cmd)"
    match $copyid {
        true => {
            ssh-copy-id ...$ssh_options $destination
        }
        false => {
            TERM=xterm ssh ...$ssh_options $destination
        }
    }
}
