#!/bin/bash
set -e
export PATH="$HOME/.local/bin:/snap/bin:$PATH"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
cd "$(dirname "$0")"

output=$(git pull)
echo "$output"
if echo "$output" | grep -q "Already up to date."; then
    echo "Already up to date, skipping update."
    exit 0
fi

if [ -f /tmp/cfmb_active ]; then
    echo "Bot is processing a request, aborting update."
    exit 0
fi

source .venv/bin/activate
uv pip install -r requirements.txt
systemctl --user restart cfmb.service
