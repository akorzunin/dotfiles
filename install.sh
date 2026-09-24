#!/bin/sh
# Run from anywhere; the Nushell bootstrap handles dependencies and links.
set -eu
cd "$(dirname "$0")"
exec nu --no-config-file update.nu
