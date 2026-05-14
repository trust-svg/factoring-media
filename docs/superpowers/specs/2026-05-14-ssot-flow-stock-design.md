# SSoT + flow/stock 構造整備 — Design Spec

**Date**: 2026-05-14
**Author**: Hiro + Claude
**Status**: Draft (要レビュー)
**Origin**: note記事「育てるClaude Codeから"勝手に育つClaude Code"へ」の④汚れにくい体質

---

## 1. 目的

情報のSSoT（Single Source of Truth）と flow/stock 分離を**明文化**し、Claude Code リポジトリが**構造的に汚れにくい体質**を獲得する。

### スコープの絞り込み

本 spec は**規約レイヤーのみ**を扱う:
- ✅ 「どの情報はどこが正か」のマップ定義
- ✅ flow → stock 昇格ルール
- ✅ 既存重複の整理計画（ポインタのみ、実作業は段階的）

含めない:
- ❌ Credentials の 1Password 移行作業（**spec #6** に分離）
- ❌ Dreams 週次振り返り（**spec #5** に分離）
- ❌ 物理ディレクトリ再編（破壊的すぎ）

---

## 2. SSoT Map（全12カテゴリ）

Claude Code が情報を探す時、**最初に参照すべき場所**を以下に固定する。

### 2.1 stock（現時点で正しい事実）

| カテゴリ | SSoT | 更新ルール |
|---------|------|----------|
| ユーザープロフィール | `~/Obsidian/context/identity.md` | 上書き、最新が正 |
| ビジネス概要 | `~/Obsidian/context/business.md` | 上書き、最新が正 |
| 技術環境（ローカル） | `~/Obsidian/context/tech-setup.md` | 上書き、最新が正 |
| プロダクト最新状態 | `memory/<product>.md`（49ファイル中） | 上書き、最新が正 |
| 顧客情報 | **Notion DB**（外部） | Notion側が正、Claudeはread only |
| 会計データ | **freee API**（外部） | freee側が正 |
| Gotchas / feedback | `memory/feedback_*.md` | scope付き、deprecated検出 |
| **Dreams 確定パターン** ⭐ | `~/Obsidian/context/dreams.md`（spec #5） | 累積追記、重複検出あり |
| AI組織の判断・戦略 | `.company/strategy/` | 上書き |
| 設計仕様書 | `docs/superpowers/specs/` | バージョン固定（日付付きファイル） |
| **広告アカウント情報** ⭐ | `~/Obsidian/context/ad-accounts.md`（新規） | 上書き、Meta/Google/LinkedIn等のID一元化 |
| **VPS / インフラ** | `memory/vps-hetzner.md` | 上書き、現役VPS情報 |
| **SaaS / API契約一覧** ⭐ | `~/Obsidian/context/subscriptions.md`（新規） | 上書き、月額・契約日記載 |
| **クロスプロダクト TODO / ロードマップ** ⭐ | `.company/strategy/roadmap.md` | 上書き、戦略レベル |
| **個別プロダクト TODO** | `memory/<product>.md` 内の TODO セクション | 上書き |
| **当日タスク** | `~/Obsidian/Daily/<今日>.md` の "Tomorrow Next" | flow 寄り（毎日ロール） |

### 2.2 flow（時系列、追記、腐っても害が小さい）

| カテゴリ | SSoT | 更新ルール |
|---------|------|----------|
| 開発日誌・日報 | `~/Obsidian/Daily/YYYY-MM-DD.md` | 時系列追記、削除しない |
| AI組織議事録 | `.company/meetings/YYYY-MM-DD_<topic>.md` | 時系列追記 |
| AI組織内部ログ | `.company/Logs/` | 時系列、必要なら月次archive |
| 取り込み待ち資料 | `~/Obsidian/inbox/` | 処理完了で削除（30日経過で要処理リマインド） |
| Outputs（生成物） | `~/Obsidian/outputs/` | 時系列、月次archive可 |
| Raw（取得した生データ） | `~/Obsidian/raw/` | 時系列、月次archive可 |
| プロダクト議事録 | `~/Obsidian/Projects/<product>/` | 時系列 |
| 設計検討中ドラフト | `~/Obsidian/Ideas/` | flow、stock昇格時に正式化 |

### 2.3 外部SSoT（Claudeは参照のみ）

| カテゴリ | SSoT | アクセス |
|---------|------|---------|
| 顧客 | Notion DB | mcp__notion 経由 |
| 会計 | freee API | mcp__freee 経由 |
| カレンダー | Google Calendar | mcp__google-calendar 経由 |
| メール | Gmail | mcp__gmail 経由 |
| **Credentials**（spec #6で別途定義） | **移行中**: 各プロダクト `.env` 散在<br>**移行後**: Bitwarden Vault (無料プラン) | 移行中は `.env` 直接編集禁止<br>移行後は `bw` CLI 経由 |
| **Cron / 自動化スケジュール一覧** ⭐ | `~/Obsidian/context/cron-inventory.md`（新規・索引） | VPS/launchd/GHA/CronCreate の4箇所を**索引化**（次節参照） |

⭐ = 新規追加カテゴリ（現状散在しているもの）

---

## 3. flow → stock 昇格ルール

### 3.1 原則

> 「議事録を読んで、**新事実だけ**ストックに昇格させる」

flow に書かれていることのほとんどは時系列イベント（進捗報告、議論、検討）であり stock 化不要。
**stock化が必要なのは「未来のClaudeが知るべき確定事実」のみ**。

### 3.2 stock 昇格判定フロー

```
flow に書かれた内容
  ↓
Q1. これは「現時点で正しい事実」か？（議論や検討じゃなく確定事項か）
  ↓ Yes
Q2. 該当する stock SSoT は存在するか？
  ↓ Yes → 既存 stock を更新（古い記述を上書き）
  ↓ No  → 新規 stock 作成 or 既存近接 stock に追記
```

### 3.3 昇格実施タイミング

**spec #5（Dreams 週次振り返り）で自動化** + **spec #1（月次棚卸し）で漏れ確認**。

本 spec 単独では「ルールの明文化」までを担当。実行は spec #5 に委譲。

### 3.4 stock側の整合チェック

stock 更新時の必須チェック:
- 既存 stock と矛盾する場合 → どちらが正か明示確認
- 更新したら `last_confirmed: YYYY-MM-DD` を frontmatter に記載（Gotchas spec #2 と同様）

---

## 4. 既存重複の整理計画（ポインタのみ）

実作業は**月次棚卸し（spec #1）のサイクルで段階実施**。本 spec では問題定義のみ。

### 4.1 識別されている重複

| 重複 | 整理方針 |
|------|---------|
| `.company/Logs/` ↔ `Obsidian/Daily/` | `.company/Logs/` = AI組織内部ログ（部署別動作記録）<br>`Obsidian/Daily/` = 人間視点の日報<br>**役割分離で重複解消** |
| `Obsidian/Projects/<product>/` ↔ `memory/<product>.md` | `Obsidian/Projects/` = flow（議事録・検討）<br>`memory/<product>.md` = stock（最新状態）<br>**役割分離で重複解消、stock側のみClaude常時参照** |
| `Obsidian/inbox/` ↔ `memory/` 直下 | inbox = 取り込み待ち（処理後削除）<br>memory/ = 取り込み済み<br>**境界明文化** |
| 散在する .env ファイル | spec #6 で 1Password 移行 |
| 4箇所の cron/自動化スケジュール | 新規 `cron-inventory.md` で索引化 |

### 4.2 段階移行スケジュール

月次棚卸し（spec #1）の②セクションで「次月着手する重複」を1つ選定 → 翌月までに人間が整理。
焦らず6ヶ月かけて全部消化する想定。

---

## 5. CLAUDE.md への追加内容

### 5.1 追加先

`~/Claude-Workspace/CLAUDE.md`（プロジェクトレベル）に追加。
`~/.claude/CLAUDE.md`（グローバル）には追加しない（個人事業主の業務知識は Workspace 側に寄せる）。

### 5.2 追加セクション（プレビュー）

```markdown
## SSoT Map（情報のありかマップ）

困った時、まずこの表を参照する。

### Stock（最新が正・上書き）
- ユーザープロフィール → ~/Obsidian/context/identity.md
- ビジネス概要 → ~/Obsidian/context/business.md
- 技術環境 → ~/Obsidian/context/tech-setup.md
- プロダクト最新状態 → memory/<product>.md
- Gotchas → memory/feedback_*.md
- 広告アカウント → ~/Obsidian/context/ad-accounts.md
- VPS情報 → memory/vps-hetzner.md
- SaaS契約一覧 → ~/Obsidian/context/subscriptions.md
- 設計仕様書 → docs/superpowers/specs/

### Flow（時系列・追記）
- 開発日誌 → ~/Obsidian/Daily/
- AI組織議事録 → .company/meetings/
- 取り込み待ち → ~/Obsidian/inbox/

### 外部SSoT（Claudeは参照のみ）
- 顧客 → Notion DB
- 会計 → freee
- Credentials → 1Password（spec #6で移行予定、現状は .env散在）
- Cron索引 → ~/Obsidian/context/cron-inventory.md

### TODO管理
- 当日タスク → ~/Obsidian/Daily/<今日>.md の "Tomorrow Next"
- TodoWrite はセッション内タスクのみ、永続化しない
```

---

## 6. 新規作成が必要なファイル

実装フェーズで以下を作成（テンプレのみ、中身は段階埋め）:

1. `~/Obsidian/context/ad-accounts.md` — Meta/Google/LinkedIn 等のID集約
2. `~/Obsidian/context/subscriptions.md` — Anthropic / OpenAI / fal.ai / Notion / freee 等の月額・契約日
3. `~/Obsidian/context/cron-inventory.md` — VPS cron / launchd / GitHub Actions / CronCreate の4箇所索引

### 6.1 cron-inventory.md の作成手順詳細

「動いてる自動化が4箇所に散在」問題（CLAUDE.md「サイレント故障対策」と直結）の解消。
**1ファイルに索引化**することで、月次棚卸し（spec #1）が漏れなく検査できる。

#### 6.1.1 4箇所の棚卸しコマンド

| 場所 | 棚卸しコマンド | 出力例 |
|------|-------------|-------|
| **VPS cron** (Contabo 46.250.252.99) | `ssh trustlink-prod 'crontab -l && ls -la /etc/cron.d/'` | `*/5 * * * * /opt/scripts/monitor-anthropic-credit.sh` |
| **ローカル launchd** | `ls ~/Library/LaunchAgents/com.trustlink.*.plist && launchctl list \| grep trustlink` | `com.trustlink.d-manager`, `com.trustlink.google-ads-report` |
| **GitHub Actions** | `gh workflow list -R trust-svg/<repo>`（主要4リポ: ai-daily-digest, ebay-inventory-tool, factoring-media, saimu-media） | `daily-digest.yml`, `inventory-check.yml` |
| **CronCreate（Claude）** | `CronList` ツール | 月次棚卸し / Dreams 週次 等 |

#### 6.1.2 cron-inventory.md フォーマット

```markdown
# Cron / 自動化スケジュール一覧

**最終棚卸し日**: 2026-05-14

## VPS cron (Contabo 46.250.252.99, TZ=Asia/Tokyo)

| schedule (JST) | command | 用途 | 通知先 |
|----------------|---------|------|-------|
| `*/5 * * * *` | `/opt/scripts/monitor-anthropic-credit.sh` | API残高監視 | Telegram bmanager |
| `0 9,12,19 * * *` | `cd /opt/apps/saimu-media && docker compose run --rm sns-engine python poster.py` | saimu Threads投稿 | (なし、ログのみ) |
| ... | ... | ... | ... |

## ローカル launchd (~/Library/LaunchAgents/)

| plist | schedule | 用途 | 通知先 |
|-------|----------|------|-------|
| `com.trustlink.d-manager.plist` | 常駐 | Discord AI組織Bot | Discord |
| `com.trustlink.google-ads-report.plist` | 毎日 09:30 | Google広告レポート | Discord |
| ... | ... | ... | ... |

## GitHub Actions

| repo | workflow | schedule | 用途 |
|------|----------|----------|------|
| `trust-svg/ai-daily-digest` | `daily-digest.yml` | `0 21 * * *` UTC (06:00 JST) | AIニュース配信 |
| `trust-svg/ebay-inventory-tool` | `inventory-check.yml` | `0 23 * * *` UTC (08:00 JST) | ヤフオク・Yahooフリマ |
| ... | ... | ... | ... |

## CronCreate (Claude remote agents)

| name | schedule (JST) | 用途 | 出力先 |
|------|---------------|------|-------|
| monthly-cleanup-ritual | `0 9 1 * *` | 月次棚卸し（spec #1） | Obsidian/Daily/ + Telegram |
| dreams-weekly | `0 8 * * 6` | Dreams 週次振り返り（spec #5） | Obsidian/Daily/ + Telegram |
```

#### 6.1.3 初回作成タスク

1. 上記4コマンドを実行 → 結果を貼り付け
2. 各 cron に「**用途**」と「**通知先**」列を埋める（コマンドだけでは意図不明なため）
3. **死んでる cron 候補**を別セクション「## 要確認・廃止候補」に分離
4. 完成したファイルを `~/Obsidian/context/cron-inventory.md` に保存

#### 6.1.4 更新タイミング

- **新規 cron 追加時**: 該当セクションに行追加（Claude が cron 作成時、自動でこのファイルも更新）
- **月次棚卸し（spec #1）時**: 4コマンドを再実行 → diff を取り、ファイル外の cron があれば追加 or 廃止判断
- **last_confirmed 更新**: 月次棚卸し完了時にファイル先頭の「最終棚卸し日」を更新

---

## 7. Gotchas / リスク

### リスク1: SSoT Map と現実がズレる

Map を作っても、Hiroが Map と違う場所に新規ファイル作れば形骸化する。

**対策**:
- 月次棚卸し（spec #1）で「Map にない場所にファイルが増えてないか」検査項目追加
- Claude側は新規ファイル作成時、Map参照して場所決定（CLAUDE.md規約で徹底）

### リスク2: flow → stock 昇格が機械化されると、ニュアンスが落ちる

人間が判断すべき微妙な事実（「これは確定？それとも検討中？」）を Claude が機械的に昇格すると誤った stock が生まれる。

**対策**:
- spec #5（Dreams）で「昇格**提案**」までを Claude が担当、最終昇格は人間が承認
- 自動昇格は禁止

### リスク3: Map が肥大化して逆に読みにくくなる

カテゴリが12個もあると、Claude が毎回全部読むのは過剰。

**対策**:
- CLAUDE.md には簡潔版（カテゴリ名 → パスのみ）を載せる
- 詳細は本 spec を参照すればよい（CLAUDE.md にはspec へのリンクのみ）

---

## 8. 受け入れ基準

- [ ] `~/Claude-Workspace/CLAUDE.md` に SSoT Map セクションが追加されている
- [ ] 新規 3ファイル（ad-accounts / subscriptions / cron-inventory）のテンプレが作成されている
- [ ] 各テンプレに「現状確認できた情報」が**最低1件ずつ**書かれている（空ファイル禁止）
- [ ] 月次棚卸し（spec #1）に「Map逸脱検査」が追加されている
- [ ] CLAUDE.md からspec本体へのリンクが張られている

---

## 9. 依存関係

- 先行: なし（独立着手可）
- 後続:
  - spec #5（Dreams）: 本 spec の flow→stock 昇格ルールを実装する側
  - spec #6（Credentials）: 本 spec の Credentials カテゴリの具体実装
  - spec #1 で更新: Map逸脱検査を月次棚卸しに追加
