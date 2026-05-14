# Dreams 週次振り返り Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 毎週土曜 08:00 JST に Claude が直近1週間の作業ログをスキャンし、**判断/ミス/未消化** 3パターンを検出して Obsidian/Daily にレポート + Telegram 通知を出す週次振り返りを稼働させる。

**Architecture:** CronCreate routine (`0 8 * * 6`) で agent を発火 → prompt（`~/.claude/commands/dreams-weekly.md`）が `~/Obsidian/Daily/<過去7日>.md` + `git log --since="7 days ago"` + JSONLログを集約 → 3パターン検出 → 週次レポートを `~/Obsidian/Daily/dreams-YYYY-MM-DD.md` に flow として書き込み → spec #1 と共用の Telegram 汎用Bot で通知。**確定パターン** は Hiro 承認後のみ `~/Obsidian/context/dreams.md` (stock) に追記。

**Tech Stack:** Claude Code slash commands (`~/.claude/commands/*.md`), Claude Code scheduled task (`CronCreate`), Telegram Bot API（spec #1 で作成済みの汎用Bot 共用）, Obsidian Daily Note (flow) + context/dreams.md (stock)

**Spec:** [`docs/superpowers/specs/2026-05-14-dreams-weekly-reflection-design.md`](../specs/2026-05-14-dreams-weekly-reflection-design.md)

**Depends on:** [`2026-05-14-monthly-cleanup.md`](2026-05-14-monthly-cleanup.md) — Telegram 汎用Bot は spec #1 Task 1 で作成済み

---

## File Structure

| ファイル | 役割 | 状態 |
|---------|------|------|
| `~/.claude/commands/dreams-weekly.md` | 週次振り返り prompt 本体 + `/dreams` slash command | 新規作成 |
| `~/Obsidian/context/dreams.md` | 確定パターンDB (stock)。Hiro 承認後のみ追記 | 新規作成（テンプレ） |
| `~/Obsidian/Daily/dreams-YYYY-MM-DD.md` | 週次レポート (flow)。毎週土曜に生成 | 実行時生成 |
| CronCreate routine | スケジュール `0 8 * * 6` (Asia/Tokyo) | Claude Code セッション内に登録 |

---

### Task 1: `~/Obsidian/context/dreams.md` テンプレ作成（stock 確定パターンDB）

**Files:**
- Create: `/Users/Mac_air/Obsidian/context/dreams.md`

- [ ] **Step 1: ファイルを Write**

`/Users/Mac_air/Obsidian/context/dreams.md` を以下で作成:

```markdown
---
type: stock
category: dreams
last_confirmed: 2026-05-14
---

# Dreams 確定パターンDB（SSoT）

Hiro が週次レポート（`Daily/dreams-YYYY-MM-DD.md`）を確認し、**承認したパターンのみ** ここに追記する。
Claude が常時参照する自己観察パターン集。

更新ルール:
- 重複検出時は `trigger_count` を +1、`last_confirmed` を更新
- 完全に陳腐化したパターンは `deprecated: true` を frontmatter に追加し、月次棚卸し (spec #1) で archive 候補

エントリ形式:

\`\`\`markdown
## パターン #NNN: <タイトル>

- **type**: judgment | mistake | unfinished
- **first_detected**: YYYY-MM-DD
- **last_confirmed**: YYYY-MM-DD
- **trigger_count**: N
- **scope**: workspace | skill:<name> | product:<name>

### 詳細
<本文>

### 関連 Gotcha
- feedback_*.md
\`\`\`

## エントリ

（初回は空。週次振り返りで承認されたパターンが累積される）

## 関連 spec

- [`docs/superpowers/specs/2026-05-14-dreams-weekly-reflection-design.md`](../../Claude-Workspace/docs/superpowers/specs/2026-05-14-dreams-weekly-reflection-design.md)
- [`docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md`](../../Claude-Workspace/docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md) — flow/stock 分離原則
```

- [ ] **Step 2: ファイル内容確認**

```bash
wc -l /Users/Mac_air/Obsidian/context/dreams.md
head -10 /Users/Mac_air/Obsidian/context/dreams.md
```

Expected: 40-50行程度、frontmatter が正しく書かれている。

- [ ] **Step 3: Commit**

```bash
git -C /Users/Mac_air/Obsidian add context/dreams.md
git -C /Users/Mac_air/Obsidian commit -m "feat(context): add dreams.md stock template (spec #5)"
```

注: Obsidian vault が git 管理外ならスキップ。

---

### Task 2: `/dreams` slash command 実装

**Files:**
- Create: `/Users/Mac_air/.claude/commands/dreams-weekly.md`

- [ ] **Step 1: commands/ ディレクトリ確認**

```bash
ls /Users/Mac_air/.claude/commands/ 2>/dev/null | head -5
```

- [ ] **Step 2: prompt を Write**

`/Users/Mac_air/.claude/commands/dreams-weekly.md` を以下で作成:

```markdown
---
description: 週次 Dreams 振り返り（spec #5）— 判断/ミス/未消化パターン検出 + Obsidianレポート + Telegram通知
---

あなたは週次振り返り（Dreams）agent です。
spec: `~/Claude-Workspace/docs/superpowers/specs/2026-05-14-dreams-weekly-reflection-design.md`

引数: $ARGUMENTS （`dry-run` を含むとTelegram通知だけスキップ、`since=YYYY-MM-DD` で開始日上書き）

## 入力データ収集

### ① Daily ログ（過去7日）

```bash
TODAY=$(date +%F)
WEEK_AGO=$(date -v-7d +%F)
find ~/Obsidian/Daily -name '*.md' -newermt "$WEEK_AGO" ! -newermt "$TODAY" \
  | sort
```

各 Daily の "Dev Log" / "Reflection" / "Tomorrow Next" セクションを読み込み。

### ② 会議議事録（過去7日）

```bash
find ~/Claude-Workspace/.company/meetings -name '*.md' -newermt "$WEEK_AGO" ! -newermt "$TODAY"
```

### ③ git log（Workspace 全体、過去7日）

```bash
git -C ~/Claude-Workspace log --since="7 days ago" --oneline --all
```

### ④ JSONL ログ抜粋（過去7日、user message のみ）

```bash
find ~/.claude/projects/-Users-Mac-air-Claude-Workspace -name '*.jsonl' -newermt "$WEEK_AGO" \
  -exec grep -h '"type":"user"' {} \;
```

「やめて」「次から」「違う」「忘れてた」「ミスった」を含むエントリを抽出。

### ⑤ 過去3週分の Tomorrow Next（未消化検出用）

```bash
for i in 7 14 21; do
  d=$(date -v-${i}d +%F)
  find ~/Obsidian/Daily -name "${d}*.md"
done
```

各ファイルから "Tomorrow Next" セクションを抽出して比較。

## 3パターン検出ロジック

### ① 判断パターン

- Daily/ の "Dev Log" 内で `--build` `--force` `--verbose` 等のフラグ言及を集計
- 「〜にした」「〜を選んだ」「〜で対応」等の判断表現を抽出
- **3回以上** 同系統が出現したら検出
- 出力: ケース3件以上を引用、推奨アクション（Gotcha化 / scope拡張 等）

### ② ミスパターン

- Daily/ の "Reflection" + JSONL user message から「ミスった/忘れてた/指摘された/やめて/次から/違う」を抽出
- 同系統のミスを **2-3回以上** 検出
- 既存 Gotcha (`~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_*.md`) と類似があれば、`trigger_count` 更新提案
- 既存 Gotcha なしなら **新規 `/gotcha`** 提案

### ③ 未消化パターン

- 過去3週分の "Tomorrow Next" を ngram 類似度（プロンプト内判定で可）で比較
- 同一/類似項目が **3週連続** で残っていれば検出
- 推奨アクション: 月次棚卸しに送る / archive / 構造的見直し

## stock 昇格候補の検出（spec #3 連動）

git log + Daily/ から「確定事実」性のあるイベントを抽出:
- 新規プロダクト稼働開始 / 初成約 / 重要マイルストーン
- 既存 stock ファイル (`~/Obsidian/context/*.md`, `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/*.md`) に該当エントリがあるか確認
- 無ければ「stock 昇格候補」として提示

## レポート出力

書き込み先: `/Users/Mac_air/Obsidian/Daily/dreams-$(date +%F).md`

フォーマット:

\`\`\`markdown
# Dreams 週次振り返り YYYY-MM-DD (土)

**期間**: <WEEK_AGO> 〜 <昨日>

## サマリー
- 判断パターン: <N>件
- ミスパターン: <N>件
- 未消化パターン: <N>件
- stock昇格候補: <N>件
- 承認推奨: 計 <N>件

---

## 判断パターン

### #1: <タイトル>
- 検出ケース:
  - YYYY-MM-DD <ファイル>: <引用1行>
  - ...
- 推奨アクション: <Gotcha化 / scope拡張 / context/dreams.md追記>

## ミスパターン

### #1: <タイトル>
- 検出ケース: ...
- 既存Gotcha: feedback_*.md → trigger_count N→N+M に更新推奨
- もしくは 新規Gotcha候補:
  \`\`\`
  /gotcha scope=... <要約>
  \`\`\`

## 未消化パターン

### #1: <Tomorrow Next 項目>
- 3週連続持ち越し: <週A> / <週B> / <週C>
- 推奨アクション: 月次棚卸しへ送付 / archive / 構造的解決

## stock 昇格候補（spec #3 連動）

- <事実> → `<昇格先ファイル>` への追記推奨

## アクションチェックリスト

- [ ] 判断パターン #1 を承認 → context/dreams.md に追記
- [ ] ミスパターン #1 を承認 → /gotcha 実行
- [ ] stock昇格 #1 を承認 → 該当 stock ファイル更新
- [ ] 未消化 #1 を 月次棚卸し送付
\`\`\`

## Telegram 通知

`dry-run` 引数が無ければ:

```bash
source ~/.claude/.telegram-meta-bot.env
TEXT="🌙 Dreams 週次レポート $(date +%F) 出ました
判断: <N>件 / ミス: <N>件 / 未消化: <N>件 / stock昇格: <N>件
レポート: ~/Obsidian/Daily/dreams-$(date +%F).md"
curl -s "https://api.telegram.org/bot${TELEGRAM_META_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_META_BOT_CHAT_ID}" \
  --data-urlencode "text=${TEXT}" > /dev/null
```

## 最終出力

ユーザーには以下を返答:
- 生成した Obsidian パス
- 4カテゴリ件数（判断/ミス/未消化/stock昇格）
- Telegram 通知の到達可否

## 重要ルール（必読）

- **context/dreams.md を直接更新しない**（人間承認待ち）
- **新規Gotchaの直接作成もしない**（提案だけ、Hiro が `/gotcha` で確定）
- 件数ゼロでも「健全宣言」をレポートに書き Telegram 通知
- 偽陽性は普通にある前提。アクションチェックリストで人間フィルタを通す
- ngram類似度はプロンプト内判定（粗くて可）
```

- [ ] **Step 3: ファイル確認**

```bash
wc -l /Users/Mac_air/.claude/commands/dreams-weekly.md
```

Expected: 130-170行程度。

- [ ] **Step 4: Commit**

```bash
git -C /Users/Mac_air/.claude add commands/dreams-weekly.md
git -C /Users/Mac_air/.claude commit -m "feat: add /dreams slash command for weekly reflection (spec #5)"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 3: launchd plist でリマインダー登録（土曜 08:00 JST）

**設計判断**: spec #1 と同じく、CronCreate と schedule skill が利用不可のため launchd + Telegram リマインダー + Hiro 手動起動方式に変更（spec 修正済み 2026-05-14, commit 75504bb）。

**Files:**
- Create: `/Users/Mac_air/.claude/scripts/dreams-weekly-reminder.sh`
- Create: `/Users/Mac_air/Library/LaunchAgents/com.trustlink.dreams-weekly-reminder.plist`
- Modify: `/Users/Mac_air/Obsidian/context/cron-inventory.md`

- [ ] **Step 1: リマインダースクリプトを Write**

`/Users/Mac_air/.claude/scripts/dreams-weekly-reminder.sh`:

```bash
#!/bin/bash
# 週次 Dreams 振り返りリマインダー (spec #5) — launchd から呼ばれる
# Telegram 汎用Botに通知だけ送る。実際の /dreams 起動は Hiro が手動で。

set -euo pipefail

LOG_FILE="/tmp/dreams-weekly-reminder.log"
ENV_FILE="/Users/Mac_air/.claude/.telegram-meta-bot.env"

{
  echo "=== $(date +%Y-%m-%d\ %H:%M:%S) ==="
  if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found"
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$ENV_FILE"

  MESSAGE="🌙 週次 Dreams 振り返りの時間です ($(date +%Y-%m-%d))

Claude Code で /dreams を起動してください。
先週の判断・ミス・未消化パターンを集計したレポートが ~/Obsidian/Daily/dreams-$(date +%F).md に出ます。"

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

`/Users/Mac_air/Library/LaunchAgents/com.trustlink.dreams-weekly-reminder.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.trustlink.dreams-weekly-reminder</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/Mac_air/.claude/scripts/dreams-weekly-reminder.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>6</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/dreams-weekly-reminder.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/dreams-weekly-reminder.stderr.log</string>

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

注: launchd の `Weekday` は **0=日曜 ... 6=土曜**（cron と同じ）。Apple 公式 launchd.plist man page で確認可。

- [ ] **Step 3: launchd plist を load**

```bash
launchctl load /Users/Mac_air/Library/LaunchAgents/com.trustlink.dreams-weekly-reminder.plist
launchctl list | grep dreams
```

Expected: `com.trustlink.dreams-weekly-reminder` が一覧に出る。

- [ ] **Step 4: 手動発火テスト**

```bash
launchctl start com.trustlink.dreams-weekly-reminder
sleep 3
cat /tmp/dreams-weekly-reminder.log | tail -10
```

Expected: `SUCCESS`、Telegram に「🌙 週次 Dreams 振り返りの時間です」が届く。

- [ ] **Step 5: cron-inventory.md の launchd セクションを更新**

`/Users/Mac_air/Obsidian/context/cron-inventory.md` の `## launchd (macOS Mac_air)` セクションに追記:

```markdown
| `com.trustlink.dreams-weekly-reminder` | 毎週土曜 08:00 JST | 週次 Dreams 振り返りリマインダー (spec #5) | `/Users/Mac_air/Library/LaunchAgents/com.trustlink.dreams-weekly-reminder.plist` |
```

`last_confirmed: 2026-05-14` を当日日付に更新。spec #1 の monthly-cleanup-reminder と並んで2件登録されているはず。

- [ ] **Step 6: Commit**

```bash
git -C /Users/Mac_air/Obsidian add context/cron-inventory.md
git -C /Users/Mac_air/Obsidian commit -m "docs(context): register dreams-weekly-reminder launchd (spec #5)"
```

---

### Task 4: 初回手動実行 + 動作確認

**Files:**
- Create (実行時): `/Users/Mac_air/Obsidian/Daily/dreams-2026-05-14.md`（テスト実行で生成）

- [ ] **Step 1: `/dreams dry-run` を手動実行**

Claude Code セッションで `/dreams dry-run` を起動。Telegram 通知スキップで agent 動作のみ検証。

Expected:
- 過去7日の Daily/ + git log を集約
- 3パターン検出（または「健全宣言」）
- レポートが `~/Obsidian/Daily/dreams-2026-05-14.md` に書き込まれる

- [ ] **Step 2: レポート内容を目視確認**

```bash
ls -la /Users/Mac_air/Obsidian/Daily/dreams-2026-05-14.md
head -60 /Users/Mac_air/Obsidian/Daily/dreams-2026-05-14.md
```

Expected:
- frontmatter なし（flow なので不要、spec #3 準拠）
- 4セクション構造（判断/ミス/未消化/stock昇格）
- アクションチェックリストが末尾にある
- 件数ゼロなら「健全宣言」

- [ ] **Step 3: Telegram 通知込みで本実行**

`/dreams` を引数なしで実行。汎用Bot に通知到達確認。

- [ ] **Step 4: context/dreams.md が更新されていないことを確認**

```bash
git -C /Users/Mac_air/Obsidian status context/dreams.md
```

Expected: 変更なし（agent は直接更新しないルール、Task 1 のテンプレ状態のまま）。

- [ ] **Step 5: 受け入れ基準チェック**

spec § 9 と対応:
- [ ] CronCreate に `dreams-weekly` が登録、CronList で確認
- [ ] 土曜 08:00 JST に発火（実発火は次土曜まで持ち越し可、手動 dry-run でロジック検証済み）
- [ ] レポート 3セクション + stock昇格 + アクションリスト構成
- [ ] Telegram 通知到達（汎用Bot 共用）
- [ ] `/dreams` slash command で手動起動できる
- [ ] 初回手動実行で「最低1パターン」or「健全宣言」
- [ ] `~/Obsidian/context/dreams.md` テンプレ用意済み
- [ ] 承認 → context/dreams.md 昇格手順がレポート末尾のアクションリストに含まれる

---

### Task 5: 「未承認 Dreams レポート」を月次棚卸しに連携（spec #1 連動）

**Files:**
- Modify: `/Users/Mac_air/.claude/commands/monthly-cleanup.md`

- [ ] **Step 1: 月次棚卸し prompt に検査項目追加**

`/Users/Mac_air/.claude/commands/monthly-cleanup.md` の「③ 処理速度ボトルネック」直後に新セクションを Edit で追加:

```markdown
### ④ 未承認 Dreams レポート再提示（spec #5 連動）

```bash
find ~/Obsidian/Daily -name 'dreams-*.md' -mtime -45 | sort
```

各レポートをスキャンし、`- [ ]` で残っているアクションチェックを集計:
- 過去4週で1件も承認されていなければ「Dreams運用見直し提案」セクションをレポートに追加
- 3ヶ月以上経過した dreams-*.md は `~/Obsidian/Daily/archive/` 移動推奨（実行コマンド付き）
```

- [ ] **Step 2: ファイル確認**

```bash
grep -n "未承認 Dreams" /Users/Mac_air/.claude/commands/monthly-cleanup.md
```

Expected: 1ヒット。

- [ ] **Step 3: Commit**

```bash
git -C /Users/Mac_air/.claude add commands/monthly-cleanup.md
git -C /Users/Mac_air/.claude commit -m "feat: link Dreams unapproved-reports check into monthly-cleanup (spec #5)"
```

注: `~/.claude` が git 管理外ならスキップ。

---

## 受け入れ基準の検証

spec #5 セクション9 と対応:

- [x] Task 3 で CronCreate 登録、Task 4 Step 5 で確認
- [x] Task 4 で土曜 08:00 JST 発火フローを dry-run で検証
- [x] Task 2 prompt が4セクション構造を強制
- [x] Task 4 Step 3 で Telegram 通知到達確認
- [x] Task 2 で `/dreams` slash command 実装
- [x] Task 4 Step 1 で初回手動実行
- [x] Task 1 で `~/Obsidian/context/dreams.md` テンプレ作成
- [x] Task 2 prompt の「アクションチェックリスト」で承認 → 昇格手順を明文化
- [x] Task 5 で spec #1 連動（未承認再提示）追加

---

## Self-Review Checklist（plan作成者用）

- [x] spec の全セクション（1-11）がタスクにマッピング済み
- [x] Telegram 汎用Bot は spec #1 で作成済みのものを共用（重複作成しない）
- [x] **agent が context/dreams.md を直接更新しない**ルールを Task 2 prompt で強制
- [x] 新規Gotcha 直接作成もしない（`/gotcha` 提案だけ）を強制
- [x] flow/stock 分離（spec #3）が Task 1 frontmatter `type: stock` と Task 2 prompt 出力先で表現されている
- [x] spec #1 月次棚卸しへの連携（未承認再提示）を Task 5 で追加
