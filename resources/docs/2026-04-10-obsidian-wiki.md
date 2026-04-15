# Obsidian AI Wiki 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obsidianにフル版AIウィキを構築し、既存ワークフロー（日次ログ・広告レポート）を自動的にrawへ取り込み、Claude CLIが自動でwikiを更新するシステムを作る。

**Architecture:** `raw/`フォルダ（不変ソース）→ `wiki/`フォルダ（Claude管理）の2層構造。launchd WatchPathsがrawの変更を検知し`ingest.sh`を起動、Claude CLI(`-p`モード)がwikiを更新する。既存ワークフロー（日次ログ・Google Adsレポート）の出力先にrawを追加することで、新しい作業を不要にする。

**Tech Stack:** macOS launchd, fswatch(不要), Claude Code CLI(`/opt/homebrew/bin/claude`), bash

---

## ファイルマップ

| ファイル | 役割 |
|---|---|
| `create: /Users/Mac_air/Obsidian/OBSIDIAN-WIKI.md` | Wikiスキーマ（Claudeへの指示書） |
| `create: /Users/Mac_air/Obsidian/wiki/index.md` | 全ページカタログ |
| `create: /Users/Mac_air/Obsidian/wiki/log.md` | 取り込み履歴（append-only） |
| `create: /Users/Mac_air/Obsidian/scripts/ingest.sh` | Claude CLI呼び出しラッパー |
| `create: /Users/Mac_air/Obsidian/scripts/daily_copy.sh` | Daily→raw/daily/コピースクリプト |
| `create: ~/Library/LaunchAgents/com.trustlink.wiki-raw-watch.plist` | raw/ WatchPaths plist |
| `create: ~/Library/LaunchAgents/com.trustlink.wiki-daily-watch.plist` | Daily/ WatchPaths plist |
| `create: ~/Library/LaunchAgents/com.trustlink.wiki-lint.plist` | 週次lintスケジュール |
| `modify: /Users/Mac_air/Claude-Workspace/marketing/google-ads/run_daily_report.sh` | 広告レポートをraw/marketing/へコピー追加 |

---

## Task 1: Obsidianフォルダ構造を作成する

**Files:**
- Create: `/Users/Mac_air/Obsidian/raw/daily/`
- Create: `/Users/Mac_air/Obsidian/raw/marketing/`
- Create: `/Users/Mac_air/Obsidian/raw/products/`
- Create: `/Users/Mac_air/Obsidian/raw/research/`
- Create: `/Users/Mac_air/Obsidian/raw/personal/`
- Create: `/Users/Mac_air/Obsidian/wiki/products/`
- Create: `/Users/Mac_air/Obsidian/wiki/concepts/`
- Create: `/Users/Mac_air/Obsidian/wiki/people/`
- Create: `/Users/Mac_air/Obsidian/scripts/`

- [ ] **Step 1: フォルダを作成する**

```bash
mkdir -p /Users/Mac_air/Obsidian/raw/{daily,marketing,products,research,personal}
mkdir -p /Users/Mac_air/Obsidian/wiki/{products,concepts,people}
mkdir -p /Users/Mac_air/Obsidian/scripts
```

- [ ] **Step 2: 作成確認**

```bash
find /Users/Mac_air/Obsidian/raw /Users/Mac_air/Obsidian/wiki /Users/Mac_air/Obsidian/scripts -type d
```

Expected:
```
/Users/Mac_air/Obsidian/raw
/Users/Mac_air/Obsidian/raw/daily
/Users/Mac_air/Obsidian/raw/marketing
/Users/Mac_air/Obsidian/raw/products
/Users/Mac_air/Obsidian/raw/research
/Users/Mac_air/Obsidian/raw/personal
/Users/Mac_air/Obsidian/wiki
/Users/Mac_air/Obsidian/wiki/products
/Users/Mac_air/Obsidian/wiki/concepts
/Users/Mac_air/Obsidian/wiki/people
/Users/Mac_air/Obsidian/scripts
```

---

## Task 2: OBSIDIAN-WIKI.md スキーマを作成する

**Files:**
- Create: `/Users/Mac_air/Obsidian/OBSIDIAN-WIKI.md`

- [ ] **Step 1: スキーマファイルを作成する**

`/Users/Mac_air/Obsidian/OBSIDIAN-WIKI.md` に以下を書く:

```markdown
# Obsidian Wiki スキーマ

このファイルはClaudeがwikiを管理するためのルール定義です。

## フォルダ構造

```
/Users/Mac_air/Obsidian/
├── raw/           ← 原本。不変。Claude は読むだけ（変更禁止）
│   ├── daily/     ← 日次開発ログ（自動コピー）
│   ├── marketing/ ← 広告レポート（自動コピー）
│   ├── products/  ← プロダクト仕様・メモ（手動追加）
│   ├── research/  ← 記事・調査（Web Clipper）
│   └── personal/  ← 個人メモ・目標（手動追加）
└── wiki/          ← Claudeが管理するまとめページ
    ├── index.md   ← 全ページカタログ（Claude が更新）
    ├── log.md     ← 取り込み履歴（Claude が追記）
    ├── products/  ← プロダクト別まとめページ
    ├── concepts/  ← ビジネス概念・戦略ページ
    └── people/    ← 人物・取引先ページ
```

## Ingest ワークフロー

rawに新しいファイルが追加されたとき:

1. ファイルを読む
2. wiki/index.md を読んで既存ページを把握する
3. ファイル内容を要約してwikiページを作成または更新する
   - 既存ページへのリンクを貼る（[[ページ名]] 形式）
   - 矛盾があれば既存ページを更新する
4. wiki/index.md を更新する（新ページを追加）
5. wiki/log.md に追記する

## wikiページのフォーマット

```yaml
---
source: raw/カテゴリ/ファイル名.md
date: YYYY-MM-DD
tags: [タグ1, タグ2]
---
```

本文はMarkdown。関連ページへは [[ページ名]] でリンク。

## Query ワークフロー

質問を受けたとき:
1. wiki/index.md を読んで関連ページを特定する
2. 関連ページを読む
3. 回答を生成する（引用元ページを明記）
4. 価値ある回答はwikiに保存することを提案する

## Lint ワークフロー

lint実行時:
1. 全wikiページをスキャンする
2. 以下を報告・修正する:
   - 他ページからリンクされていない孤立ページ
   - 矛盾する情報（新旧で内容が違う）
   - 存在しないページへのリンク
   - rawに内容があるのにwikiページがない項目
3. lint結果をwiki/log.mdに記録する

## ゆるいルール

- 完璧を目指さない。重要な情報だけで十分
- rawに入れたら必ずingestする（自動化しているが確認は推奨）
- 週1回lintを実行する（自動化済み）
```

- [ ] **Step 2: ファイル確認**

```bash
wc -l /Users/Mac_air/Obsidian/OBSIDIAN-WIKI.md
```

Expected: 70行以上

---

## Task 3: wiki/index.md と wiki/log.md を作成する

**Files:**
- Create: `/Users/Mac_air/Obsidian/wiki/index.md`
- Create: `/Users/Mac_air/Obsidian/wiki/log.md`

- [ ] **Step 1: index.md を作成する**

`/Users/Mac_air/Obsidian/wiki/index.md`:

```markdown
# Wiki Index

Claudeが管理するwikiの全ページカタログ。
最終更新: 2026-04-10

## Products
<!-- Claudeが各プロダクトのページを作成後に追記 -->

## Concepts
<!-- ビジネス戦略・概念ページ -->

## People
<!-- 取引先・バイヤー・チームメンバー -->

## Analytics
<!-- 広告・売上データ分析 -->
```

- [ ] **Step 2: log.md を作成する**

`/Users/Mac_air/Obsidian/wiki/log.md`:

```markdown
# Wiki Log

取り込み・操作の履歴（append-only）。

フォーマット: `## [YYYY-MM-DD] action | 概要`

---

## [2026-04-10] init | Wiki初期化
- フォルダ構造作成
- OBSIDIAN-WIKI.md スキーマ定義
- index.md / log.md 作成
```

- [ ] **Step 3: 確認**

```bash
ls /Users/Mac_air/Obsidian/wiki/
```

Expected: `index.md  log.md  concepts/  people/  products/`

---

## Task 4: ingest.sh スクリプトを作成する

**Files:**
- Create: `/Users/Mac_air/Obsidian/scripts/ingest.sh`

このスクリプトはlaunchdから呼ばれ、rawに追加された未処理ファイルをClaude CLIで取り込む。

- [ ] **Step 1: ingest.sh を作成する**

`/Users/Mac_air/Obsidian/scripts/ingest.sh`:

```bash
#!/bin/bash
# Obsidian Wiki 自動ingestスクリプト
# launchd WatchPaths によってraw/変更時に呼ばれる

OBSIDIAN="/Users/Mac_air/Obsidian"
WIKI="$OBSIDIAN/wiki"
LOG="$WIKI/log.md"
CLAUDE="/opt/homebrew/bin/claude"

# 処理済みファイルをログから取得
get_processed() {
  grep "^## \[" "$LOG" | grep "ingest |" | sed 's/.*ingest | //'
}

# raw/配下の全.mdファイルをスキャン
find "$OBSIDIAN/raw" -name "*.md" | while read -r filepath; do
  filename=$(basename "$filepath")
  relpath="${filepath#$OBSIDIAN/}"

  # ログに記録済みかチェック
  if grep -q "ingest | $relpath" "$LOG" 2>/dev/null; then
    continue
  fi

  echo "[ingest.sh] Processing: $relpath"

  # Claude CLIでingest実行
  PROMPT="OBSIDIAN-WIKI.mdのスキーマに従って、以下のファイルをwikiに取り込んでください。

対象ファイル: $relpath

手順:
1. $relpath を読む
2. wiki/index.md を読んで既存ページを把握する
3. 適切なwikiページを作成または更新する (wiki/products/, wiki/concepts/, wiki/people/ のいずれか)
4. wiki/index.md を更新する
5. wiki/log.md に '## [$(date +%Y-%m-%d)] ingest | $relpath' を追記する"

  "$CLAUDE" \
    --add-dir "$OBSIDIAN" \
    --allowedTools "Read,Write,Edit,Glob,Grep" \
    -p "$PROMPT" \
    >> /tmp/obsidian-wiki-ingest.log 2>&1

  echo "[ingest.sh] Done: $relpath"
done
```

- [ ] **Step 2: 実行権限を付与する**

```bash
chmod +x /Users/Mac_air/Obsidian/scripts/ingest.sh
```

- [ ] **Step 3: 動作確認（テストファイルで実行）**

```bash
# テストファイルを作成
echo "# テスト\nこれはingestテストです。ebay-agentに関するメモ。" \
  > /Users/Mac_air/Obsidian/raw/products/test-ingest.md

# 手動実行
/Users/Mac_air/Obsidian/scripts/ingest.sh
```

Expected: `/tmp/obsidian-wiki-ingest.log` にClaudeの出力が記録され、`wiki/products/` にページが作成される

- [ ] **Step 4: テストファイルを削除・ログをリセット**

```bash
rm /Users/Mac_air/Obsidian/raw/products/test-ingest.md
# log.mdのテスト行を手動で削除する
```

---

## Task 5: raw/ WatchPaths launchd plist を作成する

**Files:**
- Create: `~/Library/LaunchAgents/com.trustlink.wiki-raw-watch.plist`

- [ ] **Step 1: plist を作成する**

`~/Library/LaunchAgents/com.trustlink.wiki-raw-watch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.trustlink.wiki-raw-watch</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/Mac_air/Obsidian/scripts/ingest.sh</string>
  </array>

  <key>WatchPaths</key>
  <array>
    <string>/Users/Mac_air/Obsidian/raw</string>
  </array>

  <key>StandardOutPath</key>
  <string>/tmp/wiki-raw-watch.log</string>

  <key>StandardErrorPath</key>
  <string>/tmp/wiki-raw-watch-err.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 2: launchd に登録する**

```bash
launchctl load ~/Library/LaunchAgents/com.trustlink.wiki-raw-watch.plist
launchctl list | grep wiki-raw-watch
```

Expected: `com.trustlink.wiki-raw-watch` が表示される

- [ ] **Step 3: 動作確認**

```bash
# rawにファイルを追加してトリガーを確認
echo "# trigger test" > /Users/Mac_air/Obsidian/raw/products/trigger-test.md
sleep 5
cat /tmp/wiki-raw-watch.log | tail -5
```

Expected: `[ingest.sh] Processing: raw/products/trigger-test.md` が表示される

- [ ] **Step 4: テストファイルを削除**

```bash
rm /Users/Mac_air/Obsidian/raw/products/trigger-test.md
```

---

## Task 6: daily log → raw/daily/ 自動コピーを設定する

**Files:**
- Create: `/Users/Mac_air/Obsidian/scripts/daily_copy.sh`
- Create: `~/Library/LaunchAgents/com.trustlink.wiki-daily-watch.plist`

- [ ] **Step 1: daily_copy.sh を作成する**

`/Users/Mac_air/Obsidian/scripts/daily_copy.sh`:

```bash
#!/bin/bash
# Daily/の新しいファイルをraw/daily/にコピーする

DAILY="/Users/Mac_air/Obsidian/Daily"
RAW_DAILY="/Users/Mac_air/Obsidian/raw/daily"

# 今日のファイルを確認
TODAY=$(date +%Y-%m-%d)
SRC="$DAILY/$TODAY.md"
DST="$RAW_DAILY/$TODAY.md"

if [ -f "$SRC" ] && [ ! -f "$DST" ]; then
  cp "$SRC" "$DST"
  echo "[daily_copy.sh] Copied $TODAY.md to raw/daily/"
elif [ -f "$SRC" ] && [ "$SRC" -nt "$DST" ]; then
  cp "$SRC" "$DST"
  echo "[daily_copy.sh] Updated $TODAY.md in raw/daily/"
fi
```

- [ ] **Step 2: 実行権限を付与する**

```bash
chmod +x /Users/Mac_air/Obsidian/scripts/daily_copy.sh
```

- [ ] **Step 3: daily_watch plist を作成する**

`~/Library/LaunchAgents/com.trustlink.wiki-daily-watch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.trustlink.wiki-daily-watch</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/Mac_air/Obsidian/scripts/daily_copy.sh</string>
  </array>

  <key>WatchPaths</key>
  <array>
    <string>/Users/Mac_air/Obsidian/Daily</string>
  </array>

  <key>StandardOutPath</key>
  <string>/tmp/wiki-daily-watch.log</string>

  <key>StandardErrorPath</key>
  <string>/tmp/wiki-daily-watch-err.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 4: launchd に登録する**

```bash
launchctl load ~/Library/LaunchAgents/com.trustlink.wiki-daily-watch.plist
launchctl list | grep wiki-daily-watch
```

- [ ] **Step 5: 動作確認**

```bash
# 今日の日誌ファイルを触ってトリガーを確認
touch /Users/Mac_air/Obsidian/Daily/$(date +%Y-%m-%d).md
sleep 3
cat /tmp/wiki-daily-watch.log | tail -3
```

Expected: `[daily_copy.sh] Copied YYYY-MM-DD.md to raw/daily/` が表示される

---

## Task 7: Google Ads レポートを raw/marketing/ へ保存するよう修正する

**Files:**
- Modify: `/Users/Mac_air/Claude-Workspace/marketing/google-ads/run_daily_report.sh`

- [ ] **Step 1: 現在のスクリプトを確認する**

```bash
cat /Users/Mac_air/Claude-Workspace/marketing/google-ads/run_daily_report.sh
```

- [ ] **Step 2: スクリプトにraw/marketing/へのコピーを追加する**

`run_daily_report.sh` の末尾に以下を追加:

```bash
# Obsidian Wiki raw/marketing/ へコピー
REPORT_DATE=$(date +%Y-%m-%d)
RAW_MARKETING="/Users/Mac_air/Obsidian/raw/marketing"
REPORT_SRC="$(dirname "$0")/GOOGLE-ADS-REPORT.md"

if [ -f "$REPORT_SRC" ]; then
  cp "$REPORT_SRC" "$RAW_MARKETING/google-ads-$REPORT_DATE.md"
  echo "Copied Google Ads report to raw/marketing/google-ads-$REPORT_DATE.md"
fi
```

- [ ] **Step 3: 動作確認（ドライラン）**

```bash
# GOOGLE-ADS-REPORT.md が存在すれば確認
ls /Users/Mac_air/Claude-Workspace/marketing/google-ads/GOOGLE-ADS-REPORT.md
```

---

## Task 8: 週次lint launchd を設定する

**Files:**
- Create: `/Users/Mac_air/Obsidian/scripts/lint.sh`
- Create: `~/Library/LaunchAgents/com.trustlink.wiki-lint.plist`

- [ ] **Step 1: lint.sh を作成する**

`/Users/Mac_air/Obsidian/scripts/lint.sh`:

```bash
#!/bin/bash
# Obsidian Wiki 週次lintスクリプト

OBSIDIAN="/Users/Mac_air/Obsidian"
CLAUDE="/opt/homebrew/bin/claude"

PROMPT="OBSIDIAN-WIKI.mdのlintワークフローに従って、wikiの健全性チェックを実行してください。

1. wiki/配下の全ページをスキャンする
2. 孤立ページ・矛盾・壊れたリンクを検出する
3. 修正できるものは修正する
4. wiki/log.mdに '## [$(date +%Y-%m-%d)] lint | 週次lint完了' を追記して結果サマリーを記録する"

"$CLAUDE" \
  --add-dir "$OBSIDIAN" \
  --allowedTools "Read,Write,Edit,Glob,Grep" \
  -p "$PROMPT" \
  >> /tmp/obsidian-wiki-lint.log 2>&1

echo "[lint.sh] Weekly lint completed: $(date)"
```

- [ ] **Step 2: 実行権限を付与する**

```bash
chmod +x /Users/Mac_air/Obsidian/scripts/lint.sh
```

- [ ] **Step 3: 週次lint plist を作成する（毎週月曜9時）**

`~/Library/LaunchAgents/com.trustlink.wiki-lint.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.trustlink.wiki-lint</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/Mac_air/Obsidian/scripts/lint.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/tmp/wiki-lint.log</string>

  <key>StandardErrorPath</key>
  <string>/tmp/wiki-lint-err.log</string>
</dict>
</plist>
```

- [ ] **Step 4: launchd に登録する**

```bash
launchctl load ~/Library/LaunchAgents/com.trustlink.wiki-lint.plist
launchctl list | grep wiki-lint
```

---

## 完了チェックリスト

- [ ] `raw/` と `wiki/` フォルダ構造が存在する
- [ ] `OBSIDIAN-WIKI.md` スキーマが作成されている
- [ ] `wiki/index.md` と `wiki/log.md` が作成されている
- [ ] `ingest.sh` が実行可能で、テストファイルを正しく処理する
- [ ] `com.trustlink.wiki-raw-watch` がlaunchdに登録されている
- [ ] `com.trustlink.wiki-daily-watch` がlaunchdに登録されている
- [ ] `daily_copy.sh` が日次ログをraw/daily/にコピーする
- [ ] `run_daily_report.sh` がレポートをraw/marketing/にコピーする
- [ ] `com.trustlink.wiki-lint` が週次lintをスケジュールしている

## 動作フロー（完成後）

```
毎日の開発日誌を書く
    ↓ daily_copy.sh が自動コピー
    → Obsidian/raw/daily/YYYY-MM-DD.md
    ↓ launchd WatchPaths が検知
    → ingest.sh → Claude CLI → wiki/更新

毎朝Google Adsレポート生成
    ↓ run_daily_report.sh がコピー
    → Obsidian/raw/marketing/google-ads-YYYY-MM-DD.md
    ↓ launchd WatchPaths が検知
    → ingest.sh → Claude CLI → wiki/更新

毎週月曜9時
    → lint.sh → Claude CLI → wiki/整理

いつでも
    → Claude Code に「wiki検索して」と聞く
    → wiki/index.md を起点に回答
```
