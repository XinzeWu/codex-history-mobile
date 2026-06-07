#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

show_pid() {
    local pid_file="$1"
    local name="$2"
    if [ -s "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "$name: running pid $(cat "$pid_file")"
    else
        echo "$name: not running"
    fi
}

TOKEN=""
if [ -s token.txt ]; then
    TOKEN="$(tr -d '\n' < token.txt)"
fi

if systemctl --user is-active --quiet codex-mobile-server.service 2>/dev/null; then
    PID="$(systemctl --user show -p MainPID --value codex-mobile-server.service)"
    echo "server: running via systemd pid $PID"
else
    show_pid server.pid server
fi

if systemctl --user is-active --quiet codex-mobile-tunnel.service 2>/dev/null; then
    PID="$(systemctl --user show -p MainPID --value codex-mobile-tunnel.service)"
    echo "tunnel: running via systemd pid $PID"
    URL="$(journalctl --user -u codex-mobile-tunnel.service --no-pager -n 120 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
    if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
        echo "url: ${URL}/?token=${TOKEN}"
    elif [ -n "$URL" ]; then
        echo "url: ${URL}/?token=<token.txt not created yet>"
    fi
else
    show_pid tunnel.pid tunnel
fi

URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' tunnel.log 2>/dev/null | tail -n 1 || true)"
if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
    echo "legacy url: ${URL}/?token=${TOKEN}"
elif [ -n "$URL" ]; then
    echo "legacy url: ${URL}/?token=<token.txt not created yet>"
fi
