#!/bin/bash
# Activate venv, install requirements, and run main.py with correct interpreter
dir="$(dirname "$0")"
cd "$dir"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  pip install psutil
fi

.venv/bin/python main.py
