#!/bin/bash
if [ ! -d venv-test ]; then
    uv venv venv-test --python=python3
fi
source venv-test/bin/activate

uv pip install -r requirements-test.txt

set -o allexport
source env/test.env
set +o allexport

pytest
