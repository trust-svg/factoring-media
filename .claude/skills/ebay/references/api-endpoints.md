# eBay Agent Hub — API エンドポイント一覧

Base URL: `http://localhost:8000` (本番: Railway URL)

---

## ページルート (HTML)

| Method | Path | 説明 |
|---|---|---|
| GET | `/` | Overview ダッシュボード |
| GET | `/inventory` | 在庫一覧 |
| GET | `/pricing` | 価格分析 |
| GET | `/sourcing` | 仕入れ・調達 |
| GET | `/analytics` | 売上分析 |
| GET | `/messages` | メッセージ |
| GET | `/agent` | AIエージェントチャット |

---

## REST API

### ダッシュボード
| Method | Path | 説明 |
|---|---|---|
| GET | `/api/dashboard` | KPI統計（出品数、在庫、売上サマリー） |
| GET | `/api/activity/recent?limit=10` | 最近のアクティビティ |

### 在庫管理
| Method | Path | 説明 |
|---|---|---|
| GET | `/api/listings` | 全出品一覧 |
| GET | `/api/listings/{sku}` | SKU別詳細 |
| POST | `/api/inventory/sync` | eBayから在庫同期 |

### 価格
| Method | Path | 説明 |
|---|---|---|
| GET | `/api/pricing/alerts` | 価格アラート一覧 |
| GET | `/api/pricing/history/{sku}?days=30` | SKU別価格履歴 |
| POST | `/api/pricing/monitor` | 競合価格一括チェック |

### 売上
| Method | Path | 説明 |
|---|---|---|
| POST | `/api/sales/sync` | 売上データ同期 |
| GET | `/api/sales/analytics?days=30` | 売上分析（日次推移+トップ商品+サマリー） |

### 仕入れ
| Method | Path | 説明 |
|---|---|---|
| GET | `/api/procurements` | 仕入れ一覧 |
| POST | `/api/procurements` | 仕入れ記録追加 |
| GET | `/api/procurements/{sku}` | SKU別仕入れ |
| PUT | `/api/procurements/{id}` | 仕入れ更新（ステータス等） |

### マージン計算
| Method | Path | 説明 |
|---|---|---|
| POST | `/api/margin` | 利益率計算 |
| GET | `/api/exchange-rate` | 為替レート |

### メッセージ
| Method | Path | 説明 |
|---|---|---|
| GET | `/api/messages?days=14` | メッセージ一覧 |
| POST | `/api/messages/draft` | AI返信ドラフト生成 |
| POST | `/api/messages/process` | 未読一括処理 |

### AIエージェント
| Method | Path | 説明 |
|---|---|---|
| POST | `/api/agent` | 自然言語指示 → ツール実行 |

Request body: `{"message": "自然言語の指示"}`
Response: `{"response": "結果", "tool_calls": [...], "iterations": N}`

---

## ツール一覧 (26個)

AIエージェント経由で呼び出し可能なツール:

### 在庫系
- `check_inventory` — 在庫確認（out_of_stock_only フィルタ）
- `get_dashboard_stats` — ダッシュボード統計

### 出品系
- `generate_listing` — AI出品ドラフト生成
- `analyze_seo` — SEOスコア分析
- `optimize_listing` — リスティング最適化提案
- `update_listing` — eBay出品更新 ⚠️破壊的
- `search_ebay` — eBay商品検索（市場調査）

### 価格系
- `analyze_pricing` — SKU別競合価格分析
- `run_price_monitor` — 一括価格チェック
- `get_price_advice` — AI価格提案
- `batch_price_advice` — 一括価格提案
- `apply_price_change` — 価格変更適用 ⚠️破壊的
- `get_exchange_rate` — USD/JPY為替
- `calculate_margin` — 利益率計算

### 仕入れ系
- `search_sources` — 日本5サイト横断検索
- `record_procurement` — 仕入れ記録
- `update_procurement` — 仕入れ更新

### 需要分析系
- `research_demand` — 市場需要分析
- `compare_categories` — カテゴリ比較
- `run_research` — AI包括的リサーチ
- `generate_and_preview` — 出品プレビュー生成

### コミュニケーション系
- `sync_sales` — 売上データ同期
- `get_sales_analytics` — 売上分析
- `check_messages` — メッセージ確認
- `draft_reply` — AI返信ドラフト
- `process_unread_messages` — 未読一括処理

---

## スケジュールジョブ

| ジョブ | スケジュール | 内容 |
|---|---|---|
| 競合価格モニター | 6時間間隔 | 全出品の競合価格チェック |
| 朝のダイジェスト | 毎日 9:00 JST | 出品数・売上・在庫切れ・為替 → LINE |
| 週間レポート | 月曜 10:00 JST | 週間売上・利益・トップ商品 → LINE |
| 売上自動同期 | 毎日 8:00 JST | eBay注文データ自動同期 |

---

## POST /api/agent リクエスト例

```bash
# 在庫確認
curl -X POST http://localhost:8000/api/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Check inventory status"}'

# 仕入れ検索
curl -X POST http://localhost:8000/api/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Search for Nakamichi Dragon on Japanese marketplaces"}'

# 売上分析
curl -X POST http://localhost:8000/api/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Show sales analytics for the last 30 days"}'
```

---

## POST /api/margin リクエスト例

```json
{
  "source_price_jpy": 15000,
  "sale_price_usd": 180.00,
  "shipping_cost_jpy": 2500
}
```

Response:
```json
{
  "source_price_jpy": 15000,
  "shipping_cost_jpy": 2500,
  "total_cost_jpy": 17500,
  "total_cost_usd": 116.67,
  "sale_price_usd": 180.00,
  "ebay_fees_usd": 23.40,
  "profit_usd": 39.93,
  "margin_pct": 22.2,
  "profitable": true
}
```
