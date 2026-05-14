# 月次リポジトリ棚卸し Ritual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 毎月1日 09:00 JST に Claude Code リポジトリの「未使用スキル」「古いメモリ」「処理速度ボトルネック」を自動診断し、Obsidian にレポート + Telegram 通知を出す月次棚卸し ritual を稼働させる。

**Architecture:** CronCreate routine (`0 9 1 * *`) で agent を発火 → prompt（`~/.claude/commands/monthly-cleanup.md`）が3監査を実行 → 補助スクリプト（`~/.claude/scripts/monthly-cleanup.sh`）で JSONLログ集計とSSoT 4ソース再監査 → Obsidian Daily にレポート出力 → 新規 Telegram 汎用Bot で通知。判定だけして人間承認まで自動削除はしない (quarantine pattern)。

**Tech Stack:** Claude Code slash commands (`~/.claude/commands/*.md`), Claude Code scheduled task (`CronCreate`), Bash helper script, Telegram Bot API (BotFather新規作成), Obsidian Daily Note

**Spec:** [`docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md`](../specs/2026-05-14-monthly-cleanup-ritual-design.md)

---

## File Structure

| ファイル | 役割 | 状態 |
|---------|------|------|
| `~/.claude/commands/monthly-cleanup.md` | 棚卸し prompt 本体 + `/monthly-cleanup` slash command | 新規作成 |
| `~/.claude/scripts/monthly-cleanup.sh` | JSONLログ集計・ファイル行数測定の補助 | 新規作成 |
| `~/.claude/.telegram-meta-bot.env` | 新規 Telegram Bot の token + chat_id（gitignore） | 新規作成 |
| `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_meta_bot.md` | Bot 設定の memory（Telegram credentials の参照先） | 新規作成 |
| `~/Obsidian/Daily/repo-cleanup-YYYY-MM-DD.md` | 月次レポート出力先（実行時に生成） | 実行時生成 |
| CronCreate routine | スケジュール `0 9 1 * *` (Asia/Tokyo) | Claude Code セッション内に登録 |

---

### Task 1: 新規 Telegram Bot を BotFather で作成（Hiro 手作業 + memory 登録）

**Files:**
- Create: `/Users/Mac_air/.claude/.telegram-meta-bot.env`
- Create: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_meta_bot.md`
- Modify: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md`

- [ ] **Step 1: BotFather で新規Bot作成（Hiro手作業）**

Telegram で `@BotFather` に以下を順番に送信:

```
/newbot
<Bot表示名: Claude Cleanup Bot>
<Bot username: hiro_meta_trustlink_bot>  ← 末尾 _bot 必須、衝突したら別名
```

BotFather から返ってくる **HTTP API token** をコピー（例: `12345:ABCdef...`）。

- [ ] **Step 2: chat_id 取得**

新規Botに Hiro が個人チャットで `/start` を送る → 以下で chat_id 取得:

```bash
TOKEN="<取得したtoken>"
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | jq '.result[].message.chat.id'
```

返ってきた数字（例: `323107833`）が chat_id。

- [ ] **Step 3: credentials を .env に保存**

`/Users/Mac_air/.claude/.telegram-meta-bot.env` を以下の内容で Write（**値はチャットに出力しない、ファイル書き込みのみ**）:

```bash
# Telegram 汎用メタ運用Bot (spec #1 / spec #5 / spec #4 で共用)
TELEGRAM_META_BOT_TOKEN=<step1で取得したtoken>
TELEGRAM_META_BOT_CHAT_ID=<step2で取得したchat_id>
```

権限を 600 に:

```bash
chmod 600 /Users/Mac_air/.claude/.telegram-meta-bot.env
```

- [ ] **Step 4: .gitignore 確認**

```bash
grep -n "\.telegram-meta-bot" /Users/Mac_air/.claude/.gitignore 2>/dev/null
```

無ければ追記:

```bash
echo ".telegram-meta-bot.env" >> /Users/Mac_air/.claude/.gitignore
```

- [ ] **Step 5: memory に Bot 設定の参照を追加**

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_meta_bot.md` を以下で Write:

```markdown
---
name: Telegram 汎用メタ運用Bot
description: spec #1/#4/#5 共用の通知Bot（cleanup/dreams/x-intake）。Token/Chat IDは ~/.claude/.telegram-meta-bot.env
type: feedback
scope: workspace
trigger_count: 1
last_confirmed: 2026-05-14
---

## Telegram 汎用メタ運用Bot

spec #1 (月次棚卸し) / spec #5 (Dreams 週次) / spec #4 (X取り込み) で共用。

### 場所

- credentials: `~/.claude/.telegram-meta-bot.env`（gitignore、chmod 600）
- 参照方法: `source ~/.claude/.telegram-meta-bot.env`

### 既存Botとの分離

- eBay用 `@bmanager_trustlink_bot` (323107833) と分離。Bot ID は別物
- 通知の混線を避けるため、メタ運用通知はこの Bot に集約

### 通知例

```bash
source ~/.claude/.telegram-meta-bot.env
curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
  -d "text=📋 月次棚卸しレポート出ました: <Obsidian path>"
```
```

- [ ] **Step 6: MEMORY.md にポインタ追加**

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md` の通知ルートに関する箇所（Telegram 関連の節）に1行追記:

```markdown
- [Telegram 汎用メタ運用Bot](feedback_meta_bot.md) — spec #1/#4/#5 共用、credentials `~/.claude/.telegram-meta-bot.env`
```

- [ ] **Step 7: 動作テスト（送信確認）**

```bash
source /Users/Mac_air/.claude/.telegram-meta-bot.env
curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
  -d "text=✅ メタ運用Bot 動作確認 $(date +%F\ %T)"
```

Expected: Telegram に「✅ メタ運用Bot 動作確認 ...」が届く。届かなければ token/chat_id を再確認。

- [ ] **Step 8: Commit（memory のみ、credentials は除外）**

```bash
git -C /Users/Mac_air/.claude add projects/-Users-Mac-air-Claude-Workspace/memory/feedback_meta_bot.md projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md
git -C /Users/Mac_air/.claude status   # .telegram-meta-bot.env が出ていないことを確認
git -C /Users/Mac_air/.claude commit -m "feat(memory): register Telegram meta-ops bot for spec #1/#4/#5 notifications"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 2: 補助スクリプト `~/.claude/scripts/monthly-cleanup.sh` 作成

**Files:**
- Create: `/Users/Mac_air/.claude/scripts/monthly-cleanup.sh`

- [ ] **Step 1: scripts/ ディレクトリ確認**

```bash
ls -la /Users/Mac_air/.claude/scripts/ 2>/dev/null | head -5
```

無ければ `mkdir -p /Users/Mac_air/.claude/scripts`。

- [ ] **Step 2: スクリプトを Write**

`/Users/Mac_air/.claude/scripts/monthly-cleanup.sh` を以下で作成:

```bash
#!/bin/bash
# 月次棚卸し補助スクリプト (spec #1)
# Usage:
#   monthly-cleanup.sh skills-90days       # 90日未使用スキル候補列挙
#   monthly-cleanup.sh memory-180days      # 180日未更新memory列挙
#   monthly-cleanup.sh bottleneck          # 行数・件数の閾値チェック
#   monthly-cleanup.sh notify <text>       # Telegram 汎用Botへ通知

set -euo pipefail

WORKSPACE_LOG_DIR="/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace"
SKILLS_DIR="/Users/Mac_air/.claude/skills"
MEMORY_DIR="${WORKSPACE_LOG_DIR}/memory"
OBSIDIAN_CONTEXT="/Users/Mac_air/Obsidian/context"
ENV_FILE="/Users/Mac_air/.claude/.telegram-meta-bot.env"

cmd_skills_90days() {
  # 直近90日 JSONLログでヒットしないskillを列挙
  local cutoff="$(date -v-90d +%Y-%m-%d)"
  echo "# 90日未使用スキル候補 (cutoff: $cutoff)"
  for skill_dir in "${SKILLS_DIR}"/*/; do
    [ -d "$skill_dir" ] || continue
    local skill_name
    skill_name="$(basename "$skill_dir")"
    # .archive/ 配下はスキップ
    [[ "$skill_name" == ".archive" ]] && continue
    # JSONLログ全体でskill名が出現するか確認
    if ! find "${WORKSPACE_LOG_DIR}" -name '*.jsonl' -newermt "$cutoff" -exec grep -l "$skill_name" {} \; 2>/dev/null | head -1 | grep -q .; then
      # 内部呼び出し（他SKILL.md内）チェック
      local internal_refs
      internal_refs="$(grep -l "$skill_name" "${SKILLS_DIR}"/*/SKILL.md 2>/dev/null | grep -v "$skill_dir" | wc -l | tr -d ' ')"
      echo "- ${skill_name} (内部依存: ${internal_refs}件)"
    fi
  done
}

cmd_memory_180days() {
  # 180日以上更新されていないmemory/contextファイル列挙
  echo "# 180日未更新 memory/context ファイル"
  for dir in "$MEMORY_DIR" "$OBSIDIAN_CONTEXT"; do
    [ -d "$dir" ] || continue
    find "$dir" -maxdepth 1 -name '*.md' -mtime +180 -print 2>/dev/null | while read -r f; do
      local first_line
      first_line="$(head -1 "$f")"
      echo "- $f — $first_line"
    done
  done
}

cmd_bottleneck() {
  # 行数閾値チェック
  echo "# 処理速度ボトルネック診断"
  declare -A files=(
    ["/Users/Mac_air/.claude/CLAUDE.md"]="200:300"
    ["/Users/Mac_air/Claude-Workspace/CLAUDE.md"]="200:300"
    ["${MEMORY_DIR}/MEMORY.md"]="150:180"
  )
  for f in "${!files[@]}"; do
    [ -f "$f" ] || continue
    local lines warn crit
    lines="$(wc -l < "$f" | tr -d ' ')"
    warn="${files[$f]%%:*}"
    crit="${files[$f]##*:}"
    if [ "$lines" -ge "$crit" ]; then
      echo "🔴 $f: ${lines}行 (CRITICAL ≥${crit})"
    elif [ "$lines" -ge "$warn" ]; then
      echo "⚠️ $f: ${lines}行 (warning ≥${warn})"
    else
      echo "✅ $f: ${lines}行"
    fi
  done
  # permissions.allow 件数
  local allow_count
  allow_count="$(jq '.permissions.allow | length' /Users/Mac_air/.claude/settings.json 2>/dev/null || echo "n/a")"
  echo "- permissions.allow: ${allow_count}件 (warn≥80, crit≥150)"
}

cmd_notify() {
  local text="$1"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
    --data-urlencode "text=${text}" > /dev/null
}

case "${1:-}" in
  skills-90days) cmd_skills_90days ;;
  memory-180days) cmd_memory_180days ;;
  bottleneck) cmd_bottleneck ;;
  notify) shift; cmd_notify "$*" ;;
  *) echo "Usage: $0 {skills-90days|memory-180days|bottleneck|notify <text>}"; exit 1 ;;
esac
```

- [ ] **Step 3: 実行権限付与**

```bash
chmod +x /Users/Mac_air/.claude/scripts/monthly-cleanup.sh
```

- [ ] **Step 4: 個別動作確認（bottleneck だけ）**

```bash
/Users/Mac_air/.claude/scripts/monthly-cleanup.sh bottleneck
```

Expected: ✅/⚠️/🔴 マーク付きで4行程度（CLAUDE.md / Workspace CLAUDE.md / MEMORY.md / permissions.allow）が出る。

- [ ] **Step 5: skills-90days 動作確認**

```bash
/Users/Mac_air/.claude/scripts/monthly-cleanup.sh skills-90days | head -20
```

Expected: `# 90日未使用スキル候補` から始まる出力。エラーで止まらないこと。

- [ ] **Step 6: memory-180days 動作確認**

```bash
/Users/Mac_air/.claude/scripts/monthly-cleanup.sh memory-180days | head -20
```

Expected: `# 180日未更新 memory/context ファイル` から始まる出力。

- [ ] **Step 7: notify 動作確認（任意・送信される）**

```bash
/Users/Mac_air/.claude/scripts/monthly-cleanup.sh notify "🧪 monthly-cleanup.sh notify テスト"
```

Expected: Telegram 汎用Bot に通知到達。

- [ ] **Step 8: Commit**

```bash
git -C /Users/Mac_air/.claude add scripts/monthly-cleanup.sh
git -C /Users/Mac_air/.claude commit -m "feat: add monthly-cleanup.sh helper for spec #1 audits"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 3: `/monthly-cleanup` slash command 実装

**Files:**
- Create: `/Users/Mac_air/.claude/commands/monthly-cleanup.md`

- [ ] **Step 1: commands/ ディレクトリ確認**

```bash
ls /Users/Mac_air/.claude/commands/ 2>/dev/null | head -5
```

無ければ `mkdir -p /Users/Mac_air/.claude/commands`。

- [ ] **Step 2: prompt を Write**

`/Users/Mac_air/.claude/commands/monthly-cleanup.md` を以下で作成:

```markdown
---
description: 月次リポジトリ棚卸し（spec #1）— 3監査 + Obsidianレポート + Telegram通知
---

あなたは月次リポジトリ棚卸し agent です。
spec: `~/Claude-Workspace/docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md`

引数: $ARGUMENTS （`dry-run` を含むとTelegram通知だけスキップ）

## 実施手順

### ① 未使用スキル検出 + Quarantine 提案

補助スクリプトで一覧取得:

```bash
~/.claude/scripts/monthly-cleanup.sh skills-90days
```

出力結果について:
- 「内部依存: 0件」は **新規隔離候補** として実行コマンド付きでレポートに記載
- 「内部依存: 1件以上」は **要確認** セクションで列挙、依存元 SKILL.md パスも併記
- 既に隔離済み（`~/.claude/skills/.archive/<prev-month>/`）で30日経過したものは **完全削除候補**

⚠️ ファイル移動は **絶対に実行しない**。レポートにコピペ可能なコマンドを書くだけ。

### ② 古いメモリ/context 検出 + SSoT 4ソース再監査

#### ②-A 通常 memory/context（180日経過）

```bash
~/.claude/scripts/monthly-cleanup.sh memory-180days
```

#### ②-B SSoT 横断台帳の特別扱い（spec #3 連動）

以下3ファイルは 180日判定の対象外。代わりに毎月 **4ソース再監査** を実行:

| SSoT ファイル | 監査手段 |
|--------------|---------|
| `~/Obsidian/context/ad-accounts.md` | Meta MCP / Google Ads MCP で active アカウント取得・差分検出 |
| `~/Obsidian/context/subscriptions.md` | Hiro にサブスク変動ヒアリング（要確認フィールドの埋め残し） |
| `~/Obsidian/context/cron-inventory.md` | 4ソース再監査: ① `ssh trustlink-prod 'crontab -l && ls -la /etc/cron.d/'` ② `ls ~/Library/LaunchAgents/com.trustlink.*.plist` + `launchctl list \| grep trustlink` ③ `gh workflow list -R trust-svg/<主要repo>` ④ `CronList` ツール |

差分があれば該当ファイルを上書き提案（実行は Hiro 承認後）。`last_confirmed` を当月日付に更新。

### ③ 処理速度ボトルネック診断

```bash
~/.claude/scripts/monthly-cleanup.sh bottleneck
```

出力をそのままレポートに転記。CRITICAL があれば対処手段を明記:
- MEMORY.md CRITICAL → 古い feedback_* を `memory/.archive/YYYY-MM/<item>/` 移動推奨
- CLAUDE.md CRITICAL → 重複セクション削除 or 別ファイルへ分割
- permissions.allow CRITICAL → settings.json の重複/旧パス削除提案

### ④ レポート生成

書き込み先: `/Users/Mac_air/Obsidian/Daily/repo-cleanup-$(date +%F).md`

レポートフォーマット:

```markdown
# 月次リポジトリ棚卸し YYYY-MM-DD

**実行**: <ISO timestamp>
**先月隔離分**: <count>件 / **新規隔離候補**: <count>件 / **CRITICAL**: <count>件

## ① 未使用スキル
### 新規隔離候補（90日未使用 + 内部依存なし）
| スキル | 最終呼び出し | 内部依存 |
|--------|------------|----------|
| ... | なし | なし |

実行コマンド（コピペ）:
\`\`\`bash
mkdir -p ~/.claude/skills/.archive/$(date +%Y-%m)/
mv ~/.claude/skills/<skill> ~/.claude/skills/.archive/$(date +%Y-%m)/
\`\`\`

### 要確認（90日未使用だが内部依存あり）
| スキル | 依存元 |
|--------|--------|
| ... | ... SKILL.md |

### 隔離済み（先月分・30日経過）
- ... → 完全削除候補

## ② 古いメモリ/context
### 通常（180日+ 未更新）
- ...

### SSoT 4ソース再監査
- ad-accounts.md: 差分なし / 差分あり（詳細）
- subscriptions.md: 要確認フィールドの埋め残し N件
- cron-inventory.md: VPS/launchd/GH Actions/CronCreate の追加・削除 N件

## ③ 処理速度ボトルネック
- ✅ ~/.claude/CLAUDE.md: ...
- 🔴 MEMORY.md: ...

## 次月への持ち越し
- ...
```

### ⑤ Telegram 通知

`dry-run` 引数が含まれていなければ:

```bash
~/.claude/scripts/monthly-cleanup.sh notify "📋 月次棚卸しレポート $(date +%F) 出ました
新規隔離候補: <N>件
CRITICAL: <N>件
レポート: ~/Obsidian/Daily/repo-cleanup-$(date +%F).md"
```

### ⑥ 最終出力

ユーザーには以下を返答:
- 生成したObsidianパス
- 隔離候補件数 / CRITICAL件数
- Telegram 通知の到達可否（送信した場合）

## 重要ルール

- **ファイル移動は実行しない**（quarantine pattern、人間承認待ち）
- ログ削除でJSONLが欠落していたら「ログ無いので未使用判定スキップ」と明示
- 偽陽性検出時、Hiroが復活可能な状態を保つ
- 一度の実行で監査結果がゼロ件でも「健全宣言」をレポートに書き、Telegram に通知
```

- [ ] **Step 3: ファイル確認**

```bash
wc -l /Users/Mac_air/.claude/commands/monthly-cleanup.md
```

Expected: 100行前後。

- [ ] **Step 4: Commit**

```bash
git -C /Users/Mac_air/.claude add commands/monthly-cleanup.md
git -C /Users/Mac_air/.claude commit -m "feat: add /monthly-cleanup slash command (spec #1)"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 4: launchd plist でリマインダー登録（月初9:00 JST）

**設計判断**: 実装時に CronCreate の制約（session-only + 7日 auto-expire）と schedule skill (Claude.ai Routines) の remote 実行制約が判明したため、macOS launchd で月初リマインダーだけ送り、Hiro が手動で `/monthly-cleanup` を起動する方式に変更（spec 修正済み 2026-05-14, commit 75504bb）。

**Files:**
- Create: `/Users/Mac_air/.claude/scripts/monthly-cleanup-reminder.sh`
- Create: `/Users/Mac_air/Library/LaunchAgents/com.trustlink.monthly-cleanup-reminder.plist`
- Modify: `/Users/Mac_air/Obsidian/context/cron-inventory.md`

- [ ] **Step 1: リマインダースクリプトを Write**

`/Users/Mac_air/.claude/scripts/monthly-cleanup-reminder.sh`:

```bash
#!/bin/bash
# 月次棚卸しリマインダー (spec #1) — launchd から呼ばれる
# Telegram 汎用Botに通知だけ送る。実際の /monthly-cleanup 起動は Hiro が手動で。

set -euo pipefail

LOG_FILE="/tmp/monthly-cleanup-reminder.log"
ENV_FILE="/Users/Mac_air/.claude/.telegram-meta-bot.env"

{
  echo "=== $(date +%Y-%m-%d\ %H:%M:%S) ==="
  if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found"
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$ENV_FILE"

  MESSAGE="📋 月次リポジトリ棚卸しの時間です ($(date +%Y-%m-%d))

Claude Code で /monthly-cleanup を起動してください。
完了するとレポートが ~/Obsidian/Daily/repo-cleanup-$(date +%F).md に出ます。"

  RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
    --data-urlencode "text=${MESSAGE}")
  echo "Response: $RESPONSE"

  if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo "SUCCESS"
  else
    echo "FAILURE"
    exit 1
  fi
} >> "$LOG_FILE" 2>&1
```

`chmod +x` で実行権限付与。

- [ ] **Step 2: launchd plist を Write**

`/Users/Mac_air/Library/LaunchAgents/com.trustlink.monthly-cleanup-reminder.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.trustlink.monthly-cleanup-reminder</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/Mac_air/.claude/scripts/monthly-cleanup-reminder.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Day</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/monthly-cleanup-reminder.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/monthly-cleanup-reminder.stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/Mac_air</string>
    </dict>
</dict>
</plist>
```

注: VPS ホストTZ は Asia/Tokyo 化済み（memory: vps-timezone.md）だが、launchd は Mac ローカル TZ で動く。Mac の TZ も Asia/Tokyo なら `Hour: 9` がそのまま 09:00 JST になる（要確認: `systemsetup -gettimezone`）。

- [ ] **Step 3: launchd plist を load**

```bash
launchctl load /Users/Mac_air/Library/LaunchAgents/com.trustlink.monthly-cleanup-reminder.plist
launchctl list | grep monthly-cleanup
```

Expected: `com.trustlink.monthly-cleanup-reminder` が一覧に出る（PID 列は `-` でOK、StartCalendarInterval は idle 状態）。

- [ ] **Step 4: 手動発火テスト**

```bash
launchctl start com.trustlink.monthly-cleanup-reminder
sleep 3
cat /tmp/monthly-cleanup-reminder.log | tail -10
```

Expected: `SUCCESS` の行が出る、Telegram に「📋 月次リポジトリ棚卸しの時間です」が届く。届かなければ:
1. `~/.claude/.telegram-meta-bot.env` が正しく書かれているか確認
2. `/tmp/monthly-cleanup-reminder.stderr.log` を確認
3. Telegram API のレスポンスが `"ok":true` か確認

- [ ] **Step 5: cron-inventory.md の launchd セクションを更新**

`/Users/Mac_air/Obsidian/context/cron-inventory.md` の `## launchd (macOS Mac_air)` セクションを Edit。既存テーブル行に追記:

```markdown
| `com.trustlink.monthly-cleanup-reminder` | 月初1日 09:00 JST | 月次棚卸しリマインダー (spec #1) | `/Users/Mac_air/Library/LaunchAgents/com.trustlink.monthly-cleanup-reminder.plist` |
```

`last_confirmed: 2026-05-14` を当日日付に更新。

- [ ] **Step 6: Commit**

```bash
git -C /Users/Mac_air/Obsidian add context/cron-inventory.md
git -C /Users/Mac_air/Obsidian commit -m "docs(context): register monthly-cleanup-reminder launchd (spec #1)"
```

注: Obsidian vault は git管理されている。`~/.claude` は管理外なので、plist と reminder script は commit しない（個別端末固有）。

---

### Task 5: 初回手動実行 + 動作確認

**Files:**
- Create (実行時): `/Users/Mac_air/Obsidian/Daily/repo-cleanup-2026-05-14.md`

- [ ] **Step 1: 手動で `/monthly-cleanup dry-run` を実行**

Claude Code セッションで `/monthly-cleanup dry-run` を起動。Telegram 通知はスキップして agent 動作のみ検証。

Expected:
- 3監査（①②③）が完走
- レポートが `~/Obsidian/Daily/repo-cleanup-2026-05-14.md` に書き込まれる
- 監査結果がゼロ件でも「健全宣言」が出る

- [ ] **Step 2: レポート内容を目視確認**

```bash
ls -la /Users/Mac_air/Obsidian/Daily/repo-cleanup-2026-05-14.md
head -50 /Users/Mac_air/Obsidian/Daily/repo-cleanup-2026-05-14.md
```

Expected: 3セクション構造 + 「実行コマンド（コピペ）」がコードブロックで含まれる。

- [ ] **Step 3: Telegram 通知込みで本実行**

`/monthly-cleanup` を引数なしで実行（dry-run 外す）。Telegram 汎料Bot に通知到達確認。

- [ ] **Step 4: 隔離フォルダの skill discovery 影響確認**

```bash
mkdir -p /Users/Mac_air/.claude/skills/.archive/2026-05-test/
ls -la /Users/Mac_air/.claude/skills/.archive/
```

新規セッションで `.archive/2026-05-test/` 配下のスキルが Claude Code の skill 一覧に出ないことを確認。出てしまったら spec のリスク3 通り、`.archive/` を skill discovery 対象外にする手段を別途検討（settings.json or 命名規約）。テスト後は `rmdir /Users/Mac_air/.claude/skills/.archive/2026-05-test`。

- [ ] **Step 5: 受け入れ基準チェック**

spec § 6 と対応:

- [ ] Telegram Bot が作成され、token/chat_id が `.telegram-meta-bot.env` に保管されている
- [ ] CronCreate に `monthly-cleanup` が登録され `CronList` で確認できる
- [ ] 月初1日 09:00 JST に発火（実発火確認は次月1日に持ち越し可、ただし手動 dry-run でロジックは検証済み）
- [ ] レポートが3セクション構成で出力された
- [ ] Telegram 通知が届いた（要約3行 + Obsidianパス）
- [ ] `/monthly-cleanup` slash command で手動起動できた
- [ ] 初回実行で「最低1件の隔離候補」または「健全宣言」が出た
- [ ] レポートに「実行コマンド（コピペ）」が含まれる
- [ ] `~/.claude/skills/.archive/` が skill discovery 対象外であることを確認した（要検証メモも残す）

- [ ] **Step 6: Commit（Obsidian 側のテストレポート、任意）**

レポートがテスト用と判明する形式なら commit せず、本番月初発火を待つ運用でも可。

---

## 受け入れ基準の検証

spec #1 セクション6 と対応:

- [x] Task 1 で Telegram Bot 作成・credentials 安全保管
- [x] Task 4 で CronCreate 登録、Task 5 Step 5 で確認
- [x] Task 5 で月初発火フローを手動で検証（実発火は次月待ち）
- [x] Task 3 prompt が3セクション構造を強制
- [x] Task 5 で Telegram 通知到達確認
- [x] `/monthly-cleanup` slash command は Task 3 で実装
- [x] Task 5 で初回手動実行
- [x] レポートテンプレに「実行コマンド（コピペ）」を強制（Task 3 prompt §④）
- [x] `.archive/` が skill discovery 対象外であることは Task 5 Step 4 で検証

---

## Self-Review Checklist（plan作成者用）

- [x] spec の全セクション（1-7）がタスクにマッピング済み
- [x] quarantine pattern（移動のみ・人間承認）を Task 3 prompt で明示
- [x] SSoT 特別扱い（spec #3 連動）を Task 3 prompt §②-B に組み込み済み
- [x] BotFather 手作業ステップ（Hiro 介入必須）を Task 1 で明示
- [x] credentials は Task 1 で gitignore 確認、commit 対象外
- [x] 後続 spec #5/#4 が同じ Telegram Bot を使うことを memory に記録（Task 1 Step 5）
