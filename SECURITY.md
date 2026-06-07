# Security

Codex Mobile exposes a remote control surface for Codex sessions.

The default backend command currently runs Codex with full permissions:

```bash
codex exec --dangerously-bypass-approvals-and-sandbox resume ...
```

Treat the generated URL and `token.txt` as secrets.

Do not publish:

- `token.txt`
- `*.log`
- `*.pid`
- `job_outputs/`
- `bin/cloudflared`

Recommended production hardening:

- Put the service behind VPN, Cloudflare Access, or another authenticated reverse proxy.
- Rotate `token.txt` periodically.
- Prefer a named tunnel or authenticated proxy over anonymous quick tunnels.
- Review `server.py` before enabling it on shared machines.

