#!/bin/bash
set -e

while [ -f /tmp/cfmb_active ]; do
    echo "Bot is processing a request, waiting..."
    sleep 2
done

git pull
sudo systemctl restart cfmb.service
