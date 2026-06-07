#!/usr/bin/env bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

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
