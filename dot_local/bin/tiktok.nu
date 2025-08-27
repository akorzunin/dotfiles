#!/usr/bin/env nu

def main [
  --addr (-a): string = "192.168.1.126"
  --portrange (-r): string = "34000-47000"
] {
  print 'Scanning ports for adb'
  print $"rustscan ($portrange) ($addr)"
  let out = (rustscan -r $portrange --scan-order random -a $addr -g -t 400)
  print $out
  let ps = ($out | parse $"($addr) -> [{port}]" | get port)
  if ($ps | length) == 0 {
    print "No ports found"
    return
  }
  let p = ($ps | first)
  let user_input = (input --default Y $"Connect to port ($p)? \(Y/n)")
  if ($user_input | str trim | str starts-with "n") {
    print "Aborting"
    return
  }
  adb connect $"($addr):($p)"
  scrcpy --no-video --audio-buffer=400
}
