#!/bin/bash
if [ ! -d venv-main ]; then
    uv venv venv-main --python=python3
fi
source venv-main/bin/activate

uv pip install -r requirements.txt

set -o allexport
source env/main.env
set +o allexport

python -m cfmb.bot

