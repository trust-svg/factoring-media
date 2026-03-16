---
name: ebay
description: >
  eBay輸出ビジネスの運用スキル。出品自動化・リスティング最適化・価格戦略・仕入れ管理・売上分析・
  バイヤー対応を、eBay Agent Hub のAPIとツール群を通じて実行します。
  各タスクを細かく分けたサブコマンドで構成し、単体でもチェーン実行でも使えます。
  「出品して」「リスティング最適化」「価格チェック」「仕入れ」「売上分析」「メッセージ確認」
  「eBay」「listing」「pricing」「sourcing」「analytics」で使ってください。
argument-hint: [list|optimize|price|source|analyze|messages|monitor|research] [options]
---

# eBay — 輸出ビジネス運用スキル

eBay Agent Hub（FastAPI + 26ツール + AIエージェント）を活用し、
eBay輸出ビジネスの主要業務をClaude Codeから直接実行する。

## アーキテクチャ

```
Claude Code (このスキル)
  ↓ API呼び出し or コード実行
eBay Agent Hub (FastAPI)
  ├── tools/       ← 26個のツール定義
  ├── agents/      ← AIオーケストレーター
  ├── pricing/     ← 価格エンジン
  ├── sourcing/    ← 仕入れ検索
  ├── comms/       ← 売上分析・LINE通知
  └── database/    ← SQLAlchemy models
```

### 前提

- eBay Agent Hub が起動中であること
- サーバーURL: `http://localhost:8000`（Railway: 環境変数 `EBAY_HUB_URL`）
- eBay API トークンが `.env` に設定済み

---

## サブコマンド一覧

| コマンド | 用途 | 例 |
|---|---|---|
| `/ebay list <商品名 or シートURL>` | 新規出品（単品 or バッチ） | `/ebay list Nakamichi Dragon` or `/ebay list <Sheet URL>` |
| `/ebay optimize [SKU]` | リスティング最適化 | `/ebay optimize` (全件) |
| `/ebay price [SKU]` | 価格分析・調整 | `/ebay price SKU123` |
| `/ebay source <キーワード>` | 仕入れ検索・調達 | `/ebay source ビンテージ シンセサイザー` |
| `/ebay analyze [期間]` | 売上分析レポート | `/ebay analyze 30` |
| `/ebay messages` | バイヤーメッセージ対応 | `/ebay messages` |
| `/ebay monitor` | 24時間監視設定確認 | `/ebay monitor` |
| `/ebay research <テーマ>` | 市場調査・需要分析 | `/ebay research turntable market` |
| `/ebay` | ステータス概要 | `/ebay` |

---

## `/ebay` — ステータス概要

引数なしで実行。ダッシュボードの主要KPIを表示。

### 手順

1. `GET /api/dashboard` でダッシュボード統計を取得
2. 以下を整理して報告:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 eBay Agent Hub — ステータス
━━━━━━━━━━━━━━━━━━━━━━━━━━━
出品数: XX件 ｜ 在庫あり: XX ｜ 在庫切れ: XX
仕入れ候補: XX ｜ 調達中: XX

💰 30日間パフォーマンス
売上: $X,XXX ｜ 利益: $XXX ｜ マージン: XX%
為替: ¥XXX/USD

⚡ 要対応
・在庫切れ XX 件 → `/ebay optimize` で対応
・価格アラート XX 件 → `/ebay price` で確認
・未読メッセージ XX 件 → `/ebay messages` で対応
```

---

## `/ebay list` — 出品自動化（単品 & バッチ対応）

### モード A: 単品出品 `/ebay list <商品名>`

1. **市場調査**: `research_demand` で市場価格を確認
2. **出品生成**: `generate_listing` でタイトル・説明文・スペック生成
3. **マージン計算**: `calculate_margin` で利益率を計算
4. **プレビュー表示** → ユーザー承認 → `create_draft_listing` で下書き登録
5. 「公開して」→ `publish_draft_listings` で eBay に公開

### モード B: バッチ出品 `/ebay list <Sheet URL or CSV>`

リサーチスプレッドシートから一括で下書き登録する。

**スプレッドシートの想定カラム:**

| 商品名 | カテゴリNo | 販売価格(USD) | 送料プラン | 仕入れURL | eBay URL | コンディション | メモ |
|--------|-----------|--------------|-----------|----------|---------|-------------|------|

#### 手順

1. `read_listing_sheet` でスプレッドシート/CSV読み取り
2. 各行に対して:
   a. eBay URLからキーワード抽出 → SEOタイトル生成
   b. `get_category_aspects` でカテゴリの必須Item Specifics取得
   c. `generate_listing` でタイトル・説明文・Item Specifics生成
   d. 不足Item Specificsはネット検索で補完
   e. `create_draft_listing` で下書き登録
3. 完了サマリーテーブル表示:

```
● 全5件の下書き登録が完了しました。

---
完了サマリー

| 行 | 商品                    | Item ID      | 価格   |
|----|------------------------|-------------|--------|
| 2  | Roland JP-8080 Synth   | ITEM-A1B2C3 | $280   |
| 3  | Technics SL-1200MK5    | ITEM-D4E5F6 | $117   |
| 4  | Nakamichi Dragon       | ITEM-G7H8I9 | $354   |
| 5  | Accuphase E-305        | ITEM-J0K1L2 | $259   |
| 6  | TASCAM 424 MKIII       | ITEM-M3N4O5 | $82    |

eBay Seller Hub（スケジュール済みリスト）で内容をご確認ください：
https://www.ebay.com/sh/lst/scheduled

確認後「公開して」と指示いただければ順次出品を開始します。
```

4. ユーザーが「公開して」→ `publish_draft_listings` で全件公開

### モード C: 「出品して」（ショートカット）

引数なしの「出品して」は以下の順で処理:
1. 事前に登録されたスプレッドシートURLを確認（.env `LISTING_SHEET_URL`）
2. あればモードB実行、なければユーザーにソース指定を依頼

---

## `/ebay optimize [SKU]` — リスティング最適化

既存出品のSEO・タイトル・説明文を最適化する。

### SKU指定あり

1. `POST /api/agent` → `analyze_seo` で現状スコア取得
2. `POST /api/agent` → `optimize_listing` で改善提案生成
3. Before/After を表示

### SKU指定なし（一括）

1. `GET /api/listings` で全出品取得
2. SEOスコアが低い（60未満）出品を抽出
3. 各出品に対して改善提案を生成
4. 優先順位付きで提示:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 最適化が必要な出品 (X件)
━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. [SKU] [タイトル] — SEO: 35/100
   問題: タイトルが短い、スペック不足
   改善: [提案]

2. [SKU] [タイトル] — SEO: 42/100
   ...
```

---

## `/ebay price [SKU]` — 価格分析・調整

### SKU指定あり

1. `POST /api/agent` → `analyze_pricing` で競合価格取得
2. `POST /api/agent` → `get_price_advice` でAI提案
3. 価格履歴チャートのURLを提示: `/pricing` ページ参照

### SKU指定なし（一括）

1. `GET /api/pricing/alerts` でアラート一覧取得
2. 価格差が大きい順にソート
3. `POST /api/agent` → `batch_price_advice` で一括提案

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 価格アラート (X件)
━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 値下げ推奨:
  [SKU] $150 → $129 提案 (競合平均: $125)

🟡 要確認:
  [SKU] $89 (競合平均: $95 — 値上げ余地あり)

適用するには: `/ebay price apply SKU123 129.99`
```

---

## `/ebay source <キーワード>` — 仕入れ検索・調達

### 手順

1. `POST /api/agent` → `search_sources` で5サイト横断検索
2. `POST /api/agent` → `calculate_margin` で各候補の利益率計算
3. 利益率順にソート

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 仕入れ候補: [キーワード]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. [タイトル] — ¥12,000 (メルカリ)
   eBay想定: $150 | 利益: $XX (XX%) ✅
   URL: [link]

2. [タイトル] — ¥8,500 (ヤフオク)
   eBay想定: $120 | 利益: $XX (XX%) ✅

仕入れ記録: `/ebay source record <ID>`
```

### 仕入れ記録

`/ebay source record` → `POST /api/procurements` で購入記録をDBに保存

---

## `/ebay analyze [期間]` — 売上分析

### 手順

1. `POST /api/sales/sync` で最新データ同期
2. `GET /api/sales/analytics?days=N` で分析データ取得
3. レポート生成:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 売上レポート (過去 [N] 日)
━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 サマリー
売上: $X,XXX | 利益: $XXX | マージン: XX%
注文数: XX件 | 平均利益/件: $XX
仕入れ原価合計: ¥XXX,XXX

🏆 トップ商品 (利益順)
1. [タイトル] — $XX利益 × X件
2. [タイトル] — $XX利益 × X件

📊 トレンド
[直近7日の売上推移を簡潔に]

💡 インサイト
・[利益率が高いカテゴリ]
・[在庫切れで機会損失している商品]
・[価格調整の余地がある商品]
```

---

## `/ebay messages` — バイヤーメッセージ対応

### 手順

1. `GET /api/messages?days=14` でメッセージ取得
2. 未読をカテゴリ別に分類（返品/質問/値引き/その他）
3. AI返信ドラフト一括生成: `POST /api/messages/process`

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 バイヤーメッセージ (未読: X件)
━━━━━━━━━━━━━━━━━━━━━━━━━━━

【要返信】
1. [バイヤー名] — [件名]
   要約: [1行要約]
   AI返信案: "[ドラフト冒頭30文字...]"

【確認のみ】
・[バイヤー名] — 発送通知確認
```

---

## `/ebay monitor` — 在庫モニター（ebay-inventory-tool）

在庫切れ商品の仕入元自動検索ツール。GitHub Actionsで毎日2回自動実行。

### システム概要

- 場所: `products/ebay-inventory-tool/`
- GitHub: `trust-svg/ebay-inventory-tool`
- 実行: GitHub Actions（毎日2回自動 + 手動トリガー可能）
- 通知: メール（finvit.r@gmail.com）

### 仕組み

```
eBay Trading API (GetMyeBaySelling)
  → USD出品のみ抽出（currencyIDで判定、Site非対応）
  → 多言語重複除外 → yoroi除外
  → 在庫切れ商品を価格順に2バッチに分割
  → 5サイト横断検索（ヤフオク/メルカリ/Yahoo!フリマ/ラクマ/ブックオフ）
  → 型番フィルタ → スコアリング → ベスト3候補選定
  → HTMLレポート + メール通知
```

### バッチスケジュール

| バッチ | スケジュール | 対象 |
|---|---|---|
| バッチ1 | JST 9:00 (UTC 0:00) | 高価格帯（前半） |
| バッチ2 | JST 15:00 (UTC 6:00) | 低価格帯（後半） |

### 主要数値（2026-03時点）

- eBay全出品: 4,120件（6カ国: US/UK/DE/AU/CA/FR）
- USD出品: 590件
- 在庫切れ: 約267件
- 各バッチ: 約133件（処理時間: 約1.5〜2時間）

### 手動実行

```bash
cd products/ebay-inventory-tool
gh workflow run daily-monitor.yml -f batch=1  # バッチ1
gh workflow run daily-monitor.yml -f batch=2  # バッチ2
```

### ログ確認

```bash
gh run list --limit 5
gh run view <RUN_ID> --log 2>&1 | grep -E "Trading API|eBay自動取得|バッチ|完了"
```

### 設定変更

- 通知先メール: `gh secret set NOTIFY_EMAIL -R trust-svg/ebay-inventory-tool`
- 除外キーワード: `main.py` の `_EXCLUDE_KEYWORDS`
- バッチ分割: `main.py` の `fetch_auto_items(batch=)`

### ファイル構成

```
products/ebay-inventory-tool/
├── main.py              # メイン（キーワード生成/型番フィルタ/スコアリング）
├── ebay_client.py       # eBay API（Trading API/Sell Inventory API）
├── notifier.py          # メール通知（HTML候補リスト付き）
├── exchange_rate.py     # USD→JPY為替
├── report_generator.py  # HTMLレポート生成
├── config.py            # 設定
├── scrapers/            # 5プラットフォームスクレイパー
│   ├── yahoo_auction.py
│   ├── mercari.py
│   ├── paypay_flea.py
│   ├── rakuma.py
│   └── offmall.py
└── .github/workflows/daily-monitor.yml  # 2バッチ自動実行
```

### 技術メモ

- Trading API `GetMyeBaySelling`: `Site`フィールドは常に空 → `currencyID`で国判定
- `DetailLevel=ReturnAll` 必須（通貨コード取得のため）
- 6カ国出品: US(USD)/UK(GBP)/DE(EUR)/AU(AUD)/CA(CAD)/FR(EUR)
- Sell Inventory API: このアカウントでは0件（Trading APIにフォールバック）
- Playwright + stealth mode でスクレイピング（メルカリ/Yahoo!フリマ/ラクマ）

---

## `/ebay research <テーマ>` — 市場調査

### 手順

1. `POST /api/agent` → `run_research` で包括的市場調査を実行
2. 結果を構造化:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 市場調査: [テーマ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 市場概要
売れ筋度: [高/中/低] | 競合度: [高/中/低]
価格帯: $XX 〜 $XXX | 平均: $XX

🎯 有望商品
1. [商品名] — 推定利益 $XX (XX%)
2. [商品名] — 推定利益 $XX (XX%)

💡 推奨アクション
・[具体的なアクション]
```

---

## ワークフロー連携

スキルはチェーン実行可能:

```
/ebay research vintage synthesizer    ← 市場調査
/ebay source ビンテージ シンセサイザー  ← 仕入れ候補検索
/ebay list Korg MS-20                  ← 出品ドラフト生成
/ebay price SKU123                     ← 価格最適化
/ebay analyze 7                        ← 1週間後の売上確認
```

## APIエンドポイント一覧

eBay Agent Hub の全エンドポイントは `references/api-endpoints.md` を参照。

## 注意事項

- `update_listing` と `apply_price_change` は破壊的操作 — 必ずユーザー確認
- eBay API にはレート制限あり — 一括操作は `limit` パラメータで制御
- 仕入れ記録は正確な利益計算の基盤 — 必ず記録を推奨
- LINE通知は `LINE_CHANNEL_TOKEN` と `LINE_USER_ID` が必要
