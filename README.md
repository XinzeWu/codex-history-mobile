# Codex Mobile

当前版本：`mobile-ui-v3`

版本定位：**CLI + VS Code 兼容 + 移动端增强版**

Codex Mobile 是一个轻量级网页桥，用手机浏览器查看本机 Codex 会话历史，并把手机输入作为新的 Codex 指令发送到同一个会话里。

它适合这种场景：

- SSH 或 VS Code 断开后，后台服务继续运行。
- 手机打开公开链接，选择 Codex 会话，查看历史和发送指令。
- 手机端发送的指令写入同一套 `~/.codex` 会话记录；之后重新打开 VS Code/Codex 会话，可以看到手机端产生的历史。
- 可选通过 Cloudflare Tunnel 暴露公网访问地址。

## 版本说明

这个仓库当前整理的是 **CLI + VS Code 兼容版**。

它不是 VS Code 扩展打包版，但兼容 VS Code/Codex 扩展的会话历史：手机端发送的内容写入同一套 `~/.codex` 会话记录，VS Code/Codex 重新打开对应会话后可以看到这些历史。

它的发送链路是：

```text
手机网页输入
→ 本地 Python server
→ codex exec resume <session_id> -
→ 写入 ~/.codex 会话历史
```

它也会尝试读取 Codex app-server/remote-control 的当前加载会话，用来判断 VS Code/Codex 当前打开的是哪个 session。但手机端真正发送消息时，仍然走 Codex CLI，不是操作 VS Code 输入框，也不是 VS Code extension API。

### CLI 兼容

- 版本：`0.1.1-cli-vscode-compatible`
- 入口：`server.py`
- 后端执行：`codex exec resume`
- 会话来源：`~/.codex/state_5.sqlite` 和 `~/.codex/sessions`
- 适合：服务器、SSH、长期后台运行、手机公网访问

### VS Code 兼容

当前代码与 VS Code/Codex 扩展的兼容方式：

- 通过 app-server remote-control 查询当前加载的 thread id。
- 手机重新打开时优先选择当前 VS Code/Codex 加载的会话。
- 手机端发送结果写入 `~/.codex` 历史，VS Code/Codex 重新打开同一会话后可读取到。
- 手机端可复制 resume 命令、复制消息内容、修改目录标题、隐藏/恢复目录项。

它仍然不是 VS Code 插件包，没有 `package.json`、extension host、webview contribution 或 marketplace 发布配置。如果以后要做完整 VS Code extension edition，建议单独建 `vscode-extension/` 子项目。

建议后续多版本目录结构：

```text
.
├── cli/
│   └── 当前 server.py 这一套逻辑
├── vscode-extension/
│   └── 未来 VS Code 插件实现
└── shared/
    └── 可复用协议、类型和文档
```

当前仓库暂时没有拆目录，是为了保持部署路径简单；`0.2.0-mobile-ui` 就是现在这套单目录 CLI + VS Code 兼容 + 移动端增强版。

## 安全警告

当前版本的手机端任务默认以完整权限运行：

```bash
codex exec --dangerously-bypass-approvals-and-sandbox resume ...
```

这意味着拿到网页 token 的人可以通过你的服务器执行高权限操作。不要把 URL 发给不可信的人，不要把 `token.txt` 提交到 GitHub。

如果要公开部署，建议至少做这些事：

- 使用强 token，定期删除 `token.txt` 重新生成。
- 放在自己可信的服务器上。
- 优先使用 Cloudflare Zero Trust、VPN、反向代理鉴权或 SSH tunnel。
- 不要把 quick tunnel 当作生产级鉴权。

## 功能

- 手机端会话列表，支持选择不同 Codex session。
- 读取 `~/.codex/state_5.sqlite` 和 rollout JSONL 显示历史消息。
- 手机输入通过 `codex exec resume` 发送到选中的会话。
- 自动发现常见路径下的 Codex CLI，包括 nvm 安装路径。
- 支持复制 `codex resume <session_id>` 命令，方便电脑端重新打开指定会话。
- 支持复制用户消息、Codex 回复和网页任务输出。
- 支持 Markdown 渲染，包括代码块、列表、引用、链接和表格。
- 支持在手机端修改会话标题；标题会保存在浏览器本地，并尝试写回 Codex state DB。
- 支持左滑隐藏目录项；隐藏状态保存在浏览器本地，不删除任何 Codex 本地文件。
- 支持折叠查看隐藏会话并逐个恢复。
- 桌面端目录栏可拖拽调整宽度，移动端目录栏全屏展示。
- 后台 job 状态展示：排队、运行、失败。
- 刷新时不强制滚动到底部，方便在手机上阅读历史。
- systemd 用户服务保活，SSH 断开后继续运行。
- Cloudflare quick tunnel 支持公网访问。

## 环境要求

- Linux
- Python 3.10+
- Codex CLI 已安装并已登录
- 可读取 `~/.codex/state_5.sqlite` 和 `~/.codex/sessions`
- 可选：`cloudflared`
- 可选：`systemd --user`

默认 Codex CLI 会自动尝试多个常见位置，例如：

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

## 快速启动

```bash
cd codex-mobile
chmod +x *.sh
./start.sh
```

服务启动后会在当前目录自动生成：

```text
token.txt
```

本地访问：

```text
http://127.0.0.1:8787/?token=<token>
```

## 公网 quick tunnel

先安装 `cloudflared`，然后放到：

```text
bin/cloudflared
```

或者让它在 `PATH` 里可执行。

启动公开访问：

```bash
./run_public.sh
```

脚本会输出类似：

```text
https://xxxxx.trycloudflare.com/?token=...
```

手机打开这个 URL 即可。

注意：Cloudflare quick tunnel 的域名是临时的，进程重启后可能变化。需要固定域名时，请改用 Cloudflare named tunnel。

## systemd 用户服务

安装并启动网页服务：

```bash
./install_systemd_user.sh
```

如果 `bin/cloudflared` 存在，脚本也会安装 tunnel 服务。

查看状态：

```bash
./status_public.sh
./status_service.sh
```

停止服务：

```bash
./stop_public.sh
```

手动查看 systemd：

```bash
systemctl --user status codex-mobile-server.service
systemctl --user status codex-mobile-tunnel.service
```

为了让用户服务在完全退出 SSH 后继续运行，需要开启 linger：

```bash
loginctl enable-linger "$USER"
```

如果没有权限，请让管理员执行。

## 使用方式

1. 在电脑或服务器上启动服务。
2. 手机打开带 token 的 URL。
3. 左上角菜单选择会话。
4. 在输入框输入指令，点击发送。
5. 结果完成后会进入同一个 Codex 会话历史。

手机端默认会优先选择当前 VS Code/Codex 加载的会话；如果没有，就选择最新会话。你也可以手动切换会话。

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
server.log
tunnel.log
*.pid
job_outputs/
```

这些都已经在 `.gitignore` 中排除。

## 推到 GitHub

```bash
cd codex-mobile
git init
git add .
git commit -m "Initial Codex Mobile bridge"
git branch -M main
git remote add origin git@github.com:<your-name>/<repo-name>.git
git push -u origin main
```

推送前检查不要包含敏感文件：

```bash
git status --short
git ls-files | grep -E 'token|\\.log|\\.pid|job_outputs|cloudflared' || true
```

## 常见问题

### 手机页面能打开，但发送没有结果

检查 Codex CLI 是否可用：

```bash
codex --version
codex exec --help
```

检查服务日志：

```bash
journalctl --user -u codex-mobile-server.service -f
```

### SSH 断开后网页不可用

确认 systemd 用户服务和 linger：

```bash
systemctl --user status codex-mobile-server.service
loginctl show-user "$USER" -p Linger
```

### URL 变了

quick tunnel 是临时 URL。需要固定 URL，请使用 Cloudflare named tunnel 或自己的反向代理。
