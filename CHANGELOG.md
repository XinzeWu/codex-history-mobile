# Changelog

## 0.2.0-mobile-ui

Mobile UI and release hardening update.

- Adds automatic Codex CLI discovery across common install locations, including nvm-managed Node installs.
- Adds copy buttons for session resume commands, user messages, assistant replies, and job output.
- Adds mobile session title editing with browser-local persistence and best-effort write-back to Codex state.
- Adds swipe-to-hide sessions without deleting local Codex files.
- Adds a collapsible hidden-session section with per-session restore controls.
- Improves the session drawer with a wider, resizable desktop sidebar and full-width mobile drawer.
- Improves session card layout with stable spacing, line clamping, and reduced overlap risk.
- Adds Markdown rendering for messages, including fenced code blocks, lists, links, blockquotes, and tables.
- Keeps runtime artifacts out of the release package: `token.txt`, job outputs, logs, pids, and bytecode caches.

## 0.1.1-cli-vscode-compatible

Documentation and version-label update.

- Clarifies that this edition is compatible with both Codex CLI and VS Code/Codex session history.
- States explicitly that execution still uses `codex exec resume`.
- States explicitly that VS Code compatibility means current-session detection and shared-history visibility, not a packaged VS Code extension.

## 0.1.0-cli

Initial CLI shared-history edition.

- Mobile web UI for browsing Codex sessions.
- Sends phone input through `codex exec resume`.
- Reads session metadata from `~/.codex/state_5.sqlite`.
- Reads transcript messages from Codex rollout JSONL files.
- Optional current-session detection through Codex app-server remote-control.
- Optional Cloudflare quick tunnel.
- Optional user-level systemd services.
- Full-permission CLI execution mode documented in `SECURITY.md`.
