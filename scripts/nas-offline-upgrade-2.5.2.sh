#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
EXPECTED_VERSION=2.5.2
export EXPECTED_VERSION

exec "$SCRIPT_DIR/nas-offline-upgrade-2.5.1.sh" "$@"
