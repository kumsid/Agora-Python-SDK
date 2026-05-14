#!/usr/bin/env bash
# Recreate .venv with a Python that can run under `arch -x86_64` (universal2),
# then run setup_native_sdk.py. Fixes: "Bad CPU type in executable" on Apple Silicon
# when .venv was created from an arm64-only Homebrew Python.
#
# Usage (from repo root):
#   ./scripts/fix_apple_silicon_venv.sh
#   ./scripts/fix_apple_silicon_venv.sh --force   # any args are forwarded to setup_native_sdk.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]] || [[ "$(uname -m)" != "arm64" ]]; then
  echo "This script only applies to macOS on Apple Silicon (arm64). Nothing to do."
  exit 0
fi

if [[ -x "${ROOT}/.venv/bin/python" ]] && arch -x86_64 "${ROOT}/.venv/bin/python" -c "pass" 2>/dev/null; then
  echo "OK: ${ROOT}/.venv/bin/python already runs under arch -x86_64."
  exit 0
fi

arch -x86_64 /usr/bin/true 2>/dev/null || {
  echo "Rosetta does not seem to work (arch -x86_64 /usr/bin/true failed)." >&2
  echo "Install Rosetta, then retry:" >&2
  echo "  softwareupdate --install-rosetta" >&2
  exit 1
}

pick_base_python() {
  local py minor
  for minor in $(seq 14 -1 8); do
    py="/Library/Frameworks/Python.framework/Versions/3.${minor}/bin/python3"
    if [[ -x "$py" ]] && arch -x86_64 "$py" -c "pass" 2>/dev/null; then
      echo "$py"
      return 0
    fi
  done
  py="/usr/bin/python3"
  if [[ -x "$py" ]] && arch -x86_64 "$py" -c "pass" 2>/dev/null; then
    echo "$py"
    return 0
  fi
  return 1
}

BASE_PY="$(pick_base_python)" || {
  echo "No usable universal2 (x86_64-capable) Python found." >&2
  echo "Install the macOS 64-bit universal2 build from https://www.python.org/downloads/macos/" >&2
  echo "Then run this script again." >&2
  exit 1
}

echo "Using base interpreter: ${BASE_PY}"
"$BASE_PY" -c "import sys; print('Python', sys.version.split()[0])"

echo "Removing old .venv (if any)…"
rm -rf "${ROOT}/.venv"

echo "Running setup_native_sdk.py (creates .venv and builds extension)…"
exec "$BASE_PY" "${ROOT}/scripts/setup_native_sdk.py" "$@"
