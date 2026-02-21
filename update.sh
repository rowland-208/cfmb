#!/bin/bash
set -e
git pull
sudo systemctl restart cfmb.service
