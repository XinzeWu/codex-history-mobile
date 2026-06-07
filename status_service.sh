#!/usr/bin/env bash
set -euo pipefail

systemctl --user --no-pager status codex-mobile-server.service || true
echo
systemctl --user --no-pager is-enabled codex-mobile-tunnel.service 2>/dev/null | sed 's/^/tunnel service: /' || true
systemctl --user --no-pager is-active codex-mobile-tunnel.service 2>/dev/null | sed 's/^/tunnel active: /' || true
echo
loginctl show-user "$USER" -p Linger -p State 2>/dev/null || true
echo
"$(cd "$(dirname "$0")" && pwd)/status_public.sh"
