#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -f /tmp/cfmb_active ]; then
    echo "Bot is processing a request, aborting update."
    exit 0
fi

output=$(git pull)
echo "$output"
if echo "$output" | grep -q "Already up to date."; then
    exit 0
fi

source .venv/bin/activate
uv pip install -r requirements.txt
systemctl --user restart cfmb.service
