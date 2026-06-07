#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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

stop_pid_file server.pid server
stop_pid_file tunnel.pid tunnel

systemctl --user stop codex-mobile-server.service 2>/dev/null || true
systemctl --user stop codex-mobile-tunnel.service 2>/dev/null || true

# Clean up older manual launches that did not write pid files.
pkill -f "python3 server.py --host 0.0.0.0 --port 8787" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:8787" 2>/dev/null || true
