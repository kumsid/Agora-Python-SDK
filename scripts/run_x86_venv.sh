#!/usr/bin/env bash
# Run repo .venv Python under Rosetta (x86_64). Use on Apple Silicon with the
# Intel-only Agora v3.1.2 Mac SDK. Requires a universal2 (or x86_64) venv Python;
# see scripts/setup_native_sdk.py and docs/SETUP_CROSS_PLATFORM.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing ${PY} — create it with: python3 scripts/setup_native_sdk.py" >&2
  exit 1
fi
exec arch -x86_64 "$PY" "$@"
