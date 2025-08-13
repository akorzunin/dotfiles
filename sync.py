#!/usr/bin/env python3
"""
sync.py – tiny dot-files helper

Usage (always run from the repo root):
    ./sync.py get  <path>   # copy ~/.path → ./dot_path
    ./sync.py put  <path>   # copy ./dot_path → ~/.path  (with conflict handling)
    ./sync.py link <path>   # ln -s  ./dot_path ~/.path
"""

import os
import shutil
import sys
from pathlib import Path

# -----------------------------------------------------------
# Helpers
# -----------------------------------------------------------
REPO_ROOT = Path.cwd().resolve()
HOME      = Path.home()

def dot_path(relative: str) -> Path:
    """Return repo path ./dot_<sanitized_path>."""
    safe = relative.replace(".", "dot_", 1)
    return REPO_ROOT / safe

def home_path(relative: str) -> Path:
    """Return ~/<relative>."""
    return HOME / relative

def confirm(prompt: str) -> bool:
    return input(prompt).strip().lower() in {"y", "yes"}

def copy_with_merge(src: Path, dst: Path):
    """Copy file or directory tree, overwriting existing files."""
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def prompt_conflict(home_file: Path) -> str:
    """Ask user how to resolve a conflict."""
    print(f"\nConflict detected: {home_file}")
    while True:
        choice = input("Choose action:\n"
                       "  1) overwrite\n"
                       "  2) backup current file\n"
                       "  3) abort\n> ").strip()
        if choice in {"1", "2", "3"}:
            return choice
        print("Invalid choice.")

def backup_file(path: Path) -> None:
    """Rename path to path.bak.<n>"""
    counter = 1
    while True:
        bak = path.with_suffix(path.suffix + f".bak.{counter}")
        if not bak.exists():
            path.rename(bak)
            print(f"Backed up {path} → {bak}")
            return
        counter += 1

# -----------------------------------------------------------
# Commands
# -----------------------------------------------------------
def cmd_get(relative: str):
    src = home_path(relative)
    dst = dot_path(relative)
    if not src.exists():
        print(f"Source does not exist: {src}")
        sys.exit(1)
    print(f"Copying {src} → {dst}")
    if dst.exists() and not confirm("Destination already exists, overwrite? [y/N] "):
        print("Aborted.")
        sys.exit(1)
    if dst.is_dir() and not dst.is_symlink():
        shutil.rmtree(dst)
    copy_with_merge(src, dst)

def cmd_put(relative: str):
    src = dot_path(relative)
    dst = home_path(relative)
    if not src.exists():
        print(f"Source does not exist: {src}")
        sys.exit(1)

    conflicts = list(find_conflicts(src, dst))
    if conflicts:
        print(f"{len(conflicts)} conflicting file(s) detected.")
        for _, home_file in conflicts:
            choice = prompt_conflict(home_file)
            if choice == "1":
                pass  # overwrite will happen below
            elif choice == "2":
                backup_file(home_file)
            elif choice == "3":
                print("Aborted by user.")
                sys.exit(1)

    print(f"Copying {src} → {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    copy_with_merge(src, dst)

def find_conflicts(src: Path, dst: Path):
    """Yield (src_file, dst_file) pairs that differ."""
    if src.is_file():
        if dst.exists() and not dst.is_symlink():
            if not files_equal(src, dst):
                yield src, dst
    elif src.is_dir():
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                target = dst / rel
                if target.exists() and not target.is_symlink():
                    if not files_equal(item, target):
                        yield item, target

def files_equal(a: Path, b: Path) -> bool:
    """Naïve byte-wise comparison."""
    if not b.exists():
        return False
    return a.read_bytes() == b.read_bytes()

def cmd_link(relative: str):
    repo_dir = dot_path(relative)
    home_dir = home_path(relative)
    if not repo_dir.exists():
        print(f"Source directory does not exist: {repo_dir}")
        sys.exit(1)
    if home_dir.exists() or home_dir.is_symlink():
        if not confirm(f"{home_dir} already exists. Replace with symlink? [y/N] "):
            print("Aborted.")
            sys.exit(1)
        if home_dir.is_dir() and not home_dir.is_symlink():
            shutil.rmtree(home_dir)
        else:
            home_dir.unlink()
    home_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"Symlinking {home_dir} → {repo_dir}")
    home_dir.symlink_to(repo_dir)

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
def main():
    if os.geteuid() == 0:
        print("Do not run this script as root.", file=sys.stderr)
        sys.exit(1)

    # Ensure we are in the repo root
    if not (REPO_ROOT / ".git").exists():
        print("Run this script from the root of your dot-files git repository.", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd, path_arg = sys.argv[1], sys.argv[2]

    # Normalize path: remove leading "./" and trailing slashes
    path_arg = path_arg.lstrip().rstrip("/")

    if cmd == "get":
        cmd_get(path_arg)
    elif cmd == "put":
        cmd_put(path_arg)
    elif cmd == "link":
        cmd_link(path_arg)
    else:
        print("Unknown command:", cmd)
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
