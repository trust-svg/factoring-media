#!/bin/bash
# TrustLink 週次レポート自動生成（毎週月曜実行）

cd "$(dirname "$0")"
source venv/bin/activate

# 前週の月曜〜日曜を計算
if [ "$(uname)" = "Darwin" ]; then
    SINCE=$(date -v-1w -v-mon +%Y-%m-%d)
    UNTIL=$(date -v-1w -v-sun +%Y-%m-%d)
else
    SINCE=$(date -d "last monday -7 days" +%Y-%m-%d)
    UNTIL=$(date -d "last sunday" +%Y-%m-%d)
fi

echo "$(date): 週次レポート生成 ($SINCE 〜 $UNTIL)" >> exports/cron.log
python report.py --since "$SINCE" --until "$UNTIL" --notify >> exports/cron.log 2>&1
echo "$(date): 完了" >> exports/cron.log
