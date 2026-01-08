#!/bin/bash
if [ ! -d venv ]; then
    uv venv venv --python=python3
fi
source venv/bin/activate

uv pip install -r requirements-test.txt

set -o allexport
source env/test.env
set +o allexport

pytest
