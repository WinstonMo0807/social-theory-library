#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
EXPECTED_VERSION=2.5.3
export EXPECTED_VERSION

# Invoke the implementation through sh so a helper script that loses its
# executable bit during archive extraction cannot stop the upgrade.
exec sh "$SCRIPT_DIR/nas-offline-upgrade-2.5.1.sh" "$@"
