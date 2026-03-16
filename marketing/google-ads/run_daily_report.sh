#!/bin/bash
# Google Ads 日次レポート + LINE通知
# cron: 3 8 * * * /Users/Mac_air/Desktop/Claude\ Workspace/marketing/google-ads/run_daily_report.sh

cd "$(dirname "$0")"
export PATH="/usr/local/bin:/usr/bin:/bin:/Users/Mac_air/Library/Python/3.9/bin:$PATH"

python3 report.py --notify >> /tmp/google-ads-report.log 2>&1
