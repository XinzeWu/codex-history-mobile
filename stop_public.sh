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
SERVER_PID="${SERVER_PID:-${RUN_DIR}/server.pid}"
TUNNEL_PID="${TUNNEL_PID:-${RUN_DIR}/tunnel.pid}"

stop_pid_file() {
    local pid_file="$1"
    local name="$2"
    if [ -s "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file")"
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
            echo "Stopped $name: $pid"
        fi
        rm -f "$pid_file"
    fi
}

stop_pid_file "$SERVER_PID" server
stop_pid_file "$TUNNEL_PID" tunnel

# Compatibility with launches from older script versions.
stop_pid_file server.pid legacy-server
stop_pid_file tunnel.pid legacy-tunnel

systemctl --user stop codex-mobile-server.service 2>/dev/null || true
systemctl --user stop codex-mobile-tunnel.service 2>/dev/null || true

# Clean up older manual launches that did not write pid files.
pkill -f "python3 server.py --host 0.0.0.0 --port 8787" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:8787" 2>/dev/null || true
