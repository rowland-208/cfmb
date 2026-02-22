# cfmb
Discord bot for Cape Fear Makers Guild

## Deployment

### Prerequisites

Install [uv](https://docs.astral.sh/uv/) (Python package manager):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install [Ollama](https://ollama.com/) (local LLM runtime):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Systemd User Service

Running as a user service avoids needing `sudo` for service management.

#### 1. Create the service file

```bash
mkdir -p ~/.config/systemd/user/
```

Create `~/.config/systemd/user/cfmb.service`:

```ini
[Service]
WorkingDirectory=/home/<user>/repos/cfmb
ExecStart=/bin/bash -c 'source /home/<user>/.cfmb && /home/<user>/repos/cfmb/.venv/bin/python -m cfmb.bot'
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Replace `<user>` with your username. The `.cfmb` file should export all required environment variables (see `env/` for required vars).

#### 2. Enable linger so the service starts at boot

```bash
sudo loginctl enable-linger <user>
```

Without this, the service only runs while you are logged in.

#### 3. Enable and start the service

```bash
systemctl --user daemon-reload
systemctl --user enable cfmb
systemctl --user start cfmb
```

#### Useful commands

```bash
systemctl --user status cfmb
systemctl --user restart cfmb
journalctl --user -u cfmb -f
```

---

### Auto-update via Cron

`update.sh` pulls the latest code and restarts the service. It waits for any
in-progress LLM request to finish before restarting (via `/tmp/cfmb_active`).

#### Add the cron job

```bash
crontab -e
```

Add this line:

```
*/10 * * * * /home/<user>/repos/cfmb/update.sh >> /var/log/cfmb-update.log 2>&1
```

#### Verify

```bash
crontab -l
tail -f /var/log/cfmb-update.log
```
