#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${CODEX_MOBILE_RELEASE_DIR:-$HOME/codex-mobile-release}"
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
else
    cd "$SCRIPT_DIR"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8787}"
RUN_SOURCE="${RUN_SOURCE:-manual}"
RUN_SOURCE="${RUN_SOURCE//[^A-Za-z0-9_.-]/_}"
RUN_DIR="${RUN_DIR:-run/${RUN_SOURCE}}"
LOG_DIR="${LOG_DIR:-logs/${RUN_SOURCE}}"
SERVER_LOG="${SERVER_LOG:-${LOG_DIR}/server.log}"
TUNNEL_LOG="${TUNNEL_LOG:-${LOG_DIR}/tunnel.log}"
SERVER_PID="${SERVER_PID:-${RUN_DIR}/server.pid}"
TUNNEL_PID="${TUNNEL_PID:-${RUN_DIR}/tunnel.pid}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-./bin/cloudflared}"
CODEX_BIN="${CODEX_BIN:-$(command -v codex 2>/dev/null || true)}"
export CODEX_BIN

mkdir -p "$RUN_DIR" "$LOG_DIR"

is_running() {
    local pid_file="$1"
    [ -s "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

server_running() {
    is_running "$SERVER_PID" && return 0
    pgrep -f "python3 server.py --host ${HOST} --port ${PORT}" >/dev/null 2>&1
}

start_server() {
    if server_running; then
        return
    fi
    rm -f "$SERVER_PID"
    {
        printf '\n[%s] starting server source=%s host=%s port=%s\n' "$(date -Is)" "$RUN_SOURCE" "$HOST" "$PORT"
    } >> "$SERVER_LOG"
    setsid nohup ./start.sh >> "$SERVER_LOG" 2>&1 &
    echo "$!" > "$SERVER_PID"
}

start_tunnel() {
    if is_running "$TUNNEL_PID"; then
        return
    fi
    if [ ! -x "$CLOUDFLARED_BIN" ]; then
        if command -v cloudflared >/dev/null 2>&1; then
            CLOUDFLARED_BIN="$(command -v cloudflared)"
        else
            echo "cloudflared not found. Put it at ./bin/cloudflared or set CLOUDFLARED_BIN=/path/to/cloudflared" >&2
            exit 1
        fi
    fi
    rm -f "$TUNNEL_PID"
    {
        printf '\n[%s] starting tunnel source=%s url=http://127.0.0.1:%s\n' "$(date -Is)" "$RUN_SOURCE" "$PORT"
    } >> "$TUNNEL_LOG"
    setsid nohup "$CLOUDFLARED_BIN" tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate >> "$TUNNEL_LOG" 2>&1 &
    echo "$!" > "$TUNNEL_PID"
}

start_server
sleep 1
TOKEN=""
if [ -s token.txt ]; then
    TOKEN="$(tr -d '\n' < token.txt)"
fi
start_tunnel

if [ -s "$SERVER_PID" ]; then echo "Server PID: $(cat "$SERVER_PID")"; fi
if [ -s "$TUNNEL_PID" ]; then echo "Tunnel PID: $(cat "$TUNNEL_PID")"; fi
echo "Waiting for Cloudflare URL..."

if systemctl --user is-active --quiet codex-mobile-tunnel.service 2>/dev/null; then
    URL="$(journalctl --user -u codex-mobile-tunnel.service --no-pager -n 120 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
    if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
        echo "${URL}/?token=${TOKEN}"
        exit 0
    fi
fi

for _ in $(seq 1 90); do
    URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n 1 || true)"
    if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
        echo "${URL}/?token=${TOKEN}"
        exit 0
    fi
    sleep 1
done

echo "No tunnel URL yet. Check logs:"
echo "  $(pwd)/$SERVER_LOG"
echo "  $(pwd)/$TUNNEL_LOG"
exit 1
