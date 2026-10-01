# Report only: never stage, commit, pull, or push.
def git-output [repo: path, ...args: string] {
  let result = (^git --no-optional-locks -C $repo ...$args | complete)
  if $result.exit_code != 0 {
    error make {msg: ($result.stderr | str trim)}
  }
  $result.stdout | str trim --right --char "\n"
}

# Check only immediate child checkouts/worktrees, or root itself if it is a repo.
export def main [
  root: path = "~/Documents"
  --fetch # Fetch all remotes first (network access); otherwise use cached remote refs
] {
  let root = ($root | path expand)
  if ($root | path type) != "dir" {
    error make {msg: $"Not a directory: ($root)"}
  }
  let repos = if ($root | path join .git | path exists) {
    [$root]
  } else {
    ls --all $root
    | where type == dir
    | get name
    | where {|repo| $repo | path join .git | path exists }
    | sort
  }
  if not $fetch { print --stderr "Cached refs · --fetch to refresh" }
  let color = match $env.config.use_ansi_coloring {
    true | "true" => true
    false | "false" => false
    _ => (is-terminal --stdout)
  }
  let rows = ($repos | each {|repo|
    let name = ($repo | path basename)
    let label = if $color { $"(ansi cyan_bold)($name)(ansi reset)" } else { $name }
    try {
      mut marks = []
      if $fetch {
        let result = (with-env {GIT_TERMINAL_PROMPT: "0"} { ^git -C $repo fetch --all --prune | complete })
        if $result.exit_code != 0 {
          print --stderr $"($name): ($result.stderr | str trim)"
          $marks = ($marks | append "!fetch")
        }
      }
      let status = (git-output $repo status '--porcelain')
      let changes = if $status == "" { 0 } else { $status | lines | length }
      let head = (^git -C $repo symbolic-ref --quiet HEAD | complete)
      let current = ($head.stdout | str trim | str replace --regex '^refs/heads/' '')
      let branch = if $current == "" { "HEAD" } else { $current }
      if $head.exit_code != 0 {
        return ""
      } else {
        let commit = (^git -C $repo rev-parse --verify HEAD | complete)
        if $commit.exit_code != 0 {
          $marks = ($marks | append "no commits yet")
        } else {
          let fields = (git-output $repo for-each-ref '--format=%(upstream)%09%(upstream:remotename)' $"refs/heads/($current)" | split row (char tab))
          let upstream = ($fields | get 0)
          let remote = ($fields | get 1)
          if $upstream == "" {
            $marks = ($marks | append "?upstream")
          } else {
            let counts = (^git -C $repo rev-list --left-right --count $"HEAD...($upstream)" -- | complete)
            if $counts.exit_code != 0 {
              $marks = ($marks | append "!upstream")
            } else {
              let numbers = ($counts.stdout | split row --regex '\s+' | where {|n| $n != "" } | into int)
              let ahead = ($numbers | get 0)
              let behind = ($numbers | get 1)
              if $ahead > 0 { $marks = ($marks | append $"↑($ahead)") }
              if $behind > 0 { $marks = ($marks | append $"↓($behind)") }
            }
            if $remote == "." { $marks = ($marks | append "↔local") }
          }
        }
      }
      if $changes > 0 { $marks = ($marks | append $"±($changes)") }
      if ($marks | is-empty) { return "" }
      $"($label)  ($branch)  ($marks | str join ' ')"
    } catch {|err|
      print --stderr $"($name): ($err.msg)"
      $"($label)  !git"
    }
  } | where {|line| $line != "" })
  if ($rows | is-empty) { return $"✓  ($repos | length) repos" }
  # Plain text avoids Nushell's table column/row elision; long lines simply wrap.
  $rows | str join "\n"
}
