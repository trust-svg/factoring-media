# SSoT + flow/stock 構造整備 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「どの情報はどこが正か」のマップを明文化し、散在カテゴリ（広告アカウント・SaaS契約・Cron索引）を3つの新規ファイルに集約。Workspace CLAUDE.md に SSoT Map セクションを追加して Claude が常時参照できる状態にする。

**Architecture:** 既存ファイル構造には手を入れず、(1) 新規3ファイルを `~/Obsidian/context/` 配下に作成、(2) Workspace CLAUDE.md に簡潔版 Map を追加、(3) 既存重複の整理は spec #1（月次棚卸し）に委譲。flow/stock 昇格自動化は spec #5（Dreams）で実装。

**Tech Stack:** Markdown only。Obsidian vault (`~/Obsidian/context/`), Workspace CLAUDE.md (`/Users/Mac_air/Claude-Workspace/CLAUDE.md`)

**Spec:** [`docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md`](../specs/2026-05-14-ssot-flow-stock-design.md)

---

## File Structure

| ファイル | 役割 | 状態 |
|---------|------|------|
| `~/Obsidian/context/ad-accounts.md` | Meta/Google/LinkedIn 等の広告アカウントID集約 | 新規作成 |
| `~/Obsidian/context/subscriptions.md` | Anthropic/OpenAI/fal.ai/Notion/freee 等の月額・契約日 | 新規作成 |
| `~/Obsidian/context/cron-inventory.md` | VPS cron / launchd / GHA / CronCreate の4箇所索引 | 新規作成 |
| `/Users/Mac_air/Claude-Workspace/CLAUDE.md` | プロジェクト規約。SSoT Map セクション追加 | 既存に追記 |

---

### Task 1: ad-accounts.md 作成（広告アカウント集約）

**Files:**
- Create: `/Users/Mac_air/Obsidian/context/ad-accounts.md`

- [ ] **Step 1: 既存 memory から広告アカウント情報を収集**

Run:
```bash
grep -l "act_\|customer.*id\|MCC\|Customer Match" /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/*.md
```
Expected: `meta-ads-setup.md`, `google-ads-customer-match.md` 等が見つかる

- [ ] **Step 2: 各ファイルから ID 値を抽出（実値を確認、メモに残す）**

Read で対象ファイルを開き、以下の項目を抽出:
- Meta: act_ID（act_646557817602977 が CLAUDE.md にあり）
- Google Ads: Customer ID（5225110150 が CLAUDE.md にあり）
- LinkedIn: もし設定があれば
- TikTok: もし設定があれば
- X Ads: もし設定があれば

- [ ] **Step 3: テンプレと現状情報を含む ad-accounts.md を作成**

`/Users/Mac_air/Obsidian/context/ad-accounts.md` に以下を Write:

```markdown
---
type: stock
category: ad-accounts
last_confirmed: 2026-05-14
---

# 広告アカウント一覧（SSoT）

Claude が広告作業時、アカウントID不明な場合は**最初にここを見る**。
更新ルール: 上書き、最新が正。新規アカウント追加時は last_confirmed 更新。

## Meta Ads

| アカウント | act_ID | 用途 | 関連 memory |
|-----------|--------|------|------------|
| 共有アカウント | `act_646557817602977` | Olive/Travis/Massive 等の共有 | [meta-ads-setup.md](../../.claude/projects/-Users-Mac-air-Claude-Workspace/memory/meta-ads-setup.md) |

## Google Ads

| Customer ID | 用途 | 関連 memory |
|-------------|------|------------|
| `5225110150` | マッチング広告 Customer Match | [google-ads-customer-match.md](../../.claude/projects/-Users-Mac-air-Claude-Workspace/memory/google-ads-customer-match.md) |

## LinkedIn Ads

（未設定 / 設定時に追記）

## TikTok Ads

（未設定 / 設定時に追記）

## X Ads

（未設定 / 設定時に追記）

## 関連 Gotchas

- [Adjust連携ACI CVをGA UIからいじらない](../../.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_google_ads_aci.md)
- [広告レポートはローカルMac動作](../../.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_ads_local.md)
```

- [ ] **Step 4: 確認**

Run: `wc -l /Users/Mac_air/Obsidian/context/ad-accounts.md`
Expected: 30-40行程度

- [ ] **Step 5: Commit（Obsidian vault が git管理されている場合）**

```bash
cd /Users/Mac_air/Obsidian && git add context/ad-accounts.md && git commit -m "feat(ssot): add ad-accounts.md as stock for advertising IDs (spec #3)"
```

Obsidian vault が git 管理外ならスキップ。

---

### Task 2: subscriptions.md 作成（SaaS/API契約一覧）

**Files:**
- Create: `/Users/Mac_air/Obsidian/context/subscriptions.md`

- [ ] **Step 1: 主要 SaaS の契約情報を収集**

ユーザー（Hiro）にヒアリングする情報項目:
- Anthropic API（プラン・月額）
- OpenAI API（プラン・月額）
- fal.ai（プラン・月額・契約日）
- Notion（プラン・月額）
- freee（プラン・月額）
- Bitwarden（Free / 計画変更時記録用）
- Contabo VPS（$6.86/月、CLAUDE.md にあり）
- GitHub（プラン）
- Cursor / Claude Code Pro（プラン）

不明値は「要確認」で空欄にしておき、後日埋める。

- [ ] **Step 2: subscriptions.md を作成**

`/Users/Mac_air/Obsidian/context/subscriptions.md` に以下を Write:

```markdown
---
type: stock
category: subscriptions
last_confirmed: 2026-05-14
---

# SaaS / API 契約一覧（SSoT）

月次のコスト把握・解約タイミング判断の元データ。
更新ルール: 上書き、最新が正。プラン変更・契約日更新時は last_confirmed を更新。

## API・LLM

| サービス | プラン | 月額 (USD/JPY) | 契約日 | メモ |
|---------|-------|----------------|--------|------|
| Anthropic API | 従量 | （実績ベース） | - | Claude Code 経由含む |
| OpenAI API | 従量 | （実績ベース） | - | gpt-image-1 等 |
| fal.ai | （要確認） | （要確認） | （要確認） | 画像・動画生成 |

## ノーコード・データベース

| サービス | プラン | 月額 | 契約日 | メモ |
|---------|-------|------|--------|------|
| Notion | （要確認） | （要確認） | - | mcp__notion 経由で連携 |

## 会計

| サービス | プラン | 月額 | 契約日 | メモ |
|---------|-------|------|--------|------|
| freee | （要確認） | （要確認） | - | 税理士: 星野税理士 |

## インフラ

| サービス | プラン | 月額 | 契約日 | メモ |
|---------|-------|------|--------|------|
| Contabo VPS | Cloud VPS 10 | $6.86 | 年払い $82.32 | 46.250.252.99 (東京) |

## 開発ツール

| サービス | プラン | 月額 | 契約日 | メモ |
|---------|-------|------|--------|------|
| GitHub | （要確認） | （要確認） | - | trust-svg |
| Claude Code | （要確認） | （要確認） | - | Pro plan |
| Bitwarden | Free | $0 | 2026-05-14〜（spec #6 で本格導入） | 個人用 vault |

## アフィリエイト・収益関連（参考）

- A8.net（イストワール提携済）
- アクセストレード（アビエス/はたの/アース 申請中）

## 関連 memory

- [vps-hetzner.md](../../.claude/projects/-Users-Mac-air-Claude-Workspace/memory/vps-hetzner.md) — VPS 詳細
- [freee-accounting.md](../../.claude/projects/-Users-Mac-air-Claude-Workspace/memory/freee-accounting.md) — freee連携
```

- [ ] **Step 3: 確認**

Run: `wc -l /Users/Mac_air/Obsidian/context/subscriptions.md`
Expected: 50-60行程度

- [ ] **Step 4: Commit（Obsidian vault が git管理されている場合）**

---

### Task 3: cron-inventory.md 作成（4箇所索引）

このタスクは **spec #3 セクション 6.1.3 の初回作成タスク**に対応する。

**Files:**
- Create: `/Users/Mac_air/Obsidian/context/cron-inventory.md`

- [ ] **Step 1: VPS cron を棚卸し**

Run:
```bash
ssh trustlink-prod 'crontab -l 2>/dev/null'
ssh trustlink-prod 'ls -la /etc/cron.d/ 2>/dev/null'
```
Expected: cron 行が複数出力される。出力を一時メモに保存。

注: ssh エイリアスが通っていない場合は `ssh root@46.250.252.99` を試す。

- [ ] **Step 2: ローカル launchd を棚卸し**

```bash
ls ~/Library/LaunchAgents/com.trustlink.*.plist 2>/dev/null
launchctl list | grep trustlink
```
Expected: `com.trustlink.d-manager` 等が見つかる

- [ ] **Step 3: GitHub Actions を棚卸し**

主要4リポについて:
```bash
gh workflow list -R trust-svg/ai-daily-digest 2>/dev/null
gh workflow list -R trust-svg/ebay-inventory-tool 2>/dev/null
gh workflow list -R trust-svg/factoring-media 2>/dev/null
gh workflow list -R trust-svg/saimu-media 2>/dev/null
```
Expected: workflow 一覧が出力される

- [ ] **Step 4: CronCreate を棚卸し**

ToolSearch で `CronList` を読み込み、`CronList` ツールを呼び出して登録済み cron を一覧化。

- [ ] **Step 5: 上記4出力を統合した cron-inventory.md を作成**

`/Users/Mac_air/Obsidian/context/cron-inventory.md` に Write。
フォーマットは spec #3 セクション 6.1.2 のテンプレに従う:

```markdown
---
type: stock
category: cron-inventory
last_confirmed: 2026-05-14
---

# Cron / 自動化スケジュール一覧（SSoT）

「動いてる自動化が4箇所に散在」問題の解消用索引。
月次棚卸し（spec #1）で 4 コマンド再実行 → diff を取り、差分があれば更新。

## VPS cron (Contabo 46.250.252.99, TZ=Asia/Tokyo)

<Step 1 の出力を整形して以下のテーブルに転記>

| schedule (JST) | command | 用途 | 通知先 |
|----------------|---------|------|-------|
| `*/5 * * * *` | `/opt/scripts/monitor-anthropic-credit.sh` | API残高監視 | Telegram bmanager |
| `0 9,12,19 * * *` | `cd /opt/apps/saimu-media && docker compose run --rm sns-engine python poster.py` | saimu Threads投稿 | (ログのみ) |
| ... | ... | ... | ... |

## ローカル launchd (~/Library/LaunchAgents/)

<Step 2 の出力を整形して以下のテーブルに転記>

| plist | schedule | 用途 | 通知先 |
|-------|----------|------|-------|
| `com.trustlink.d-manager.plist` | 常駐 | Discord AI組織Bot | Discord |
| `com.trustlink.google-ads-report.plist` | 毎日 09:30 | Google広告レポート | Discord |
| ... | ... | ... | ... |

## GitHub Actions

<Step 3 の出力を整形して以下のテーブルに転記>

| repo | workflow | schedule | 用途 |
|------|----------|----------|------|
| `trust-svg/ai-daily-digest` | `daily-digest.yml` | `0 21 * * *` UTC (06:00 JST) | AIニュース配信 |
| ... | ... | ... | ... |

## CronCreate (Claude remote agents)

<Step 4 の CronList 出力を整形>

| name | schedule (JST) | 用途 | 出力先 |
|------|---------------|------|-------|
| （未登録 / spec #1+#5 で追加予定） | - | - | - |

## 要確認・廃止候補

（4 コマンドで出てきたが用途不明の cron をここに分離）

## 関連 spec

- [`docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md`](../../Claude-Workspace/docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md) — 月次棚卸しで本ファイルを更新
- [`docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md`](../../Claude-Workspace/docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md) — このファイルの設計
```

- [ ] **Step 6: 確認**

Run: `wc -l /Users/Mac_air/Obsidian/context/cron-inventory.md`
Expected: 60-100行程度（cron 数による）

- [ ] **Step 7: Commit（Obsidian vault が git管理されている場合）**

---

### Task 4: Workspace CLAUDE.md に SSoT Map セクション追加

**Files:**
- Modify: `/Users/Mac_air/Claude-Workspace/CLAUDE.md`

- [ ] **Step 1: 既存 CLAUDE.md の構造を確認**

Run: `wc -l /Users/Mac_air/Claude-Workspace/CLAUDE.md && grep -n "^## " /Users/Mac_air/Claude-Workspace/CLAUDE.md`
Expected: 既存セクション一覧（"Workspace Overview", "Mandatory Rules" 等）。"SSoT Map" がまだ無いことを確認。

- [ ] **Step 2: 追加箇所を決定**

挿入位置: `## Working Process Rules（作業プロセス規律）` の**直前**（規律よりも上位の「情報のありか」だから）。

`grep -n "## Working Process Rules" /Users/Mac_air/Claude-Workspace/CLAUDE.md` で行番号を確認。

- [ ] **Step 3: SSoT Map セクションを追加（Edit ツール）**

挿入する内容:

```markdown
## SSoT Map（情報のありかマップ）

困った時、まずこの表を参照する。詳細は [`docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md`](docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md)

### Stock（最新が正・上書き）
- ユーザープロフィール → `~/Obsidian/context/identity.md`
- ビジネス概要 → `~/Obsidian/context/business.md`
- 技術環境 → `~/Obsidian/context/tech-setup.md`
- プロダクト最新状態 → `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/<product>.md`
- Gotchas → `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_*.md`
- 広告アカウント → `~/Obsidian/context/ad-accounts.md`
- SaaS契約一覧 → `~/Obsidian/context/subscriptions.md`
- VPS情報 → `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/vps-hetzner.md`
- AI組織戦略 → `.company/strategy/`
- 設計仕様書 → `docs/superpowers/specs/`
- Dreams 確定パターン → `~/Obsidian/context/dreams.md`（spec #5）
- クロスプロダクト TODO → `.company/strategy/roadmap.md`
- 個別プロダクト TODO → `memory/<product>.md` 内の TODO セクション

### Flow（時系列・追記）
- 開発日誌 → `~/Obsidian/Daily/`
- AI組織議事録 → `.company/meetings/`
- 取り込み待ち → `~/Obsidian/inbox/`
- 当日タスク → `~/Obsidian/Daily/<今日>.md` の "Tomorrow Next"

### 外部SSoT（Claudeは参照のみ）
- 顧客 → Notion DB（`mcp__notion`）
- 会計 → freee API（`mcp__freee`）
- カレンダー → Google Calendar（`mcp__google-calendar`）
- メール → Gmail（`mcp__gmail`）
- Credentials → 移行中 `.env`散在、移行後 Bitwarden（spec #6）
- Cron索引 → `~/Obsidian/context/cron-inventory.md`

### TodoWrite との関係
- TodoWrite はセッション内タスクのみ、永続化しない
- 永続化が必要な TODO は「クロスプロダクト/個別プロダクト/当日タスク」のいずれか stock に書く

```

- [ ] **Step 4: 確認**

Run: `grep -n "## SSoT Map" /Users/Mac_air/Claude-Workspace/CLAUDE.md && wc -l /Users/Mac_air/Claude-Workspace/CLAUDE.md`
Expected: SSoT Map がヒット、CLAUDE.md の行数が増えている

- [ ] **Step 5: Commit**

```bash
git -C /Users/Mac_air/Claude-Workspace add CLAUDE.md
git -C /Users/Mac_air/Claude-Workspace commit -m "feat(ssot): add SSoT Map section to Workspace CLAUDE.md (spec #3)"
```

---

### Task 5: spec #1（月次棚卸し）への「Map逸脱検査」追加メモを Issue/TODO 化

このタスクは**ドキュメントレベルの追跡**。実装は spec #1 のプランで行う。

- [ ] **Step 1: spec #1 ファイルに「依存追加」コメントを追記**

`/Users/Mac_air/Claude-Workspace/docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md` の依存関係セクションに以下を追加（既に書かれていれば skip）:

```markdown
### spec #3 からの依存追加（2026-05-14）

月次棚卸しの監査項目に以下を追加:
- 「SSoT Map にない場所に新規ファイルが増えていないか」検査
- `~/Obsidian/context/cron-inventory.md` を4コマンドで再生成し diff を提示
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/Mac_air/Claude-Workspace add docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md
git -C /Users/Mac_air/Claude-Workspace commit -m "docs(spec #1): add Map逸脱検査 dependency from spec #3"
```

---

## 受け入れ基準の検証

spec #3 セクション8の受け入れ基準と対応:

- [ ] Task 4 で `~/Claude-Workspace/CLAUDE.md` に SSoT Map セクション追加済み
- [ ] Task 1-3 で 新規 3ファイル（ad-accounts / subscriptions / cron-inventory）のテンプレ作成済み
- [ ] Task 1-3 の各 Step で「現状確認できた情報」を最低1件ずつ記載（空ファイル禁止）
- [ ] Task 5 で 月次棚卸し（spec #1）に「Map逸脱検査」追加メモ済み（実装は spec #1 のプラン側）
- [ ] Task 4 の Map 冒頭で spec 本体へのリンク済み

---

## Self-Review Checklist（plan作成者用）

- [x] 物理ディレクトリ再編は対象外（spec で明示）→ プランも対応せず
- [x] Credentials 1Password 移行 = spec #6 → このプランからは除外
- [x] Dreams 週次振り返り = spec #5 → このプランからは除外
- [x] flow → stock 昇格作業 = spec #5 で自動化 → このプランでは「ルール明文化」のみ
- [x] cron-inventory.md の作成手順詳細（spec #3 6.1.3）を Task 3 でカバー
