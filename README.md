# Codex Mobile

当前版本：`mobile-ui-v4`

Codex Mobile 是一个面向手机和远程服务器的 Codex 会话管理网页。它可以在浏览器里查看本机 Codex 历史、继续发送指令、浏览服务器文件，并通过 Cloudflare Tunnel 暴露一个带 token 的公网入口。

## 安装提示词

如果你想让 Codex 在一台 Linux 服务器上自动安装并启动这个项目，可以直接发送类似下面的提示词：

```text
安装 https://github.com/XinzeWu/codex-history-mobile 这个库，启动 Codex Mobile 服务，并返回可以访问的网页地址。要求：
1. 克隆或更新仓库到合适的本地目录。
2. 安装或复用 cloudflared。
3. 启动本地服务和 Cloudflare quick tunnel。
4. 不要提交 token、日志、pid、job_outputs 等运行产物。
5. 启动后先立即检查服务是否可访问，再等待约 1 分钟复查一次。
6. 最后返回本地端口、公网 URL、token 文件位置和运行进程状态。
```

如果只需要本地访问，可以把第 2、3 条改成“只启动本地服务，不开启公网 tunnel”。

## 功能介绍

### 会话查看与继续对话

- 在网页中列出本机 `~/.codex` 里的 Codex 会话。
- 查看用户消息、Codex 回复和网页任务输出。
- 支持 Markdown 渲染，包括代码块、列表、引用、链接和表格。
- 在当前会话中发送新指令，后端通过 `codex exec resume <session_id>` 继续同一个 Codex 会话。
- 支持中断网页启动的 Codex 任务；中断会向 Codex 进程组发送类似 `Ctrl+C` 的信号。
- 后台任务显示排队、运行、失败等状态。

### 会话管理

每个会话卡片右侧有 5 个快捷按钮：

```text
◂ 隐藏/↩ 恢复
⧉ 复制对话
✎ 重命名
⌘ 复制 codex resume 指令
⌂ 复制工作目录路径
```

- 支持重命名会话。
- 标题写入服务端 `.codex_mobile_state.json`，多台设备访问同一个服务时能看到一致标题。
- 会尽量同步标题到 Codex state DB。
- 支持隐藏/恢复会话；隐藏状态同样写入 `.codex_mobile_state.json`。
- 隐藏不会删除任何 Codex 本地文件。
- 支持折叠查看隐藏会话并逐个恢复。
- 桌面端左侧目录栏可拖拽调整宽度，移动端目录栏全屏展示。

### 文件浏览

- 文件入口从当前用户的 `~` 目录开始。
- 支持浏览 `/home/<user>` 和 `/nfs`。
- 支持文件预览和下载。
- 支持隐藏点文件，顶部按钮可切换显示隐藏文件。
- 支持路径输入跳转、复制当前路径、上级目录、刷新。
- 可以在当前浏览目录直接新建一个全权限 Codex 对话。

### 移动端与刷新体验

- 支持手机浏览器访问。
- 支持浅色/深色主题切换。
- 会话列表、消息历史、job 状态和文件列表使用 revision 判断；没有变化时跳过 DOM 重绘，减少刷新对滚动、横向浏览表格和目录浏览的干扰。
- 刷新和中断按钮会在界面里给出即时反馈。
- 刷新时不强制滚动到底部，方便阅读历史。

### 公网访问与后台运行

- 支持本地启动。
- 支持 Cloudflare quick tunnel 生成公网 URL。
- 支持 systemd 用户服务保活，SSH 断开后服务继续运行。

## 快速启动

```bash
cd codex-mobile-release
chmod +x *.sh
./start.sh
```

服务启动后会在当前目录生成：

```text
token.txt
```

本地访问：

```text
http://127.0.0.1:8787/?token=<token>
```

## 公网访问

先安装 `cloudflared`，然后放到：

```text
bin/cloudflared
```

或者让 `cloudflared` 在 `PATH` 中可执行。

启动公开访问：

```bash
./run_public.sh
```

查看服务和 tunnel 状态：

```bash
./status_public.sh
```

停止公开访问：

```bash
./stop_public.sh
```

脚本会输出类似：

```text
https://xxxxx.trycloudflare.com/?token=...
```

Cloudflare quick tunnel 的域名是临时的，进程重启后可能变化。需要固定域名时，请使用 Cloudflare named tunnel、反向代理或 Zero Trust。

## systemd 用户服务

安装并启动网页服务：

```bash
./install_systemd_user.sh
```

如果 `bin/cloudflared` 存在，脚本也会安装 tunnel 服务。

查看状态：

```bash
./status_service.sh
systemctl --user status codex-mobile-server.service
systemctl --user status codex-mobile-tunnel.service
```

为了让用户服务在完全退出 SSH 后继续运行，需要开启 linger：

```bash
loginctl enable-linger "$USER"
```

如果没有权限，请让管理员执行。

## 环境要求

- Linux
- Python 3.10+
- Codex CLI 已安装并已登录
- 可读取 `~/.codex/state_5.sqlite`
- 可读取 `~/.codex/sessions`
- 可选：`cloudflared`
- 可选：`systemd --user`

默认会自动查找常见位置的 Codex CLI：

```bash
~/.local/bin/codex
~/.nvm/versions/node/*/bin/codex
~/.npm-global/bin/codex
~/.bun/bin/codex
/usr/local/bin/codex
```

也可以手动指定：

```bash
export CODEX_BIN=/path/to/codex
```

## 安全警告

当前版本的网页任务默认以完整权限运行：

```bash
codex exec --dangerously-bypass-approvals-and-sandbox ...
```

这意味着拿到网页 URL 和 token 的人，可以通过你的服务器执行高权限操作。

建议：

- 不要把 URL 发给不可信的人。
- 不要把 `token.txt` 提交到 GitHub。
- 定期删除 `token.txt` 重新生成 token。
- 公网部署时优先使用 Cloudflare Zero Trust、VPN、反向代理鉴权或 SSH tunnel。
- 不要把 quick tunnel 当作生产级鉴权方案。

## 工作原理

这个项目是单文件 Python 服务，核心入口是 `server.py`。前端 HTML/CSS/JS 直接内嵌在 `INDEX_HTML` 字符串里。

主要数据来源：

```text
~/.codex/state_5.sqlite
~/.codex/sessions/**/*.jsonl
```

会话列表来自 Codex state DB，消息历史来自 rollout JSONL 文件。

继续旧对话的链路：

```text
浏览器输入
→ Python server
→ codex exec --dangerously-bypass-approvals-and-sandbox resume <session_id> -
→ 写入 ~/.codex 会话历史
```

新建全权限对话的链路：

```text
浏览器选择会话 cwd 或文件浏览目录
→ Python server
→ codex exec --dangerously-bypass-approvals-and-sandbox -
→ 在目标目录启动新的 Codex 任务
```

服务还会尝试读取 Codex app-server/remote-control 的当前加载会话，用来优先选择 VS Code/Codex 当前打开的 session。但网页发送消息时走的是 Codex CLI，不是 VS Code extension API。

## VS Code 兼容说明

这个仓库不是 VS Code 插件包，没有 `package.json`、extension host、webview contribution 或 marketplace 发布配置。

它与 VS Code/Codex 的兼容方式是：

- 读取同一套 `~/.codex` 会话历史。
- 查询 app-server remote-control 当前加载的 thread id。
- 手机端产生的会话历史写回 `~/.codex`，VS Code/Codex 重新打开对应会话后可以读取。
- 可以复制 `codex resume <session_id>` 指令，方便在电脑端恢复指定会话。

## 目录结构

```text
.
├── server.py
├── start.sh
├── run_public.sh
├── stop_public.sh
├── status_public.sh
├── status_service.sh
├── install_systemd_user.sh
├── systemd/
│   ├── codex-mobile-server.service.in
│   └── codex-mobile-tunnel.service.in
└── bin/
    └── .gitkeep
```

运行后会生成：

```text
token.txt
.codex_mobile_state.json
logs/
run/
job_outputs/
```

这些运行产物都应该被 `.gitignore` 排除。

## 常见操作

查看服务：

```bash
./status_public.sh
```

重启公网服务：

```bash
./stop_public.sh
./run_public.sh
```

检查 Codex CLI：

```bash
codex --version
codex exec --help
```

检查 Git 状态，避免提交敏感文件：

```bash
git status --short
git ls-files | grep -E 'token|\\.log|\\.pid|job_outputs|cloudflared|codex_mobile_state' || true
```

## 常见问题

### 页面能打开，但发送没有结果

先确认 Codex CLI 能运行：

```bash
codex --version
codex exec --help
```

再查看服务状态和日志：

```bash
./status_public.sh
journalctl --user -u codex-mobile-server.service -f
```

### SSH 断开后网页不可用

确认 systemd 用户服务和 linger：

```bash
systemctl --user status codex-mobile-server.service
loginctl show-user "$USER" -p Linger
```

### URL 变了

quick tunnel 是临时 URL。每次重启 tunnel 后，trycloudflare 域名都可能变化。需要固定 URL 时，请使用 Cloudflare named tunnel 或自己的反向代理。

### 重命名标题在不同设备不一致

当前版本会把标题写入服务端 `.codex_mobile_state.json`。如果仍然不一致，确认访问的是同一个服务目录、同一个公网 URL 对应的同一个后端进程。
