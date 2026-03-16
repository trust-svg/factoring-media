#!/bin/bash
# Sync deal-watcher code + eBay DB to ~/Services/deal-watcher
SRC="$HOME/Desktop/Claude Workspace/products/deal-watcher"
DST="$HOME/Services/deal-watcher"
EBAY_SRC="$HOME/Desktop/Claude Workspace/products/ebay-agent/agent.db"

# First update local eBay DB copy
if [ -f "$EBAY_SRC" ]; then
    cp "$EBAY_SRC" "$SRC/ebay_agent.db"
fi

# Copy code (exclude venv, deal_watcher.db, logs)
rsync -a --exclude='venv' --exclude='deal_watcher.db' --exclude='logs' --exclude='__pycache__' "$SRC/" "$DST/"

# Restart service
launchctl unload ~/Library/LaunchAgents/com.trustlink.deal-watcher.plist 2>/dev/null
sleep 1
launchctl load ~/Library/LaunchAgents/com.trustlink.deal-watcher.plist

echo "Deployed and restarted deal-watcher"
