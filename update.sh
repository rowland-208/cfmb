#!/bin/bash
set -e

if [ -f /tmp/cfmb_active ]; then
    echo "Bot is processing a request, aborting update."
    exit 0
fi

git pull
source .venv/bin/activate
uv pip install -r requirements.txt
systemctl --user restart cfmb.service
