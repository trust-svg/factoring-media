#!/bin/bash
# =============================================================================
# VPS Health Check — 全定期実行システム監視
# 異常時のみ Telegram 通知（正常時はサイレント）
# =============================================================================

set -euo pipefail

# --- Telegram設定（b-managerのBotを利用） ---
source /opt/apps/claude-workspace/products/b-manager/.env
CHAT_ID="${TELEGRAM_CHAT_ID:-323107833}"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"

# --- 設定 ---
ALERT_LOG="/var/log/healthcheck.log"
STALE_HOURS_CRON=26        # cronログが26時間以上古ければ異常（日次ジョブ用）
STALE_HOURS_WEEKLY=170     # 週次ログは170時間（約7日+2時間）

# --- 変数 ---
ERRORS=()
WARNINGS=()
NOW=$(date +%s)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$ALERT_LOG"
}

send_telegram() {
    local msg="$1"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": $(echo "$msg" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))'), \"parse_mode\": \"HTML\"}" \
        > /dev/null 2>&1
}

# =============================================================================
# 1. Docker コンテナ稼働チェック
# =============================================================================
EXPECTED_CONTAINERS=(
    "ebay-agent"
    "threads-auto"
    "ai-uranai"
    "zinq"
    "caddy"
    "shared-postgres"
    "factoring-media"
    "faxcel-x-auto"
)

RUNNING_CONTAINERS=$(docker ps --format '{{.Names}}' 2>/dev/null)

for container in "${EXPECTED_CONTAINERS[@]}"; do
    if ! echo "$RUNNING_CONTAINERS" | grep -q "^${container}$"; then
        ERRORS+=("Docker: <b>${container}</b> が停止しています")
    fi
done

# PostgreSQL ヘルスチェック
PG_HEALTH=$(docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep shared-postgres || echo "")
if echo "$PG_HEALTH" | grep -q "(unhealthy)"; then
    ERRORS+=("Docker: <b>shared-postgres</b> が unhealthy です")
fi

# =============================================================================
# 2. Cron ジョブのログ鮮度チェック
# =============================================================================
check_log_freshness() {
    local label="$1"
    local logfile="$2"
    local max_hours="$3"

    if [ ! -f "$logfile" ]; then
        WARNINGS+=("ログ: <b>${label}</b> のログが存在しません (${logfile})")
        return
    fi

    local file_age=$(( (NOW - $(stat -c %Y "$logfile" 2>/dev/null || echo "$NOW")) ))
    local max_seconds=$((max_hours * 3600))

    if [ "$file_age" -gt "$max_seconds" ]; then
        local hours_ago=$((file_age / 3600))
        WARNINGS+=("ログ: <b>${label}</b> が ${hours_ago}時間更新されていません")
    fi
}

# 日次cronジョブ
check_log_freshness "eBay在庫監視(VPS)" \
    "/opt/apps/claude-workspace/products/ebay-inventory-tool/logs/vps_cron.log" \
    "$STALE_HOURS_CRON"

check_log_freshness "AIニュース日報" \
    "/root/ai-daily-digest/cron.log" \
    "$STALE_HOURS_CRON"

check_log_freshness "Google Ads日報" \
    "/root/marketing/google-ads/cron.log" \
    "$STALE_HOURS_CRON"

check_log_freshness "Meta Ads日報" \
    "/root/marketing/meta-ads/exports/cron.log" \
    "$STALE_HOURS_CRON"

check_log_freshness "VPSバックアップ" \
    "/var/log/backup.log" \
    "$STALE_HOURS_CRON"

# 週次ジョブ
check_log_freshness "セキュリティチェック" \
    "/var/log/security-check.log" \
    "$STALE_HOURS_WEEKLY"

check_log_freshness "Sion分析" \
    "/var/log/sion-analysis.log" \
    "$STALE_HOURS_WEEKLY"

# =============================================================================
# 3. Docker コンテナのログ最終出力チェック（APSchedulerの生存確認）
# =============================================================================
check_container_log() {
    local container="$1"
    local max_hours="$2"

    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        return  # コンテナ停止は上でチェック済み
    fi

    local last_log
    last_log=$(docker logs --tail 1 --timestamps "$container" 2>&1 | head -1)

    if [ -z "$last_log" ]; then
        WARNINGS+=("ログ: <b>${container}</b> のDockerログが空です")
        return
    fi

    # タイムスタンプを抽出してチェック
    local ts
    ts=$(echo "$last_log" | grep -oP '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' 2>/dev/null || echo "")
    if [ -n "$ts" ]; then
        local log_epoch
        log_epoch=$(date -d "${ts}Z" +%s 2>/dev/null || echo "0")
        local age=$(( NOW - log_epoch ))
        local max_seconds=$((max_hours * 3600))
        if [ "$age" -gt "$max_seconds" ]; then
            local hours_ago=$((age / 3600))
            WARNINGS+=("コンテナ: <b>${container}</b> のログが${hours_ago}時間沈黙中")
        fi
    fi
}

# threads-autoは5分毎ヘルスチェックがあるので1時間でアラート
check_container_log "threads-auto" 1
# 他のコンテナは6時間以内に何かしらログがあるはず
check_container_log "ebay-agent" 6
check_container_log "ai-uranai" 6

# =============================================================================
# 4. ディスク容量チェック
# =============================================================================
DISK_USAGE=$(df / --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
if [ -n "$DISK_USAGE" ] && [ "$DISK_USAGE" -gt 90 ]; then
    ERRORS+=("ディスク: 使用率 <b>${DISK_USAGE}%</b> (90%超過)")
elif [ -n "$DISK_USAGE" ] && [ "$DISK_USAGE" -gt 80 ]; then
    WARNINGS+=("ディスク: 使用率 <b>${DISK_USAGE}%</b> (80%超過)")
fi

# =============================================================================
# 5. メモリチェック
# =============================================================================
MEM_AVAILABLE=$(free -m 2>/dev/null | awk '/^Mem:/ {printf "%.0f", $7/$2*100}')
if [ -n "$MEM_AVAILABLE" ] && [ "$MEM_AVAILABLE" -lt 10 ]; then
    ERRORS+=("メモリ: 空き <b>${MEM_AVAILABLE}%</b> (10%未満)")
elif [ -n "$MEM_AVAILABLE" ] && [ "$MEM_AVAILABLE" -lt 20 ]; then
    WARNINGS+=("メモリ: 空き <b>${MEM_AVAILABLE}%</b> (20%未満)")
fi

# =============================================================================
# 結果判定・通知
# =============================================================================
TOTAL_ISSUES=$(( ${#ERRORS[@]} + ${#WARNINGS[@]} ))

if [ "$TOTAL_ISSUES" -gt 0 ]; then
    MSG="🚨 <b>VPS ヘルスチェック異常検知</b>\n"
    MSG+="$(date '+%Y-%m-%d %H:%M JST')\n\n"

    if [ ${#ERRORS[@]} -gt 0 ]; then
        MSG+="❌ <b>エラー (${#ERRORS[@]}件)</b>\n"
        for err in "${ERRORS[@]}"; do
            MSG+="  • ${err}\n"
        done
        MSG+="\n"
    fi

    if [ ${#WARNINGS[@]} -gt 0 ]; then
        MSG+="⚠️ <b>警告 (${#WARNINGS[@]}件)</b>\n"
        for warn in "${WARNINGS[@]}"; do
            MSG+="  • ${warn}\n"
        done
    fi

    send_telegram "$MSG"
    log "ALERT: ${#ERRORS[@]} errors, ${#WARNINGS[@]} warnings — notified"
else
    log "OK: all checks passed"
fi

exit 0
