#!/bin/bash
# TrustLink 日次レポート自動生成（毎朝実行）

cd "$(dirname "$0")"

# 前日の日付（JST基準）
export TZ=Asia/Tokyo
if [ "$(uname)" = "Darwin" ]; then
    SINCE=$(date -v-1d +%Y-%m-%d)
else
    SINCE=$(date -d "yesterday" +%Y-%m-%d)
fi

echo "$(date): 日次レポート生成 ($SINCE)" >> exports/cron.log
./venv/bin/python report.py --since "$SINCE" --until "$SINCE" --notify --no-csv --no-html >> exports/cron.log 2>&1
RC=$?
echo "$(date): 完了 (rc=$RC)" >> exports/cron.log
exit $RC
