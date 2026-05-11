#!/bin/bash
# D-Manager launcher — activates venv and starts bot
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Activate virtual environment
source "$DIR/.venv/bin/activate"

# Start bot
exec python main.py
