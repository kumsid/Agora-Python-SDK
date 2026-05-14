#!/usr/bin/env sh
# Cross-platform helper on Unix: runs the Python setup driver.
set -eu
cd "$(dirname "$0")"
exec python3 scripts/setup_native_sdk.py "$@"
