#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${CODEX_MOBILE_RELEASE_DIR:-$HOME/codex-mobile-release}"
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR"
else
  cd "$SCRIPT_DIR"
fi
exec python3 server.py --host "${HOST:-0.0.0.0}" --port "${PORT:-8787}"
