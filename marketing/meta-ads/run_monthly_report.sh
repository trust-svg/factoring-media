#!/bin/bash
# TrustLink 月次レポート自動生成（毎月1日実行）

cd "$(dirname "$0")"
source venv/bin/activate

# 前月の開始日・終了日を計算
if [ "$(uname)" = "Darwin" ]; then
    SINCE=$(date -v-1m -v1d +%Y-%m-%d)
    UNTIL=$(date -v1d -v-1d +%Y-%m-%d)
else
    SINCE=$(date -d "last month" +%Y-%m-01)
    UNTIL=$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m-%d)
fi

echo "$(date): 月次レポート生成 ($SINCE 〜 $UNTIL)" >> exports/cron.log
python report.py --since "$SINCE" --until "$UNTIL" --notify >> exports/cron.log 2>&1
echo "$(date): 完了" >> exports/cron.log
