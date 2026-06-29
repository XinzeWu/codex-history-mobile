#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import struct
import subprocess
import threading
import time
import urllib.parse
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOME = Path.home()
CODEX_HOME = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
STATE_DB = CODEX_HOME / "state_5.sqlite"
TOKEN_FILE = Path(__file__).with_name("token.txt")
APP_VERSION = "0.1.1-cli-vscode-compatible"
DEFAULT_CODEX_BIN = HOME / ".local" / "bin" / "codex"


def find_codex_bin():
    env_bin = os.environ.get("CODEX_BIN")
    if env_bin:
        return env_bin
    candidates = [
        DEFAULT_CODEX_BIN,
        HOME / ".nvm" / "current" / "bin" / "codex",
        HOME / ".local" / "share" / "npm" / "bin" / "codex",
        HOME / ".npm-global" / "bin" / "codex",
        HOME / ".bun" / "bin" / "codex",
        Path("/usr/local/bin/codex"),
        Path("/opt/homebrew/bin/codex"),
    ]
    nvm_versions = HOME / ".nvm" / "versions" / "node"
    if nvm_versions.exists():
        candidates.extend(
            sorted(
                nvm_versions.glob("*/bin/codex"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )
        )
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    path_bin = shutil.which("codex")
    return path_bin or "codex"


CODEX_BIN = find_codex_bin()
APP_SERVER_SOCK = CODEX_HOME / "app-server-control" / "app-server-control.sock"
JOB_OUTPUT_DIR = Path(__file__).with_name("job_outputs")
JOBS = {}
JOBS_LOCK = threading.Lock()
INPUTBOX_QUEUE = []
INPUTBOX_LOCK = threading.Lock()
FILE_ROOTS = [HOME, Path("/nfs")]
BLOCKED_FILE_NAMES = {".env", ".git-credentials", "token.txt"}
BLOCKED_FILE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
BLOCKED_FILE_PARTS = {".ssh", ".gnupg"}
TEXT_PREVIEW_SUFFIXES = {
    ".txt", ".md", ".json", ".jsonl", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".log", ".csv", ".sql", ".xml",
}
IMAGE_PREVIEW_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_TEXT_PREVIEW_BYTES = 1024 * 1024


def codex_env():
    env = os.environ.copy()
    codex_dir = str(Path(CODEX_BIN).expanduser().parent)
    current_path = env.get("PATH", "")
    env["PATH"] = codex_dir + (os.pathsep + current_path if current_path else "")
    env["CODEX_BIN"] = CODEX_BIN
    return env


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>Codex Mobile</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1d232d;
      --muted: #667085;
      --line: #d8dee8;
      --accent: #0f766e;
      --accent-2: #1f2937;
      --user: #dff5ee;
      --assistant: #ffffff;
      --danger: #b42318;
      --sidebar-bg: #eef1f5;
      --button-bg: #ffffff;
      --active-bg: #ffffff;
      --active-border: #94bdb8;
      --soft-bg: #edfdfa;
      --soft-text: #115e59;
      --code-bg: #eef1f5;
      --pre-bg: #111827;
      --pre-text: #e5e7eb;
      --quote-text: #475467;
      --table-bg: #ffffff;
      --job-bg: #fff7ed;
      --job-border: #fed7aa;
      --failed-bg: #fff1f2;
      --failed-border: #fecdd3;
      --terminal-bg: #111827;
      --terminal-text: #d1fae5;
      --header-bg: rgba(255,255,255,.78);
      --link: #0f766e;
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg: #111318;
      --panel: #181b22;
      --text: #e6e8ee;
      --muted: #9aa3b2;
      --line: #303642;
      --accent: #14b8a6;
      --accent-2: #d5dae3;
      --user: #113d37;
      --assistant: #1b2028;
      --danger: #fca5a5;
      --sidebar-bg: #151922;
      --button-bg: #202631;
      --active-bg: #202631;
      --active-border: #2dd4bf;
      --soft-bg: #123d38;
      --soft-text: #99f6e4;
      --code-bg: #242b36;
      --pre-bg: #090b10;
      --pre-text: #e6e8ee;
      --quote-text: #c1c7d0;
      --table-bg: #181d26;
      --job-bg: #322215;
      --job-border: #7c4a16;
      --failed-bg: #371b24;
      --failed-border: #7f1d1d;
      --terminal-bg: #090b10;
      --terminal-text: #99f6e4;
      --header-bg: rgba(24,27,34,.86);
      --link: #5eead4;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      height: 100vh;
      height: 100dvh;
      overflow: hidden;
    }
    .app {
      display: grid;
      grid-template-columns: minmax(520px, var(--sidebar-width, 44vw)) minmax(0, 1fr);
      height: 100vh;
      height: 100dvh;
      min-height: 0;
    }
    aside {
      background: var(--sidebar-bg);
      border-right: 1px solid var(--line);
      min-height: 0;
      min-width: 0;
      display: flex;
      flex-direction: column;
      position: relative;
    }
    .sidebar-resizer {
      position: absolute;
      top: 0;
      right: -4px;
      width: 8px;
      height: 100%;
      cursor: col-resize;
      z-index: 2;
    }
    header {
      height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 14px;
      border-bottom: 1px solid var(--line);
      background: var(--header-bg);
      backdrop-filter: blur(10px);
    }
    h1 {
      font-size: 16px;
      line-height: 1.2;
      margin: 0;
      font-weight: 700;
    }
    .status {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .side-head {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .side-refresh {
      width: 28px;
      height: 28px;
      border-radius: 7px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      color: var(--accent-2);
      font-size: 14px;
      display: inline-grid;
      place-items: center;
      padding: 0;
      appearance: none;
    }
    .sessions {
      overflow: auto;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-width: 0;
    }
    .session {
      width: 100%;
      min-height: 132px;
      border: 1px solid transparent;
      border-radius: 8px;
      background: transparent;
      text-align: left;
      padding: 14px 46px 14px 14px;
      color: var(--text);
      display: block;
      position: relative;
      cursor: pointer;
      overflow: visible;
      touch-action: pan-y;
    }
    .session.hiding {
      opacity: .35;
      transform: translateX(-28px);
      transition: opacity .16s ease, transform .16s ease;
    }
    .session.active {
      border-color: var(--active-border);
      background: var(--active-bg);
    }
    .session .title {
      font-size: 15px;
      line-height: 1.5;
      font-weight: 650;
      overflow-wrap: anywhere;
      word-break: break-word;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .session .meta {
      font-size: 12px;
      color: var(--muted);
      overflow-wrap: anywhere;
      word-break: break-word;
      line-height: 1.5;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .session .time {
      -webkit-line-clamp: 1;
    }
    .session-main {
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-width: 0;
    }
    .session-actions {
      display: grid;
      gap: 4px;
      position: absolute;
      top: 10px;
      right: 10px;
      width: 24px;
    }
    .session-action {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      color: var(--accent-2);
      font-size: 12px;
      line-height: 1;
      padding: 0;
      display: inline-grid;
      place-items: center;
      appearance: none;
    }
    .session-action.done {
      border-color: var(--active-border);
      background: var(--soft-bg);
      color: var(--soft-text);
    }
    .session-group {
      width: 100%;
      margin-top: 20px;
      padding: 10px 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--button-bg);
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
      text-align: left;
      appearance: none;
    }
    .session.hidden-card {
      opacity: .72;
      background: var(--panel);
      border-style: dashed;
    }
    .file-entry {
      min-height: 58px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      border-radius: 8px;
      padding: 10px 12px;
      color: var(--text);
      cursor: pointer;
    }
    .file-entry.active {
      border-color: var(--active-border);
      background: var(--active-bg);
    }
    .file-browser {
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 14px;
      display: none;
      flex-direction: column;
      gap: 10px;
    }
    .file-browser.open { display: flex; }
    .file-bar {
      display: flex;
      gap: 8px;
      align-items: center;
      min-width: 0;
      flex-wrap: wrap;
    }
    .file-path {
      flex: 1 0 100%;
      order: 2;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--button-bg);
      color: var(--text);
      padding: 9px 10px;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      outline: 0;
    }
    .file-btn {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--button-bg);
      color: var(--accent-2);
      font-weight: 650;
      padding: 0 10px;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .file-layout {
      display: grid;
      grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
      gap: 10px;
      min-height: 0;
      flex: 1;
    }
    .file-list,
    .file-preview {
      min-height: 0;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .file-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
    }
    .file-row:last-child { border-bottom: 0; }
    .file-row.active { background: var(--active-bg); }
    .file-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 650;
    }
    .file-meta {
      color: var(--muted);
      font-size: 11px;
      margin-top: 4px;
    }
    .file-preview {
      padding: 12px;
    }
    .file-preview pre {
      margin: 0;
      white-space: pre;
      overflow: auto;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .file-preview img {
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      border: 1px solid var(--line);
    }
    main {
      min-width: 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .toolbar {
      height: 58px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .mobile-menu {
      display: none;
      width: 38px;
      height: 38px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      font-size: 20px;
    }
    .thread-title {
      min-width: 0;
      flex: 1;
      font-size: 14px;
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .refresh {
      height: 38px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      border-radius: 8px;
      padding: 0 12px;
      color: var(--accent-2);
      font-weight: 650;
    }
    .theme-toggle {
      width: 38px;
      height: 38px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      border-radius: 8px;
      color: var(--accent-2);
      font-size: 16px;
      line-height: 1;
      display: inline-grid;
      place-items: center;
      padding: 0;
      appearance: none;
    }
    .mode {
      height: 38px;
      border: 1px solid var(--active-border);
      border-color: var(--active-border);
      background: var(--soft-bg);
      border-radius: 8px;
      padding: 0 12px;
      color: var(--soft-text);
      font-weight: 750;
    }
    .messages {
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .msg {
      max-width: min(780px, 92%);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 40px 10px 12px;
      background: var(--assistant);
      overflow-wrap: anywhere;
      line-height: 1.45;
      font-size: 14px;
      position: relative;
    }
    .msg.user {
      align-self: flex-end;
      background: var(--user);
      border-color: var(--active-border);
    }
    .msg.job {
      align-self: flex-end;
      background: var(--job-bg);
      border-color: var(--job-border);
    }
    .msg.job.failed {
      background: var(--failed-bg);
      border-color: var(--failed-border);
    }
    .msg .content {
      display: block;
      white-space: normal;
    }
    .content p {
      margin: 0 0 9px;
    }
    .content p:last-child,
    .content pre:last-child,
    .content ul:last-child,
    .content ol:last-child,
    .content blockquote:last-child {
      margin-bottom: 0;
    }
    .content h1,
    .content h2,
    .content h3 {
      margin: 12px 0 8px;
      line-height: 1.25;
    }
    .content h1 { font-size: 20px; }
    .content h2 { font-size: 17px; }
    .content h3 { font-size: 15px; }
    .content pre {
      margin: 8px 0;
      padding: 10px;
      border-radius: 8px;
      background: var(--pre-bg);
      color: var(--pre-text);
      overflow: auto;
      white-space: pre;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .content code {
      border-radius: 5px;
      background: var(--code-bg);
      padding: 1px 5px;
      font: .92em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .content pre code {
      background: transparent;
      padding: 0;
      font: inherit;
    }
    .content ul,
    .content ol {
      margin: 7px 0 10px;
      padding-left: 22px;
    }
    .content li { margin: 3px 0; }
    .content blockquote {
      margin: 8px 0;
      padding: 2px 0 2px 10px;
      border-left: 3px solid var(--active-border);
      color: var(--quote-text);
    }
    .content a {
      color: var(--link);
      text-decoration: underline;
      overflow-wrap: anywhere;
    }
    .content .table-wrap {
      max-width: 100%;
      overflow-x: auto;
      margin: 8px 0 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--table-bg);
    }
    .content table {
      width: 100%;
      min-width: 420px;
      border-collapse: collapse;
      font-size: 13px;
      white-space: normal;
    }
    .content th,
    .content td {
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 7px 9px;
      text-align: left;
      vertical-align: top;
    }
    .content th:last-child,
    .content td:last-child {
      border-right: 0;
    }
    .content tr:last-child td {
      border-bottom: 0;
    }
    .content th {
      background: var(--code-bg);
      font-weight: 750;
    }
    .msg .role {
      display: block;
      font-size: 11px;
      color: var(--muted);
      margin-bottom: 5px;
      font-weight: 700;
    }
    .msg-copy {
      position: absolute;
      top: 8px;
      right: 8px;
      width: 24px;
      height: 24px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: var(--button-bg);
      color: var(--accent-2);
      font-size: 12px;
      line-height: 1;
      padding: 0;
      display: inline-grid;
      place-items: center;
      appearance: none;
    }
    .msg-copy.done {
      border-color: var(--active-border);
      background: var(--soft-bg);
      color: var(--soft-text);
    }
    .composer {
      border-top: 1px solid var(--line);
      background: var(--panel);
      padding: 10px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
    }
    textarea {
      width: 100%;
      min-height: 48px;
      max-height: 160px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      font: inherit;
      line-height: 1.35;
    }
    .send {
      width: 72px;
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: #fff;
      font-weight: 800;
    }
    .send:disabled { opacity: .55; }
    .notice {
      padding: 10px 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .terminal {
      display: none;
      border-top: 1px solid var(--line);
      background: var(--terminal-bg);
      color: var(--terminal-text);
      max-height: 26vh;
      min-height: 108px;
      overflow: auto;
      padding: 10px 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .terminal.open { display: block; }
    .error { color: var(--danger); }
    @media (max-width: 760px) {
      body,
      .app {
        height: 100dvh;
        min-height: 100dvh;
      }
      .app { grid-template-columns: 1fr; }
      aside {
        position: fixed;
        inset: 0 auto 0 0;
        width: 100vw;
        z-index: 10;
        transform: translateX(-100%);
        transition: transform .18s ease;
        box-shadow: 8px 0 24px rgba(17,24,39,.18);
      }
      .sidebar-resizer { display: none; }
      aside.open { transform: translateX(0); }
      .mobile-menu { display: block; }
      .toolbar {
        flex: 0 0 58px;
        order: 0;
      }
      .composer {
        order: 1;
        flex: 0 0 auto;
        border-top: 0;
        border-bottom: 1px solid var(--line);
        padding: 8px;
        grid-template-columns: minmax(0, 1fr) 64px;
      }
      textarea {
        min-height: 44px;
        max-height: 108px;
      }
      .send { width: 64px; }
      .messages {
        order: 2;
        padding: 10px;
      }
      .file-browser { order: 2; padding: 10px; }
      .file-layout { grid-template-columns: 1fr; }
      .file-list,
      .file-preview { max-height: none; }
      .msg { max-width: 96%; }
      .terminal { order: 3; max-height: 22vh; min-height: 84px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside id="sidebar">
      <header>
        <div class="side-head">
          <h1>Codex Mobile</h1>
          <button class="side-refresh" id="sessionRefreshBtn" type="button" title="刷新目录">↻</button>
        </div>
        <span class="status" id="sessionCount">加载中</span>
      </header>
      <div class="sessions" id="sessions"></div>
      <div class="sidebar-resizer" id="sidebarResizer"></div>
    </aside>
    <main>
      <div class="toolbar">
        <button class="mobile-menu" id="menuBtn" title="会话">☰</button>
        <div class="thread-title" id="threadTitle">选择一个会话</div>
        <button class="theme-toggle" id="themeBtn" type="button" title="切换明暗主题">☾</button>
        <button class="mode" id="terminalBtn">历史</button>
        <button class="refresh" id="refreshBtn">刷新</button>
      </div>
      <div class="messages" id="messages">
        <div class="notice">选择左侧会话后，就可以在手机上查看消息并发送新指令。</div>
      </div>
      <div class="file-browser" id="fileBrowser">
        <div class="file-bar">
          <button class="file-btn" id="fileUpBtn" type="button">上级</button>
          <input class="file-path" id="filePathInput" value="/home/wxz" spellcheck="false" autocomplete="off">
          <button class="file-btn" id="fileGoBtn" type="button">打开</button>
          <button class="file-btn" id="fileCopyBtn" type="button">复制</button>
          <button class="file-btn" id="fileHiddenBtn" type="button">显示隐藏</button>
          <button class="file-btn" id="fileRefreshBtn" type="button">刷新</button>
        </div>
        <div class="file-layout">
          <div class="file-list" id="fileList"></div>
          <div class="file-preview" id="filePreview"><div class="notice">选择文件预览，或点击目录进入。</div></div>
        </div>
      </div>
      <div class="terminal" id="terminal">共享历史状态加载中</div>
      <div class="composer" id="composer">
        <textarea id="input" placeholder="输入后写入当前会话历史"></textarea>
        <button class="send" id="sendBtn">发送</button>
      </div>
    </main>
  </div>
  <script>
    const params = new URLSearchParams(location.search);
    const token = params.get("token") || localStorage.getItem("codexMobileToken") || "";
    if (token) localStorage.setItem("codexMobileToken", token);
    const savedTheme = localStorage.getItem("codexMobileTheme") || "light";
    document.documentElement.dataset.theme = savedTheme === "dark" ? "dark" : "light";
    const explicitSessionId = params.get("session_id") || "";
    let sessions = [];
    let activeId = explicitSessionId || localStorage.getItem("codexMobileSession") || "";
    let activeMode = localStorage.getItem("codexMobileMode") || "chat";
    let firstSessionLoad = true;
    let loadedThreadIds = [];
    let currentSessionId = "";
    let sending = false;
    let jobs = {};
    let remote = {};
    let terminalOpen = false;
    let stickToBottom = true;
    let forceScrollBottom = true;
    let uiEvents = [];
    let lastRenderedItems = [];
    let lastRefreshError = "";
    let sessionsRevision = "";
    let messagesRevisionBySession = {};
    let jobsRevision = "";
    let filePath = localStorage.getItem("codexMobileFilePath") || "/home/wxz";
    let fileParent = "";
    let fileRevision = "";
    let selectedFilePath = "";
    let showHiddenFiles = localStorage.getItem("codexMobileShowHiddenFiles") === "1";
    let hiddenSessionIds = new Set(JSON.parse(localStorage.getItem("codexMobileHiddenSessions") || "[]"));
    let titleOverrides = JSON.parse(localStorage.getItem("codexMobileSessionTitles") || "{}");
    let hiddenPanelOpen = localStorage.getItem("codexMobileHiddenPanelOpen") === "1";
    const qs = (s) => document.querySelector(s);
    const api = (path, opts = {}) => fetch(path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(token), opts);
    const savedSidebarWidth = localStorage.getItem("codexMobileSidebarWidth");
    if (savedSidebarWidth) document.documentElement.style.setProperty("--sidebar-width", savedSidebarWidth);

    function applyTheme(theme) {
      const next = theme === "dark" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("codexMobileTheme", next);
      const btn = qs("#themeBtn");
      if (btn) {
        btn.textContent = next === "dark" ? "☀" : "☾";
        btn.title = next === "dark" ? "切换到白天模式" : "切换到黑夜模式";
        btn.setAttribute("aria-label", btn.title);
      }
    }

    function fmt(ts) {
      if (!ts) return "";
      const d = new Date(ts);
      return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
    }
    function textOf(s, n = 80) {
      const t = (s || "").replace(/\s+/g, " ").trim();
      return t.length > n ? t.slice(0, n - 1) + "…" : t;
    }
    function shellQuote(value) {
      return "'" + String(value || "").replace(/'/g, "'\\''") + "'";
    }
    function resumeCommand(sessionId) {
      return "codex resume " + shellQuote(sessionId);
    }
    function sessionTitle(s) {
      return titleOverrides[s.id] || s.title || s.preview || s.id;
    }
    function saveTitleOverrides() {
      localStorage.setItem("codexMobileSessionTitles", JSON.stringify(titleOverrides));
    }
    async function renameSession(sessionId, currentTitle) {
      const nextTitle = window.prompt("修改会话标题", currentTitle || "");
      if (nextTitle === null) return;
      const title = nextTitle.trim();
      if (!title) return;
      titleOverrides[sessionId] = title;
      saveTitleOverrides();
      const item = sessions.find(s => s.id === sessionId);
      if (item) item.title = title;
      renderSessions();
      if (sessionId === activeId) qs("#threadTitle").textContent = title;
      const res = await api("/api/session/title", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session_id: sessionId, title})
      });
      if (!res.ok) {
        addUiError("标题已保存在手机本地，但写入 Codex 历史库失败：" + await res.text());
        return;
      }
      await loadSessions();
    }
    async function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
      }
      const el = document.createElement("textarea");
      el.value = text;
      el.setAttribute("readonly", "");
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    function saveHiddenSessions() {
      localStorage.setItem("codexMobileHiddenSessions", JSON.stringify([...hiddenSessionIds]));
    }
    function setMode(mode) {
      activeMode = mode === "files" ? "files" : "chat";
      localStorage.setItem("codexMobileMode", activeMode);
      qs("#messages").style.display = activeMode === "files" ? "none" : "flex";
      qs("#composer").style.display = activeMode === "files" ? "none" : "";
      qs("#fileBrowser").classList.toggle("open", activeMode === "files");
      if (activeMode === "files") {
        qs("#threadTitle").textContent = "文件浏览";
        qs("#terminal").classList.remove("open");
        terminalOpen = false;
        loadFiles();
      }
    }
    function hideSession(sessionId) {
      hiddenSessionIds.add(sessionId);
      saveHiddenSessions();
      if (activeId === sessionId) {
        const next = sessions.find(s => !hiddenSessionIds.has(s.id));
        activeId = next ? next.id : "";
        if (activeId) localStorage.setItem("codexMobileSession", activeId);
      }
      renderSessions();
      forceScrollBottom = true;
      loadMessages(true);
    }
    function renderSessions() {
      const visibleSessions = sessions.filter(s => !hiddenSessionIds.has(s.id));
      const hiddenSessions = sessions.filter(s => hiddenSessionIds.has(s.id));
      const hiddenCount = sessions.length - visibleSessions.length;
      qs("#sessionCount").textContent = visibleSessions.length + " 个会话" + (hiddenCount ? " · 隐藏 " + hiddenCount : "");
      const fileHtml = `
        <div class="file-entry ${activeMode === "files" ? "active" : ""}" id="fileEntry">
          <div class="title">文件</div>
          <div class="meta">浏览 /home/wxz 和 /nfs，支持预览与下载</div>
        </div>`;
      const visibleHtml = visibleSessions.map(s => `
        <div class="session ${s.id === activeId ? "active" : ""}" data-id="${s.id}">
          <div class="session-main">
            <div class="title">${escapeHtml(sessionTitle(s))}</div>
            <div class="meta time">${escapeHtml((s.id === currentSessionId ? "当前窗口 · " : "") + fmt(s.updated_at_ms))}</div>
            <div class="meta" title="${escapeHtml(s.cwd || "")}">${escapeHtml(s.cwd || "")}</div>
          </div>
          <div class="session-actions">
            <button class="session-action new-codex" type="button" data-session-id="${escapeHtml(s.id)}" title="新建全权限 Codex 对话">⧉</button>
            <button class="session-action rename-session" type="button" data-rename-id="${escapeHtml(s.id)}" data-title="${escapeHtml(sessionTitle(s))}" title="修改标题">✎</button>
            <button class="session-action copy-path" type="button" data-path="${escapeHtml(s.cwd || "")}" title="复制路径">⌂</button>
          </div>
        </div>`).join("");
      const hiddenHtml = hiddenSessions.length ? `
        <button class="session-group" id="hiddenToggle" type="button">隐藏对话 ${hiddenSessions.length} ${hiddenPanelOpen ? "收起" : "展开"}</button>
        ${hiddenPanelOpen ? hiddenSessions.map(s => `
          <div class="session hidden-card" data-id="${s.id}">
            <div class="session-main">
              <div class="title">${escapeHtml(sessionTitle(s))}</div>
              <div class="meta time">${escapeHtml(fmt(s.updated_at_ms))}</div>
              <div class="meta" title="${escapeHtml(s.cwd || "")}">${escapeHtml(s.cwd || "")}</div>
            </div>
            <div class="session-actions">
              <button class="session-action restore-session" type="button" data-restore-id="${escapeHtml(s.id)}" title="恢复显示">↩</button>
              <button class="session-action new-codex" type="button" data-session-id="${escapeHtml(s.id)}" title="新建全权限 Codex 对话">⧉</button>
              <button class="session-action copy-path" type="button" data-path="${escapeHtml(s.cwd || "")}" title="复制路径">⌂</button>
            </div>
          </div>`).join("") : ""}` : "";
      qs("#sessions").innerHTML = fileHtml + visibleHtml + hiddenHtml;
      qs("#fileEntry").onclick = () => {
        setMode("files");
        qs("#sidebar").classList.remove("open");
        renderSessions();
      };
      document.querySelectorAll(".session").forEach(b => b.onclick = () => {
        const previousId = activeId;
        activeId = b.dataset.id;
        setMode("chat");
        localStorage.setItem("codexMobileSession", activeId);
        qs("#sidebar").classList.remove("open");
        renderSessions();
        forceScrollBottom = true;
        if (previousId !== activeId) {
          const active = sessions.find(s => s.id === activeId);
          qs("#threadTitle").textContent = active ? sessionTitle(active) : "选择一个会话";
          qs("#messages").innerHTML = '<div class="notice">加载中...</div>';
        }
        loadMessages(true);
      });
      const hiddenToggle = qs("#hiddenToggle");
      if (hiddenToggle) hiddenToggle.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        hiddenPanelOpen = !hiddenPanelOpen;
        localStorage.setItem("codexMobileHiddenPanelOpen", hiddenPanelOpen ? "1" : "0");
        renderSessions();
      };
      document.querySelectorAll(".session").forEach(card => {
        if (hiddenSessionIds.has(card.dataset.id)) return;
        let startX = 0;
        let startY = 0;
        let swiping = false;
        card.addEventListener("touchstart", e => {
          const t = e.touches[0];
          startX = t.clientX;
          startY = t.clientY;
          swiping = true;
        }, {passive: true});
        card.addEventListener("touchmove", e => {
          if (!swiping) return;
          const t = e.touches[0];
          const dx = t.clientX - startX;
          const dy = t.clientY - startY;
          if (dx < -56 && Math.abs(dx) > Math.abs(dy) * 1.4) {
            card.classList.add("hiding");
          }
        }, {passive: true});
        card.addEventListener("touchend", e => {
          if (!swiping) return;
          swiping = false;
          const t = e.changedTouches[0];
          const dx = t.clientX - startX;
          const dy = t.clientY - startY;
          if (dx < -72 && Math.abs(dx) > Math.abs(dy) * 1.4) {
            hideSession(card.dataset.id);
          } else {
            card.classList.remove("hiding");
          }
        }, {passive: true});
      });
      document.querySelectorAll(".new-codex").forEach(btn => btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await startNewCodex(btn.dataset.sessionId, btn);
      });
      document.querySelectorAll(".copy-path").forEach(btn => btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          await copyText(btn.dataset.path || "");
          btn.classList.add("done");
          btn.textContent = "✓";
          setTimeout(() => {
            btn.classList.remove("done");
            btn.textContent = "⌂";
          }, 1200);
        } catch (err) {
          addUiError("复制路径失败：" + (err.message || String(err)));
        }
      });
      document.querySelectorAll(".rename-session").forEach(btn => btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await renameSession(btn.dataset.renameId, btn.dataset.title);
      });
      document.querySelectorAll(".restore-session").forEach(btn => btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        hiddenSessionIds.delete(btn.dataset.restoreId);
        saveHiddenSessions();
        renderSessions();
      });
    }
    function nearBottom(el) {
      return el.scrollHeight - el.scrollTop - el.clientHeight < 96;
    }
    function addUiError(text) {
      const message = String(text || "未知错误");
      const last = uiEvents[uiEvents.length - 1];
      const now = Date.now() / 1000;
      if (last && last.message === message && now - last.started_at < 60) return;
      uiEvents.push({
        id: "ui-" + Date.now() + "-" + Math.random().toString(16).slice(2),
        session_id: activeId,
        status: "failed",
        mode: "ui-error",
        started_at: now,
        message,
        output: ""
      });
      uiEvents = uiEvents.slice(-30);
    }
    function renderMessages(items) {
      lastRenderedItems = items;
      const list = qs("#messages");
      const keepBottom = forceScrollBottom || stickToBottom || nearBottom(list);
      const distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight;
      const active = sessions.find(s => s.id === activeId);
      qs("#threadTitle").textContent = active ? sessionTitle(active) : "选择一个会话";
      const activeJobs = [
        ...Object.values(jobs),
        ...uiEvents
      ]
        .filter(j => j.session_id === activeId && j.status !== "done")
        .sort((a, b) => (a.started_at || 0) - (b.started_at || 0));
      if (!items.length && !activeJobs.length) {
        qs("#messages").innerHTML = '<div class="notice">这个会话还没有可显示消息。</div>';
        return;
      }
      const rows = [
        ...items.map(m => ({type: "message", ts: Date.parse(m.timestamp) || 0, data: m})),
        ...activeJobs.map(j => ({type: "job", ts: (j.started_at || j.completed_at || 0) * 1000, data: j}))
      ].sort((a, b) => a.ts - b.ts);
      const html = rows.map(row => {
        if (row.type === "message") {
          const m = row.data;
          return `
        <div class="msg ${m.role === "user" ? "user" : "assistant"}">
          <button class="msg-copy" type="button" data-copy-text="${attrJson(m.text)}" title="复制内容">⧉</button>
          <span class="role">${m.role === "user" ? "你" : "Codex"} · ${escapeHtml(fmt(m.timestamp))}</span><span class="content">${markdown(m.text)}</span>
        </div>`;
        }
        const j = row.data;
        const body = [j.message || "", j.output || ""].filter(Boolean).join("\n\n") || "没有详细错误信息。";
        return `
        <div class="msg job ${j.status === "failed" ? "failed" : ""}">
          <button class="msg-copy" type="button" data-copy-text="${attrJson(body)}" title="复制内容">⧉</button>
          <span class="role">网页任务 · ${escapeHtml(jobLabel(j))}</span><span class="content">${markdown(body)}</span>
        </div>`;
      }).join("");
      list.innerHTML = html;
      document.querySelectorAll(".msg-copy").forEach(btn => btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          await copyText(JSON.parse(btn.dataset.copyText || "\"\""));
          btn.classList.add("done");
          btn.textContent = "✓";
          setTimeout(() => {
            btn.classList.remove("done");
            btn.textContent = "⧉";
          }, 1200);
        } catch (err) {
          addUiError("复制失败：" + (err.message || String(err)));
        }
      });
      if (keepBottom) {
        list.scrollTop = list.scrollHeight;
        stickToBottom = true;
      } else {
        list.scrollTop = Math.max(0, list.scrollHeight - list.clientHeight - distanceFromBottom);
      }
      forceScrollBottom = false;
    }
    function jobLabel(j) {
      if (j.mode === "ui-error") return "错误";
      if (j.mode === "new-exec" && j.status === "running") return "新对话运行中";
      if (j.mode === "new-exec" && j.status === "queued") return "新对话已投递";
      if (j.status === "queued") return "已投递";
      if (j.status === "running") return "运行中";
      if (j.status === "failed") return "失败";
      if (j.status === "done") return "已完成";
      return "同步中";
    }
    function formatSize(size) {
      if (size === null || size === undefined) return "";
      if (size < 1024) return size + " B";
      if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
      if (size < 1024 * 1024 * 1024) return (size / 1024 / 1024).toFixed(1) + " MB";
      return (size / 1024 / 1024 / 1024).toFixed(1) + " GB";
    }
    function fileIcon(item) {
      if (item.type === "dir") return "📁";
      if (item.blocked) return "⛔";
      return "📄";
    }
    function downloadUrl(path) {
      return "/api/files/download?path=" + encodeURIComponent(path) + "&token=" + encodeURIComponent(token);
    }
    function isHiddenFileName(name) {
      return String(name || "").startsWith(".");
    }
    async function loadFiles(force = false) {
      if (activeMode !== "files") return;
      const res = await api("/api/files/list?path=" + encodeURIComponent(filePath));
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (!force && data.revision && data.revision === fileRevision) return;
      fileRevision = data.revision || "";
      filePath = data.path;
      fileParent = data.parent || "";
      localStorage.setItem("codexMobileFilePath", filePath);
      renderFiles(data);
    }
    function renderFiles(data) {
      qs("#filePathInput").value = data.path;
      qs("#fileUpBtn").disabled = !data.parent;
      qs("#fileHiddenBtn").textContent = showHiddenFiles ? "隐藏点文件" : "显示隐藏";
      const visibleItems = showHiddenFiles ? data.items : data.items.filter(item => !isHiddenFileName(item.name));
      const rows = visibleItems.map(item => `
        <div class="file-row ${item.path === selectedFilePath ? "active" : ""}" data-path="${attrJson(item.path)}" data-type="${escapeHtml(item.type)}" data-blocked="${item.blocked ? "1" : "0"}">
          <div>
            <div class="file-name">${fileIcon(item)} ${escapeHtml(item.name)}</div>
            <div class="file-meta">${escapeHtml(item.type === "dir" ? "目录" : formatSize(item.size))} · ${escapeHtml(fmt(item.mtime))}${item.blocked ? " · 已屏蔽" : ""}</div>
          </div>
          ${item.type === "file" && !item.blocked ? `<a class="file-btn" href="${downloadUrl(item.path)}" download onclick="event.stopPropagation()">下载</a>` : ""}
        </div>`).join("");
      qs("#fileList").innerHTML = rows || '<div class="notice">目录为空，或隐藏项已被过滤。</div>';
      document.querySelectorAll(".file-row").forEach(row => row.onclick = async () => {
        const path = JSON.parse(row.dataset.path || "\"\"");
        if (row.dataset.blocked === "1") {
          qs("#filePreview").innerHTML = '<div class="notice">这个路径已被安全规则屏蔽。</div>';
          return;
        }
        if (row.dataset.type === "dir") {
          filePath = path;
          fileRevision = "";
          selectedFilePath = "";
          qs("#filePreview").innerHTML = '<div class="notice">选择文件预览，或点击目录进入。</div>';
          await loadFiles(true);
          return;
        }
        selectedFilePath = path;
        await previewFile(path);
        renderFiles(data);
      });
    }
    async function previewFile(path) {
      qs("#filePreview").innerHTML = '<div class="notice">加载预览...</div>';
      const res = await api("/api/files/preview?path=" + encodeURIComponent(path));
      if (!res.ok) {
        qs("#filePreview").innerHTML = '<div class="notice error">' + escapeHtml(await res.text()) + '</div>';
        return;
      }
      const data = await res.json();
      const actions = `<div class="file-bar" style="margin-bottom:10px"><div class="file-path">${escapeHtml(data.path)}</div><a class="file-btn" href="${downloadUrl(data.path)}" download>下载</a></div>`;
      if (data.type === "image") {
        qs("#filePreview").innerHTML = actions + `<img src="${downloadUrl(data.path)}" alt="${escapeHtml(data.name)}">`;
      } else if (data.type === "text") {
        qs("#filePreview").innerHTML = actions + `<pre>${escapeHtml(data.text || "")}</pre>`;
      } else if (data.type === "too_large") {
        qs("#filePreview").innerHTML = actions + `<div class="notice">文件过大，大小 ${escapeHtml(formatSize(data.size))}，请下载查看。</div>`;
      } else {
        qs("#filePreview").innerHTML = actions + `<div class="notice">这个文件类型暂不支持预览，请下载查看。</div>`;
      }
    }
    async function loadSessions() {
      const [sessionsRes, loadedRes] = await Promise.all([
        api("/api/sessions"),
        api("/api/remote/loaded")
      ]);
      if (!sessionsRes.ok) throw new Error(await sessionsRes.text());
      const sessionsPayload = await sessionsRes.json();
      const nextSessions = Array.isArray(sessionsPayload) ? sessionsPayload : (sessionsPayload.items || []);
      const nextSessionsRevision = Array.isArray(sessionsPayload) ? "" : (sessionsPayload.revision || "");
      loadedThreadIds = loadedRes.ok ? (await loadedRes.json()).thread_ids || [] : [];
      const sessionsChanged = !nextSessionsRevision || nextSessionsRevision !== sessionsRevision;
      if (sessionsChanged) {
        sessions = nextSessions;
        sessionsRevision = nextSessionsRevision;
      }
      currentSessionId = loadedThreadIds.find(id => sessions.some(s => s.id === id)) || "";
      const firstVisible = sessions.find(s => !hiddenSessionIds.has(s.id));
      const currentVisible = currentSessionId && !hiddenSessionIds.has(currentSessionId) ? currentSessionId : "";
      if (firstSessionLoad && !explicitSessionId) {
        activeId = currentVisible || (firstVisible && firstVisible.id) || activeId;
        if (activeId) localStorage.setItem("codexMobileSession", activeId);
      } else if ((firstSessionLoad && currentVisible && explicitSessionId === currentVisible) || hiddenSessionIds.has(activeId) || !sessions.some(s => s.id === activeId)) {
        activeId = currentVisible || (firstVisible && firstVisible.id) || "";
        if (activeId) localStorage.setItem("codexMobileSession", activeId);
      }
      firstSessionLoad = false;
      if (sessionsChanged) renderSessions();
    }
    async function loadMessages(forceRender = false) {
      if (activeMode === "files") return;
      if (!activeId) {
        renderMessages([]);
        return;
      }
      const res = await api("/api/messages?session_id=" + encodeURIComponent(activeId));
      if (!res.ok) throw new Error(await res.text());
      const payload = await res.json();
      const items = Array.isArray(payload) ? payload : (payload.items || []);
      const revision = Array.isArray(payload) ? "" : (payload.revision || "");
      if (!forceRender && revision && messagesRevisionBySession[activeId] === revision) return;
      messagesRevisionBySession[activeId] = revision;
      renderMessages(items);
    }
    async function loadJobs() {
      const res = await api("/api/jobs");
      if (!res.ok) throw new Error(await res.text());
      const nextJobs = await res.json();
      const nextRevision = JSON.stringify(nextJobs);
      const changed = nextRevision !== jobsRevision;
      if (changed) {
        jobs = nextJobs;
        jobsRevision = nextRevision;
      }
      return changed;
    }
    async function loadTerminal() {
      const res = await api("/api/remote/status");
      remote = res.ok ? await res.json() : {status: "unavailable", error: await res.text()};
      qs("#terminal").textContent = JSON.stringify({
        mode: "shared-history",
        target: activeId || null,
        currentWindowSession: currentSessionId || null,
        loadedThreadIds,
        remote
      }, null, 2);
      qs("#terminal").classList.toggle("open", terminalOpen);
      qs("#terminalBtn").textContent = terminalOpen ? "隐藏" : "状态";
    }
    async function refreshAll() {
      try {
        await loadSessions();
        if (activeMode === "files") {
          await loadFiles();
          lastRefreshError = "";
          return;
        }
        const jobsChanged = await loadJobs();
        await loadTerminal();
        await loadMessages(jobsChanged);
        lastRefreshError = "";
      } catch (e) {
        const message = e.message || String(e);
        if (message !== lastRefreshError) {
          addUiError("刷新失败：" + message);
          lastRefreshError = message;
        }
        renderMessages(lastRenderedItems);
      }
    }
    async function sendMessage() {
      const text = qs("#input").value.trim();
      if (activeMode === "files" || !text || !activeId || sending) return;
      sending = true;
      qs("#sendBtn").disabled = true;
      const targetId = activeId;
      const res = await api("/api/send", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session_id: targetId, message: text})
      });
      const data = res.ok ? await res.json() : null;
      if (data && data.job_id) {
        jobs[data.job_id] = {
          status: "running",
          mode: data.mode || "exec",
          started_at: Date.now() / 1000,
          session_id: targetId,
          message: text
        };
      }
      forceScrollBottom = true;
      qs("#input").value = "";
      sending = false;
      qs("#sendBtn").disabled = false;
      if (!res.ok) {
        addUiError("发送失败：" + await res.text());
      }
      await refreshAll();
    }
    async function startNewCodex(sessionId, btn) {
      if (!sessionId) return;
      const message = window.prompt("新建全权限 Codex 对话", "在当前目录继续处理这个项目");
      if (message === null) return;
      const text = message.trim();
      if (!text) return;
      const res = await api("/api/new", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session_id: sessionId, message: text})
      });
      if (!res.ok) {
        addUiError("新建 Codex 对话失败：" + await res.text());
        await refreshAll();
        return;
      }
      const data = await res.json();
      if (data && data.job_id) {
        jobs[data.job_id] = {
          status: "running",
          mode: data.mode || "new-exec",
          started_at: Date.now() / 1000,
          session_id: sessionId,
          message: text
        };
        if (btn) {
          btn.classList.add("done");
          btn.textContent = "✓";
          setTimeout(() => {
            btn.classList.remove("done");
            btn.textContent = "⧉";
          }, 1200);
        }
      }
      await refreshAll();
    }
    async function startTerminal() {
      terminalOpen = !terminalOpen;
      qs("#terminal").classList.toggle("open", terminalOpen);
      qs("#terminalBtn").textContent = terminalOpen ? "隐藏" : "状态";
      await refreshAll();
    }
    function escapeHtml(x) {
      return String(x || "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    }
    function attrJson(value) {
      return escapeHtml(JSON.stringify(String(value || "")));
    }
    function inlineMarkdown(text) {
      return escapeHtml(text)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    }
    function tableCells(line) {
      let s = line.trim();
      if (!s.includes("|")) return null;
      if (s.startsWith("|")) s = s.slice(1);
      if (s.endsWith("|")) s = s.slice(0, -1);
      return s.split("|").map(cell => cell.trim());
    }
    function isTableSeparator(line) {
      const cells = tableCells(line);
      return !!cells && cells.length > 1 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
    }
    function renderTable(lines) {
      const header = tableCells(lines[0]) || [];
      const rows = lines.slice(2).map(line => tableCells(line) || []);
      const head = `<thead><tr>${header.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>`;
      const body = `<tbody>${rows.map(row => `<tr>${header.map((_, i) => `<td>${inlineMarkdown(row[i] || "")}</td>`).join("")}</tr>`).join("")}</tbody>`;
      return `<div class="table-wrap"><table>${head}${body}</table></div>`;
    }
    function markdown(text) {
      const src = String(text || "").replace(/\r\n/g, "\n");
      const blocks = [];
      const token = "\u0000CODEBLOCK";
      let body = src.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
        const i = blocks.length;
        blocks.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
        return `${token}${i}\u0000`;
      });
      const lines = body.split("\n");
      const out = [];
      let list = null;
      const closeList = () => {
        if (list) {
          out.push(`</${list}>`);
          list = null;
        }
      };
      for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx];
        const blockMatch = line.match(new RegExp("^" + token + "(\\d+)\\u0000$"));
        if (blockMatch) {
          closeList();
          out.push(blocks[Number(blockMatch[1])] || "");
          continue;
        }
        if (!line.trim()) {
          closeList();
          continue;
        }
        if (idx + 1 < lines.length && tableCells(line)?.length > 1 && isTableSeparator(lines[idx + 1])) {
          closeList();
          const tableLines = [line, lines[idx + 1]];
          idx += 2;
          while (idx < lines.length && tableCells(lines[idx])?.length > 1 && lines[idx].trim()) {
            tableLines.push(lines[idx]);
            idx++;
          }
          idx--;
          out.push(renderTable(tableLines));
          continue;
        }
        const heading = line.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
          closeList();
          const level = heading[1].length;
          out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
          continue;
        }
        const quote = line.match(/^>\s?(.*)$/);
        if (quote) {
          closeList();
          out.push(`<blockquote>${inlineMarkdown(quote[1])}</blockquote>`);
          continue;
        }
        const unordered = line.match(/^\s*[-*]\s+(.+)$/);
        if (unordered) {
          if (list !== "ul") {
            closeList();
            list = "ul";
            out.push("<ul>");
          }
          out.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
          continue;
        }
        const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
        if (ordered) {
          if (list !== "ol") {
            closeList();
            list = "ol";
            out.push("<ol>");
          }
          out.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
          continue;
        }
        closeList();
        out.push(`<p>${inlineMarkdown(line)}</p>`);
      }
      closeList();
      return out.join("");
    }
    qs("#refreshBtn").onclick = refreshAll;
    applyTheme(document.documentElement.dataset.theme);
    qs("#themeBtn").onclick = () => {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    };
    qs("#sessionRefreshBtn").onclick = async (e) => {
      e.preventDefault();
      await refreshAll();
    };
    qs("#fileRefreshBtn").onclick = async () => {
      fileRevision = "";
      await loadFiles(true);
    };
    qs("#fileHiddenBtn").onclick = () => {
      showHiddenFiles = !showHiddenFiles;
      localStorage.setItem("codexMobileShowHiddenFiles", showHiddenFiles ? "1" : "0");
      fileRevision = "";
      loadFiles(true);
    };
    qs("#fileGoBtn").onclick = async () => {
      const nextPath = qs("#filePathInput").value.trim();
      if (!nextPath) return;
      filePath = nextPath;
      fileRevision = "";
      selectedFilePath = "";
      qs("#filePreview").innerHTML = '<div class="notice">选择文件预览，或点击目录进入。</div>';
      await loadFiles(true);
    };
    qs("#filePathInput").addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      await qs("#fileGoBtn").onclick();
    });
    qs("#fileCopyBtn").onclick = async () => {
      try {
        await copyText(qs("#filePathInput").value);
        qs("#fileCopyBtn").textContent = "已复制";
        setTimeout(() => qs("#fileCopyBtn").textContent = "复制", 1200);
      } catch (err) {
        addUiError("复制路径失败：" + (err.message || String(err)));
      }
    };
    qs("#fileUpBtn").onclick = async () => {
      if (!fileParent) return;
      filePath = fileParent;
      fileRevision = "";
      selectedFilePath = "";
      qs("#filePreview").innerHTML = '<div class="notice">选择文件预览，或点击目录进入。</div>';
      await loadFiles(true);
    };
    qs("#sendBtn").onclick = sendMessage;
    qs("#terminalBtn").onclick = startTerminal;
    qs("#menuBtn").onclick = () => qs("#sidebar").classList.toggle("open");
    setMode(activeMode);
    qs("#sidebarResizer").addEventListener("pointerdown", e => {
      if (window.matchMedia("(max-width: 760px)").matches) return;
      e.preventDefault();
      const move = ev => {
        const width = Math.max(320, Math.min(640, ev.clientX));
        const value = width + "px";
        document.documentElement.style.setProperty("--sidebar-width", value);
        localStorage.setItem("codexMobileSidebarWidth", value);
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
    qs("#messages").addEventListener("scroll", () => {
      stickToBottom = nearBottom(qs("#messages"));
    }, {passive: true});
    qs("#input").addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") sendMessage();
    });
    refreshAll();
    setInterval(refreshAll, 3000);
  </script>
</body>
</html>
"""


def ensure_token():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return token


def db_connect():
    return sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)


def db_write_connect():
    return sqlite3.connect(STATE_DB)


def list_sessions():
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in conn.execute("pragma table_info(threads)").fetchall()}
        preview_expr = "preview" if "preview" in columns else "first_user_message"
        archived_expr = "archived" if "archived" in columns else "0"
        updated_expr = (
            "coalesce(updated_at_ms, updated_at * 1000, created_at_ms, created_at * 1000, 0)"
        )
        rows = conn.execute(
            f"""
            select id, title, rollout_path, cwd,
                   {updated_expr} as updated_at_ms,
                   {preview_expr} as preview,
                   {archived_expr} as archived
            from threads
            order by updated_at_ms desc
            limit 200
            """
        ).fetchall()
        sessions = []
        for row in rows:
            item = dict(row)
            item["title"] = shorten(item.get("title", ""), 180)
            item["preview"] = shorten(item.get("preview", ""), 220)
            sessions.append(item)
        return sessions
    finally:
        conn.close()


def sessions_payload():
    sessions = list_sessions()
    revision_parts = "\n".join(
        f"{item.get('id', '')}:{item.get('updated_at_ms', '')}:{item.get('title', '')}:{item.get('archived', '')}"
        for item in sessions
    )
    return {
        "revision": hashlib.sha256(revision_parts.encode("utf-8")).hexdigest()[:16],
        "items": sessions,
    }


def shorten(text, max_len):
    text = (text or "").strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "..."


def get_session(session_id):
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select id, title, rollout_path, cwd, updated_at_ms from threads where id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_session_title(session_id, title):
    title = shorten(title, 180)
    if not title:
        raise ValueError("title is required")
    conn = db_write_connect()
    try:
        now_ms = int(time.time() * 1000)
        cur = conn.execute(
            "update threads set title = ?, updated_at_ms = ? where id = ?",
            (title, now_ms, session_id),
        )
        if cur.rowcount == 0:
            raise ValueError("unknown session")
        conn.commit()
        return {"session_id": session_id, "title": title, "updated_at_ms": now_ms}
    finally:
        conn.close()


def content_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("input_text") or item.get("output_text")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def parse_messages(session_id, limit=120):
    session = get_session(session_id)
    if not session:
        return []
    path = Path(session["rollout_path"])
    if not path.exists():
        return []
    messages = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "response_item":
                continue
            payload = obj.get("payload") or {}
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = content_text(payload.get("content")).strip()
            if not text or text.startswith("<environment_context>"):
                continue
            messages.append(
                {
                    "timestamp": obj.get("timestamp"),
                    "role": role,
                    "text": text,
                }
            )
    return messages[-limit:]


def messages_payload(session_id):
    session = get_session(session_id)
    if not session:
        return {"revision": f"{session_id}:missing", "items": []}
    path = Path(session["rollout_path"])
    if not path.exists():
        return {"revision": f"{session_id}:missing-rollout", "items": []}
    try:
        stat = path.stat()
        revision = f"{session_id}:{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        revision = f"{session_id}:stat-error:{time.time_ns()}"
    return {
        "revision": revision,
        "items": parse_messages(session_id),
    }


def path_is_blocked(path):
    parts = set(path.parts)
    if parts & BLOCKED_FILE_PARTS:
        return True
    name = path.name
    if name in BLOCKED_FILE_NAMES:
        return True
    if path.suffix.lower() in BLOCKED_FILE_SUFFIXES:
        return True
    if ".codex" in parts and name in {"auth.json", "config.toml"}:
        return True
    return False


def safe_file_path(raw_path, allow_file=True):
    raw_path = urllib.parse.unquote(raw_path or "")
    path = Path(raw_path).expanduser() if raw_path else HOME
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ValueError(str(exc))
    allowed = False
    for root in FILE_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise PermissionError("path is outside allowed roots")
    if path_is_blocked(resolved):
        raise PermissionError("path is blocked")
    if not allow_file and not resolved.is_dir():
        raise ValueError("path is not a directory")
    return resolved


def file_item(path):
    try:
        stat = path.stat()
        is_dir = path.is_dir()
        suffix = path.suffix.lower()
        blocked = path_is_blocked(path)
        return {
            "name": path.name or str(path),
            "path": str(path),
            "type": "dir" if is_dir else "file",
            "size": None if is_dir else stat.st_size,
            "mtime": int(stat.st_mtime * 1000),
            "previewable": (
                not is_dir
                and not blocked
                and (suffix in TEXT_PREVIEW_SUFFIXES or suffix in IMAGE_PREVIEW_SUFFIXES)
                and stat.st_size <= MAX_TEXT_PREVIEW_BYTES
            ),
            "blocked": blocked,
        }
    except OSError:
        return None


def files_list_payload(raw_path):
    path = safe_file_path(raw_path, allow_file=False)
    items = []
    try:
        children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        raise ValueError(str(exc))
    for child in children:
        item = file_item(child)
        if item:
            items.append(item)
    revision_src = "\n".join(
        f"{item['name']}:{item['type']}:{item.get('size')}:{item.get('mtime')}:{item.get('blocked')}"
        for item in items
    )
    parent = None
    try:
        parent_path = safe_file_path(str(path.parent), allow_file=False)
        if parent_path != path:
            parent = str(parent_path)
    except Exception:
        parent = None
    return {
        "path": str(path),
        "parent": parent,
        "roots": [str(root.resolve()) for root in FILE_ROOTS if root.exists()],
        "revision": hashlib.sha256((str(path) + "\n" + revision_src).encode("utf-8")).hexdigest()[:16],
        "items": items,
    }


def files_preview_payload(raw_path):
    path = safe_file_path(raw_path, allow_file=True)
    if not path.is_file():
        raise ValueError("path is not a file")
    stat = path.stat()
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if stat.st_size > MAX_TEXT_PREVIEW_BYTES and suffix not in IMAGE_PREVIEW_SUFFIXES:
        return {
            "path": str(path),
            "name": path.name,
            "type": "too_large",
            "size": stat.st_size,
            "mime": mime,
            "text": "",
        }
    if suffix in IMAGE_PREVIEW_SUFFIXES:
        return {
            "path": str(path),
            "name": path.name,
            "type": "image",
            "size": stat.st_size,
            "mime": mime,
            "text": "",
        }
    if suffix not in TEXT_PREVIEW_SUFFIXES:
        return {
            "path": str(path),
            "name": path.name,
            "type": "binary",
            "size": stat.st_size,
            "mime": mime,
            "text": "",
        }
    data = path.read_bytes()[:MAX_TEXT_PREVIEW_BYTES]
    return {
        "path": str(path),
        "name": path.name,
        "type": "text",
        "size": stat.st_size,
        "mime": mime,
        "text": data.decode("utf-8", errors="replace"),
    }


class AppServerClient:
    def __init__(self, sock_path=APP_SERVER_SOCK):
        self.sock_path = str(sock_path)
        self.sock = None
        self.next_id = 1

    def __enter__(self):
        self.sock = self._connect()
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "codex-mobile", "title": "Codex Mobile", "version": APP_VERSION},
                "capabilities": {
                    "experimentalApi": True,
                    "requestAttestation": False,
                    "optOutNotificationMethods": [],
                },
            },
        )
        self.notify("initialized")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.sock:
            self.sock.close()

    def _connect(self):
        import socket

        if not Path(self.sock_path).exists():
            raise RuntimeError("app-server daemon socket not found; run `codex remote-control start --json`")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect(self.sock_path)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
        sock.sendall(req)
        headers = b""
        while b"\r\n\r\n" not in headers:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("app-server websocket handshake failed")
            headers += chunk
        if b"101 Switching Protocols" not in headers:
            raise RuntimeError(headers.decode(errors="replace"))
        return sock

    def _send_text(self, text):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header = bytes([0x81, 0x80 | n])
        elif n < 65536:
            header = bytes([0x81, 0x80 | 126]) + struct.pack("!H", n)
        else:
            header = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", n)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _recv_text(self):
        header = self.sock.recv(2)
        if not header:
            raise RuntimeError("app-server websocket closed")
        b1, b2 = header
        opcode = b1 & 0x0F
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self.sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self.sock.recv(8))[0]
        mask = self.sock.recv(4) if (b2 & 0x80) else b""
        payload = b""
        while len(payload) < length:
            payload += self.sock.recv(length - len(payload))
        if mask:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        if opcode == 8:
            raise RuntimeError("app-server websocket closed")
        if opcode != 1:
            return None
        return payload.decode("utf-8")

    def notify(self, method, params=None):
        msg = {"method": method}
        if params is not None:
            msg["params"] = params
        self._send_text(json.dumps(msg, separators=(",", ":")))

    def request(self, method, params=None):
        req_id = self.next_id
        self.next_id += 1
        msg = {"id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send_text(json.dumps(msg, separators=(",", ":")))
        while True:
            text = self._recv_text()
            if not text:
                continue
            data = json.loads(text)
            if data.get("id") != req_id:
                continue
            if "error" in data:
                raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
            return data.get("result")


def app_server_status():
    try:
        with AppServerClient() as client:
            return client.request("remoteControl/status/read")
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def loaded_thread_ids():
    try:
        with AppServerClient() as client:
            result = client.request("thread/loaded/list", {"limit": 50})
            return {"thread_ids": result.get("data", [])}
    except Exception as exc:
        return {"thread_ids": [], "error": str(exc)}


def current_loaded_thread_id():
    ids = loaded_thread_ids().get("thread_ids", [])
    return ids[0] if ids else ""


def inputbox_injector_script(base_url, token):
    host = urllib.parse.urlparse(base_url).hostname or "*"
    return f"""// ==UserScript==
// @name         Codex Mobile InputBox Relay
// @namespace    codex-mobile
// @version      0.1
// @description  Poll Codex Mobile and send queued text through the currently open chat input box.
// @match        *://chatgpt.com/*
// @match        *://chat.openai.com/*
// @match        *://*.vscode.dev/*
// @match        *://*.github.dev/*
// @match        *://*.vscode-cdn.net/*
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @connect      {host}
// ==/UserScript==

(function () {{
  "use strict";
  const BASE = {json.dumps(base_url)};
  const TOKEN = {json.dumps(token)};
  let busy = false;

  function request(method, path, body) {{
    const url = BASE + path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN);
    return new Promise((resolve, reject) => {{
      if (typeof GM_xmlhttpRequest === "function") {{
        GM_xmlhttpRequest({{
          method,
          url,
          headers: {{"Content-Type": "application/json"}},
          data: body ? JSON.stringify(body) : undefined,
          onload: r => {{
            try {{ resolve(JSON.parse(r.responseText || "{{}}")); }}
            catch (e) {{ reject(new Error(r.responseText || e.message)); }}
          }},
          onerror: () => reject(new Error("request failed"))
        }});
      }} else {{
        fetch(url, {{
          method,
          headers: {{"Content-Type": "application/json"}},
          body: body ? JSON.stringify(body) : undefined
        }}).then(r => r.json()).then(resolve, reject);
      }}
    }});
  }}

  function visible(el) {{
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
  }}

  function findInput() {{
    const selectors = [
      "textarea:not([disabled])",
      "[contenteditable='true']",
      "div[role='textbox']",
      ".ProseMirror",
      "[data-testid='composer'] [contenteditable='true']",
      "[data-testid='prompt-textarea']"
    ];
    for (const sel of selectors) {{
      const nodes = Array.from(document.querySelectorAll(sel)).filter(visible);
      if (nodes.length) return nodes[nodes.length - 1];
    }}
    return null;
  }}

  function setInputText(el, text) {{
    el.focus();
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {{
      const proto = Object.getPrototypeOf(el);
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, text);
      else el.value = text;
      el.dispatchEvent(new InputEvent("input", {{bubbles: true, inputType: "insertText", data: text}}));
      el.dispatchEvent(new Event("change", {{bubbles: true}}));
      return;
    }}
    document.getSelection()?.selectAllChildren(el);
    document.execCommand("delete", false);
    document.execCommand("insertText", false, text);
    el.dispatchEvent(new InputEvent("input", {{bubbles: true, inputType: "insertText", data: text}}));
  }}

  function findSendButton() {{
    const selectors = [
      "button[data-testid='send-button']",
      "button[data-testid='composer-send-button']",
      "button[aria-label*='Send']",
      "button[aria-label*='send']",
      "button[aria-label*='发送']",
      "form button[type='submit']",
      "button[type='submit']"
    ];
    for (const sel of selectors) {{
      const nodes = Array.from(document.querySelectorAll(sel)).filter(b => visible(b) && !b.disabled && b.getAttribute("aria-disabled") !== "true");
      if (nodes.length) return nodes[nodes.length - 1];
    }}
    return null;
  }}

  function pressEnter(el) {{
    for (const type of ["keydown", "keypress", "keyup"]) {{
      el.dispatchEvent(new KeyboardEvent(type, {{key: "Enter", code: "Enter", bubbles: true, cancelable: true}}));
    }}
  }}

  function assistantNodes() {{
    const selectors = [
      "[data-message-author-role='assistant']",
      "[data-testid*='assistant']",
      ".markdown.prose",
      "article"
    ];
    for (const sel of selectors) {{
      const nodes = Array.from(document.querySelectorAll(sel)).filter(visible);
      if (nodes.length) return nodes;
    }}
    return [];
  }}

  function generating() {{
    return !!document.querySelector("button[data-testid='stop-button'], button[aria-label*='Stop'], button[aria-label*='停止']");
  }}

  async function sleep(ms) {{
    return new Promise(r => setTimeout(r, ms));
  }}

  async function sendThroughInputBox(text) {{
    const before = assistantNodes().length;
    const input = findInput();
    if (!input) throw new Error("没有找到当前页面的输入框");
    setInputText(input, text);
    await sleep(250);
    const btn = findSendButton();
    if (btn) btn.click();
    else pressEnter(input);

    let last = "";
    let lastChange = Date.now();
    const start = Date.now();
    while (Date.now() - start < 300000) {{
      await sleep(1000);
      const nodes = assistantNodes();
      const newer = nodes.slice(before);
      const textNow = (newer[newer.length - 1]?.innerText || "").trim();
      if (textNow && textNow !== last) {{
        last = textNow;
        lastChange = Date.now();
      }}
      if (last && !generating() && Date.now() - lastChange > 3500 && Date.now() - start > 5000) {{
        return last;
      }}
    }}
    return last || "已发送，但脚本没有识别到回复文本";
  }}

  async function handle(job) {{
    try {{
      const output = await sendThroughInputBox(job.message || "");
      await request("POST", "/api/inputbox/result", {{job_id: job.job_id, status: "done", output}});
    }} catch (e) {{
      await request("POST", "/api/inputbox/result", {{job_id: job.job_id, status: "failed", output: e.message || String(e)}});
    }}
  }}

  async function poll() {{
    if (busy) return;
    busy = true;
    try {{
      const data = await request("GET", "/api/inputbox/next");
      if (data && data.job) await handle(data.job);
    }} catch (_) {{
    }} finally {{
      busy = false;
    }}
  }}

  setInterval(poll, 2000);
  poll();
}})();
"""


def ensure_remote_control():
    proc = subprocess.run(
        [CODEX_BIN, "remote-control", "start", "--json"],
        text=True,
        env=codex_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(HOME),
        timeout=30,
    )
    output = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(output)
    return json.loads(output)


def send_remote_turn(session_id, message):
    session = get_session(session_id)
    if not session:
        raise ValueError("unknown session")
    with AppServerClient() as client:
        status = client.request("remoteControl/status/read")
        if status.get("status") != "connected":
            raise RuntimeError(f"remote-control is not connected: {status}")
        client.request("thread/resume", {"threadId": session_id, "excludeTurns": True})
        input_items = [{"type": "text", "text": message, "text_elements": []}]
        active_turn_id = None
        turns = client.request("thread/turns/list", {"threadId": session_id, "limit": 20})
        in_progress = [
            turn for turn in turns.get("data", [])
            if turn.get("status") == "inProgress" and turn.get("id")
        ]
        if in_progress:
            active_turn_id = max(in_progress, key=lambda turn: turn.get("startedAt") or 0)["id"]
            result = client.request(
                "turn/steer",
                {
                    "threadId": session_id,
                    "expectedTurnId": active_turn_id,
                    "input": input_items,
                },
            )
            mode = "steer"
        else:
            result = client.request(
                "turn/start",
                {
                    "threadId": session_id,
                    "input": input_items,
                },
            )
            mode = "start"
        return {
            "status": "sent",
            "mode": mode,
            "session_id": session_id,
            "active_turn_id": active_turn_id,
            "remote": status,
            "turn": result,
        }


def extract_agent_message(stdout):
    last = ""
    for line in stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = obj.get("payload") or obj
        if payload.get("type") == "agent_message":
            last = payload.get("message") or last
        if payload.get("type") == "message" and payload.get("role") == "assistant":
            text = content_text(payload.get("content")).strip()
            if text:
                last = text
    return last.strip()


def run_codex_job(job_id, session_id, message):
    JOB_OUTPUT_DIR.mkdir(exist_ok=True)
    output_file = JOB_OUTPUT_DIR / f"{job_id}.txt"
    cmd = [
        CODEX_BIN,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "resume",
        "--skip-git-repo-check",
        "--json",
        "-o",
        str(output_file),
        session_id,
        "-",
    ]
    started = time.time()
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "mode": "exec",
            "started_at": started,
            "session_id": session_id,
            "message": message,
            "output": "",
        }
    try:
        proc = subprocess.run(
            cmd,
            input=message,
            text=True,
            env=codex_env(),
            cwd=str(HOME),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=None,
        )
        status = "done" if proc.returncode == 0 else "failed"
        output = ""
        if output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="replace").strip()
        if not output:
            output = extract_agent_message(proc.stdout)
        if not output:
            output = proc.stdout[-8000:]
    except Exception as exc:
        status = "failed"
        output = str(exc)
    with JOBS_LOCK:
        JOBS[job_id].update(
            {
                "status": status,
                "completed_at": time.time(),
                "output": output,
            }
        )


def run_new_codex_job(job_id, source_session_id, cwd, message):
    JOB_OUTPUT_DIR.mkdir(exist_ok=True)
    output_file = JOB_OUTPUT_DIR / f"{job_id}.txt"
    cmd = [
        CODEX_BIN,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--json",
        "-o",
        str(output_file),
        "-",
    ]
    started = time.time()
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "mode": "new-exec",
            "started_at": started,
            "session_id": source_session_id,
            "cwd": cwd,
            "message": message,
            "output": "",
        }
    try:
        proc = subprocess.run(
            cmd,
            input=message,
            text=True,
            env=codex_env(),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=None,
        )
        status = "done" if proc.returncode == 0 else "failed"
        output = ""
        if output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="replace").strip()
        if not output:
            output = extract_agent_message(proc.stdout)
        if not output:
            output = proc.stdout[-8000:]
    except Exception as exc:
        status = "failed"
        output = str(exc)
    with JOBS_LOCK:
        JOBS[job_id].update(
            {
                "status": status,
                "completed_at": time.time(),
                "output": output,
            }
        )


class Handler(BaseHTTPRequestHandler):
    token = ""

    def log_message(self, fmt, *args):
        return

    def parse_url(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        return parsed.path, {k: v[-1] for k, v in params.items()}

    def authorized(self, params):
        return params.get("token") == self.token

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, status=200, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file_download(self, path):
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded_name = urllib.parse.quote(path.name)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 256)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path, params = self.parse_url()
        if path == "/":
            self.send_text(INDEX_HTML, content_type="text/html; charset=utf-8")
            return
        if path == "/injector.user.js":
            if not self.authorized(params):
                self.send_text("unauthorized", 401)
                return
            origin = f"https://{self.headers.get('Host')}"
            self.send_text(
                inputbox_injector_script(origin, self.token),
                content_type="application/javascript; charset=utf-8",
            )
            return
        if not self.authorized(params):
            self.send_text("unauthorized", 401)
            return
        if path == "/api/sessions":
            self.send_json(sessions_payload())
            return
        if path == "/api/messages":
            self.send_json(messages_payload(params.get("session_id", "")))
            return
        if path == "/api/files/list":
            try:
                self.send_json(files_list_payload(params.get("path", "")))
            except PermissionError as exc:
                self.send_text(str(exc), 403)
            except Exception as exc:
                self.send_text(str(exc), 400)
            return
        if path == "/api/files/preview":
            try:
                self.send_json(files_preview_payload(params.get("path", "")))
            except PermissionError as exc:
                self.send_text(str(exc), 403)
            except Exception as exc:
                self.send_text(str(exc), 400)
            return
        if path == "/api/files/download":
            try:
                target = safe_file_path(params.get("path", ""), allow_file=True)
                if not target.is_file():
                    self.send_text("path is not a file", 400)
                    return
                self.send_file_download(target)
            except PermissionError as exc:
                self.send_text(str(exc), 403)
            except Exception as exc:
                self.send_text(str(exc), 400)
            return
        if path == "/api/jobs":
            with JOBS_LOCK:
                self.send_json(JOBS)
            return
        if path == "/api/remote/status":
            self.send_json(app_server_status())
            return
        if path == "/api/remote/loaded":
            self.send_json(loaded_thread_ids())
            return
        if path == "/api/inputbox/next":
            now = time.time()
            with INPUTBOX_LOCK, JOBS_LOCK:
                for job_id in list(INPUTBOX_QUEUE):
                    job = JOBS.get(job_id)
                    if not job:
                        INPUTBOX_QUEUE.remove(job_id)
                        continue
                    if job.get("status") == "claimed" and now - job.get("claimed_at", 0) < 120:
                        continue
                    if job.get("status") in {"queued", "claimed"}:
                        job["status"] = "claimed"
                        job["claimed_at"] = now
                        self.send_json({"job": {"job_id": job_id, **job}})
                        return
                    INPUTBOX_QUEUE.remove(job_id)
            self.send_json({"job": None})
            return
        self.send_text("not found", 404)

    def do_POST(self):
        path, params = self.parse_url()
        if not self.authorized(params):
            self.send_text("unauthorized", 401)
            return
        if path not in {"/api/send", "/api/new", "/api/remote/start", "/api/remote/send", "/api/inputbox/result", "/api/session/title"}:
            self.send_text("not found", 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = {}
        if length:
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self.send_text("bad json", 400)
                return
        if path == "/api/inputbox/result":
            job_id = (data.get("job_id") or "").strip()
            status = (data.get("status") or "done").strip()
            output = (data.get("output") or "").strip()
            if status not in {"done", "failed"}:
                status = "done"
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    self.send_text("unknown job", 404)
                    return
                job.update({"status": status, "completed_at": time.time(), "output": output})
            with INPUTBOX_LOCK:
                if job_id in INPUTBOX_QUEUE:
                    INPUTBOX_QUEUE.remove(job_id)
            self.send_json({"job_id": job_id, "status": status})
            return
        if path == "/api/session/title":
            session_id = (data.get("session_id") or "").strip()
            title = (data.get("title") or "").strip()
            if not session_id:
                self.send_text("session_id is required", 400)
                return
            try:
                self.send_json(update_session_title(session_id, title))
            except Exception as exc:
                self.send_text(str(exc), 400)
            return
        if path == "/api/remote/start":
            try:
                self.send_json(ensure_remote_control())
            except Exception as exc:
                self.send_text(str(exc), 500)
            return
        session_id = (data.get("session_id") or "").strip()
        message = (data.get("message") or "").strip()
        if not session_id:
            self.send_text("session_id is required", 400)
            return
        if not message:
            self.send_text("message is required", 400)
            return
        requested_session_id = session_id
        if path == "/api/remote/send":
            session_id = current_loaded_thread_id() or session_id
        if not get_session(session_id):
            self.send_text("unknown session", 404)
            return
        if path == "/api/new":
            session = get_session(session_id)
            cwd = (session.get("cwd") or "").strip() or str(HOME)
            try:
                cwd_path = Path(cwd).expanduser().resolve()
            except Exception as exc:
                self.send_text(str(exc), 400)
                return
            if not cwd_path.is_dir():
                self.send_text(f"cwd is not a directory: {cwd_path}", 400)
                return
            job_id = secrets.token_hex(8)
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "queued",
                    "mode": "new-exec",
                    "started_at": time.time(),
                    "session_id": session_id,
                    "cwd": str(cwd_path),
                    "message": message,
                    "output": "",
                }
            threading.Thread(
                target=run_new_codex_job,
                args=(job_id, session_id, str(cwd_path), message),
                daemon=True,
            ).start()
            self.send_json({
                "job_id": job_id,
                "status": "queued",
                "mode": "new-exec",
                "cwd": str(cwd_path),
            })
            return
        if path == "/api/remote/send":
            try:
                result = send_remote_turn(session_id, message)
            except Exception as exc:
                self.send_text(str(exc), 500)
                return
            job_id = secrets.token_hex(8)
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "done",
                    "started_at": time.time(),
                    "completed_at": time.time(),
                    "session_id": session_id,
                    "requested_session_id": requested_session_id,
                    "message": message,
                    "output": "sent through app-server remote-control",
                }
            result["job_id"] = job_id
            result["requested_session_id"] = requested_session_id
            self.send_json(result)
            return
        job_id = secrets.token_hex(8)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "queued",
                "mode": "exec",
                "started_at": time.time(),
                "session_id": session_id,
                "requested_session_id": requested_session_id,
                "message": message,
                "output": "",
            }
        threading.Thread(
            target=run_codex_job,
            args=(job_id, session_id, message),
            daemon=True,
        ).start()
        self.send_json({
            "job_id": job_id,
            "status": "queued",
            "mode": "exec",
            "session_id": session_id,
            "requested_session_id": requested_session_id,
        })
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    Handler.token = ensure_token()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Codex Mobile: http://127.0.0.1:{args.port}/?token={Handler.token}")
    print(f"LAN URL:       http://<this-computer-ip>:{args.port}/?token={Handler.token}")
    print(f"Token file:    {TOKEN_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
