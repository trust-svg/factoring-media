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
    "video-analyzer"
    "furima-backend"
    "furima-pwa"
    "saimu-web"
    "saimu-x-auto"
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

check_log_freshness "バックアップ(db成果物)" \
    "/opt/backups/db/ebay-agent.db" \
    "$STALE_HOURS_CRON"

# 週次ジョブ
check_log_freshness "セキュリティチェック" \
    "/var/log/security-check.log" \
    "$STALE_HOURS_WEEKLY"

check_log_freshness "Sion分析" \
    "/var/log/sion-analysis.log" \
    "$STALE_HOURS_WEEKLY"

# saimu-x-auto Threads自動投稿（APScheduler: 07:30/12:30/19:00 JST）
# 19:00→翌07:30 で最大 12.5h ギャップなので閾値は 16h（3.5h grace）
check_saimu_xauto_threads() {
    if ! docker ps --format '{{.Names}}' | grep -q "^saimu-x-auto$"; then
        return  # コンテナ停止は上でチェック済み
    fi

    # 直近16時間のDockerログから投稿成功を確認
    local recent_logs
    recent_logs=$(docker logs saimu-x-auto --since 16h 2>&1)

    # 致命的エラー検出
    local error_pattern='credit balance is too low|authentication_error|invalid x-api-key|insufficient_quota|OAuthException|invalid access_token|expired access_token'
    if echo "$recent_logs" | grep -qiE "$error_pattern"; then
        local sample
        sample=$(echo "$recent_logs" | grep -iE "$error_pattern" | head -1 | head -c 200)
        ERRORS+=("Threads投稿: 直近ログで致命的エラー — ${sample}")
        return
    fi

    # 投稿成功マーカーチェック（saimu-x-autoは "投稿成功" をログ出力）
    if ! echo "$recent_logs" | grep -q "投稿成功"; then
        ERRORS+=("Threads投稿: 直近16時間に <b>投稿成功なし</b>（saimu-x-auto ログ確認）")
    fi
}
check_saimu_xauto_threads

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
# 5. コンテナ image 古さチェック
# =============================================================================
# git pull だけで完了報告して再ビルド忘れる事故の再発防止
# (2026-05-09 ai-uranai で 8 日間旧コード稼働した事故から)
check_container_image_age() {
    local container="$1"
    local max_days="$2"

    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        return
    fi

    local image_id
    image_id=$(docker inspect "$container" --format '{{.Image}}' 2>/dev/null)
    [ -z "$image_id" ] && return

    local image_created
    image_created=$(docker inspect "$image_id" --format '{{.Created}}' 2>/dev/null)
    [ -z "$image_created" ] && return

    local created_epoch
    created_epoch=$(date -d "$image_created" +%s 2>/dev/null || echo "0")
    [ "$created_epoch" = "0" ] && return

    local age_days=$(( (NOW - created_epoch) / 86400 ))
    local image_date
    image_date=$(date -d "$image_created" +%Y-%m-%d 2>/dev/null || echo "unknown")

    if [ "$age_days" -gt "$max_days" ]; then
        WARNINGS+=("Image: <b>${container}</b> の image が${max_days}日超過 (作成: ${image_date})。git pullのみで再ビルド忘れの可能性")
    fi
}

# 自社開発コンテナ (頻繁に更新されるべき)
check_container_image_age "ai-uranai" 14
check_container_image_age "ebay-agent" 14
check_container_image_age "zinq" 14
check_container_image_age "threads-auto" 14
check_container_image_age "factoring-media" 30
check_container_image_age "faxcel-x-auto" 30

# =============================================================================
# 6. メモリチェック
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

# 通常時のサマリ MSG（REPORT_ONLY 用 / 差分通知の補足にも使う）
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
else
    MSG="✅ VPS ヘルスチェック OK ($(date '+%Y-%m-%d %H:%M JST'))"
fi

# REPORT_ONLY モード: 差分関係なくサマリを stdout に吐いて終了（夜間QA等から呼ばれる用）
if [ "${HEALTHCHECK_REPORT_ONLY:-0}" = "1" ]; then
    printf '%b\n' "$MSG"
    log "REPORT_ONLY: ${#ERRORS[@]} errors, ${#WARNINGS[@]} warnings"
    exit 0
fi

# =============================================================================
# 状態差分検出（A案）: 同じ警告を30分毎に通知し続けないよう、
# 「新規発生」「復旧」したものだけ Telegram に送る
# =============================================================================
STATE_DIR="/var/lib/healthcheck"
STATE_FILE="$STATE_DIR/last_state.txt"
mkdir -p "$STATE_DIR"

# 現在の状態スナップショット（ERR / WARN ごと sort -u）
CURRENT_SNAPSHOT=$({
    for e in "${ERRORS[@]}"; do echo "ERR|$e"; done
    for w in "${WARNINGS[@]}"; do echo "WARN|$w"; done
} | sort -u)

PREVIOUS_SNAPSHOT=""
if [ -f "$STATE_FILE" ]; then
    PREVIOUS_SNAPSHOT=$(cat "$STATE_FILE")
fi

# diff: 新規発生 / 復旧
NEW_ITEMS=$(comm -23 <(echo "$CURRENT_SNAPSHOT") <(echo "$PREVIOUS_SNAPSHOT"))
RESOLVED_ITEMS=$(comm -13 <(echo "$CURRENT_SNAPSHOT") <(echo "$PREVIOUS_SNAPSHOT"))

# 状態変化なし → 通知 skip（ログのみ）
if [ -z "$NEW_ITEMS" ] && [ -z "$RESOLVED_ITEMS" ]; then
    log "NO CHANGE: ${#ERRORS[@]} errors, ${#WARNINGS[@]} warnings — notify skipped"
    echo "$CURRENT_SNAPSHOT" > "$STATE_FILE"
    exit 0
fi

# 状態変化あり → 差分メッセージを構築
# pipefail 環境で空マッチ時の grep -c は exit 1 を返すため || true で吸収
NEW_COUNT=$(printf '%s\n' "$NEW_ITEMS" | grep -c . || true)
RES_COUNT=$(printf '%s\n' "$RESOLVED_ITEMS" | grep -c . || true)

DIFF_MSG="🔄 <b>VPS ヘルスチェック 状態変化</b>\n"
DIFF_MSG+="$(date '+%Y-%m-%d %H:%M JST')\n\n"

if [ "$NEW_COUNT" -gt 0 ]; then
    DIFF_MSG+="🆕 <b>新規発生 (${NEW_COUNT}件)</b>\n"
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        kind="${line%%|*}"
        msg="${line#*|}"
        if [ "$kind" = "ERR" ]; then
            DIFF_MSG+="  • ❌ ${msg}\n"
        else
            DIFF_MSG+="  • ⚠️ ${msg}\n"
        fi
    done <<< "$NEW_ITEMS"
    DIFF_MSG+="\n"
fi

if [ "$RES_COUNT" -gt 0 ]; then
    DIFF_MSG+="✅ <b>復旧 (${RES_COUNT}件)</b>\n"
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        msg="${line#*|}"
        DIFF_MSG+="  • ${msg}\n"
    done <<< "$RESOLVED_ITEMS"
    DIFF_MSG+="\n"
fi

# 継続中の件数を補足
if [ "$TOTAL_ISSUES" -gt 0 ]; then
    PERSIST=$(( TOTAL_ISSUES - NEW_COUNT ))
    [ "$PERSIST" -lt 0 ] && PERSIST=0
    DIFF_MSG+="📌 現在: ${TOTAL_ISSUES}件 (継続中 ${PERSIST}件)"
fi

send_telegram "$DIFF_MSG"
log "ALERT (diff): new=${NEW_COUNT} resolved=${RES_COUNT} total=${TOTAL_ISSUES}"

# 状態保存
echo "$CURRENT_SNAPSHOT" > "$STATE_FILE"
exit 0
