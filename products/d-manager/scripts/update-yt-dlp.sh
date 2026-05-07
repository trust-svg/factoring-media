#!/bin/bash
# Daily yt-dlp update inside the video-analyzer container.
#
# YouTube changes its player JS frequently and yt-dlp ships fixes within hours.
# Pinning the Dockerfile version means a working analyzer breaks days later.
# Running pip install in the live container's writable layer survives `restart`
# but is wiped on rebuild — so a Dockerfile rebuild gives a clean baseline and
# the cron tops it up daily.
#
# Deployed on VPS at /root/d-manager/scripts/update-yt-dlp.sh and called from
# crontab. Logs to /var/log/yt-dlp-update.log.

set -euo pipefail

LOG=/var/log/yt-dlp-update.log
exec >>"$LOG" 2>&1

echo "----- $(date -Iseconds) -----"

cd /root/d-manager

if ! docker compose ps video-analyzer --status running | grep -q video-analyzer; then
  echo "video-analyzer not running; aborting"
  exit 1
fi

OLD=$(docker exec video-analyzer pip show yt-dlp 2>/dev/null | awk '/^Version:/{print $2}')
echo "current: $OLD"

docker exec video-analyzer pip install --no-cache-dir -U --quiet "yt-dlp[default]"

NEW=$(docker exec video-analyzer pip show yt-dlp 2>/dev/null | awk '/^Version:/{print $2}')
echo "after:   $NEW"

if [ "$OLD" != "$NEW" ]; then
  echo "version changed; restarting"
  docker compose restart video-analyzer
else
  echo "no change; skip restart"
fi

echo "done"
