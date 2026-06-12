#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="${CODEX_MOBILE_RELEASE_DIR:-$HOME/codex-mobile-release}"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

if [ "$SOURCE_DIR" != "$BASE" ]; then
  mkdir -p "$BASE"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '.git/' \
      --exclude '__pycache__/' \
      --exclude 'token.txt' \
      --exclude 'job_outputs/' \
      --exclude 'logs/' \
      --exclude 'run/' \
      --exclude '*.log' \
      --exclude '*.pid' \
      "$SOURCE_DIR/" "$BASE/"
  else
    cp -a "$SOURCE_DIR/." "$BASE/"
  fi
  rm -rf "$BASE/.git" "$BASE/__pycache__" "$BASE/job_outputs" "$BASE/logs" "$BASE/run"
  rm -f "$BASE/token.txt" "$BASE"/*.log "$BASE"/*.pid
fi

sed "s#__PROJECT_DIR__#${BASE}#g" "$BASE/systemd/codex-mobile-server.service.in" > "$USER_SYSTEMD_DIR/codex-mobile-server.service"

systemctl --user daemon-reload
systemctl --user enable --now codex-mobile-server.service

if [ -x "$BASE/bin/cloudflared" ]; then
  sed "s#__PROJECT_DIR__#${BASE}#g" "$BASE/systemd/codex-mobile-tunnel.service.in" > "$USER_SYSTEMD_DIR/codex-mobile-tunnel.service"
  systemctl --user daemon-reload
  systemctl --user enable --now codex-mobile-tunnel.service
else
  echo "cloudflared is not installed at $BASE/bin/cloudflared"
  echo "Server service was installed. Install cloudflared before enabling the tunnel service."
fi

if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$USER" 2>/dev/null || true
fi

"$BASE/status_public.sh"
