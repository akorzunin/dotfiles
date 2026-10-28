#!/bin/sh
# Explicit, opt-in system installation; not part of the general dotfiles updater.
set -eu
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run as your normal user; only installation steps use sudo.' >&2
    exit 1
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
commit=c4d0b1990129dce2b28095277173ee0d7702d304
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT

git -C "$build" init -q
git -C "$build" remote add origin https://github.com/bol-van/zapret.git
git -C "$build" fetch --depth 1 origin "$commit"
git -C "$build" checkout --detach FETCH_HEAD
[ "$(git -C "$build" rev-parse HEAD)" = "$commit" ]
make -C "$build/nfq" systemd
make -C "$build/tpws"
make -C "$build/mdig"
make -C "$build/ip2net"
rm -rf "$build/.git"

# Stop before replacing a running executable. Preserve unrelated network services.
if systemctl cat zapret.service >/dev/null 2>&1; then
    sudo systemctl stop zapret.service
fi
sudo install -d -m 755 /opt/zapret /etc/systemd/system/zapret.service.d
sudo cp -a "$build/." /opt/zapret/
sudo chown -R root:root /opt/zapret
sudo chmod -R go-w /opt/zapret
sudo install -m 644 "$here/config" "$here/hosts-discord.txt" "$here/hosts-youtube.txt" /opt/zapret/
sudo install -m 644 "$here/README.md" /opt/zapret/README.local.md
sudo install -m 644 /opt/zapret/init.d/systemd/zapret.service /etc/systemd/system/zapret.service
sudo install -m 644 "$here/sing-box.conf" /etc/systemd/system/zapret.service.d/sing-box.conf
sudo systemctl daemon-reload
sudo systemctl enable --now zapret.service
sudo systemctl --no-pager status zapret.service

echo 'Zapret installed. See etc/zapret/README.md for sing-box and Vesktop settings.'
