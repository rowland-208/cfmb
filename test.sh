#!/bin/sh
if [ ! -d venv ]; then
    python -m venv venv
    pip install -r requirements-test.txt
fi
source venv/bin/activate

pytest
