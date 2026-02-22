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

### vLLM (optional, for image generation on Linux/CUDA)

Ollama's image generation backend uses MLX and is macOS-only. On Linux with an NVIDIA GPU, use vLLM via Docker instead.

#### 1. Install Docker & NVIDIA Container Toolkit

```bash
# Install Docker Engine
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo usermod -aG docker $USER && newgrp docker

# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

# Configure Docker for GPU
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

#### 2. Create the vLLM systemd user service

```bash
mkdir -p ~/.config/systemd/user/
```

Create `~/.config/systemd/user/vllm.service`:

```ini
[Unit]
Description=vLLM Docker Container
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStartPre=-/usr/bin/docker stop vllm-server
ExecStartPre=-/usr/bin/docker rm vllm-server
ExecStart=/usr/bin/docker run --name vllm-server \
    --gpus all \
    -p 8000:8000 \
    -v %h/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:latest \
    --model facebook/opt-125m
ExecStop=/usr/bin/docker stop vllm-server

[Install]
WantedBy=default.target
```

#### 3. Enable linger and start the service

```bash
sudo loginctl enable-linger $USER

systemctl --user daemon-reload
systemctl --user enable vllm.service
systemctl --user start vllm.service
```

#### Useful commands

```bash
systemctl --user status vllm
journalctl --user -u vllm -f
systemctl --user restart vllm
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
