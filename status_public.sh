#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${CODEX_MOBILE_RELEASE_DIR:-$HOME/codex-mobile-release}"
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
else
    cd "$SCRIPT_DIR"
fi

RUN_SOURCE="${RUN_SOURCE:-manual}"
RUN_SOURCE="${RUN_SOURCE//[^A-Za-z0-9_.-]/_}"
RUN_DIR="${RUN_DIR:-run/${RUN_SOURCE}}"
LOG_DIR="${LOG_DIR:-logs/${RUN_SOURCE}}"
SERVER_PID="${SERVER_PID:-${RUN_DIR}/server.pid}"
TUNNEL_PID="${TUNNEL_PID:-${RUN_DIR}/tunnel.pid}"
TUNNEL_LOG="${TUNNEL_LOG:-${LOG_DIR}/tunnel.log}"

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

if [ -s "$SERVER_PID" ] && kill -0 "$(cat "$SERVER_PID")" 2>/dev/null; then
    show_pid "$SERVER_PID" server
elif systemctl --user is-active --quiet codex-mobile-server.service 2>/dev/null; then
    PID="$(systemctl --user show -p MainPID --value codex-mobile-server.service)"
    echo "server: running via systemd pid $PID"
else
    show_pid "$SERVER_PID" server
fi

if [ -s "$TUNNEL_PID" ] && kill -0 "$(cat "$TUNNEL_PID")" 2>/dev/null; then
    show_pid "$TUNNEL_PID" tunnel
elif systemctl --user is-active --quiet codex-mobile-tunnel.service 2>/dev/null; then
    PID="$(systemctl --user show -p MainPID --value codex-mobile-tunnel.service)"
    echo "tunnel: running via systemd pid $PID"
    URL="$(journalctl --user -u codex-mobile-tunnel.service --no-pager -n 120 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
    if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
        echo "url: ${URL}/?token=${TOKEN}"
    elif [ -n "$URL" ]; then
        echo "url: ${URL}/?token=<token.txt not created yet>"
    fi
else
    show_pid "$TUNNEL_PID" tunnel
fi

URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -n 1 || true)"
if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
    echo "url from ${TUNNEL_LOG}: ${URL}/?token=${TOKEN}"
elif [ -n "$URL" ]; then
    echo "url from ${TUNNEL_LOG}: ${URL}/?token=<token.txt not created yet>"
fi

LEGACY_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' tunnel.log 2>/dev/null | tail -n 1 || true)"
if [ -n "$LEGACY_URL" ] && [ "$TUNNEL_LOG" != "tunnel.log" ]; then
    if [ -n "$TOKEN" ]; then
        echo "legacy url: ${LEGACY_URL}/?token=${TOKEN}"
    else
        echo "legacy url: ${LEGACY_URL}/?token=<token.txt not created yet>"
    fi
fi
