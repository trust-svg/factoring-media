#!/bin/zsh
set -e
REPORTS_DIR="/Users/Mac_air/Claude-Workspace/products/factoring-media/reports"
cd "$REPORTS_DIR"

if [ ! -d "$REPORTS_DIR/venv" ]; then
    python3 -m venv venv
    venv/bin/pip install -q -r requirements.txt
fi

venv/bin/python weekly_report.py
