# ebay-agent Phase 3: 在庫台帳 → 仕入れ記録 完全移行 設計仕様書

## 概要

在庫台帳（InventoryItem）の全機能・全フィールドを仕入れ記録（Procurement）に移行し、在庫台帳を廃止する。Phase 2 で Procurement に eBay連携フィールド8つを追加済み。Phase 3 では UI・API・スクレイピング機能をすべて Procurement に統合する。

**絶対要件:** 在庫台帳の機能と項目は完璧に仕入れ記録に移すこと。

## ゴール

- Procurement を仕入れ実績の唯一の管理元（SSoT）にする
- 在庫台帳タブを非表示化（Phase 3）→ Phase 4 で完全削除
- `stock.js`（1473行）の全機能を `procurement-table.js` として再実装（Approach B: ゼロから書き直し）

## 設計決定事項

| 質問 | 決定 |
|---|---|
| スクレイピング機能 | 移行する（よく使う） |
| UI スタイル | テーブル表示に統一（在庫台帳と同様） |
| 実装アプローチ | B: Procurement専用JSをゼロから書き直し |
| `/api/stock/from-procurement/{proc_id}` | Phase 3 で完全削除 |
| テーブルソート | 全列ソート可能 |
| 表示列 | ユーザーが選択可（列トグル + ドラッグ並べ替え） |

---

## セクション1: データモデル変更

### Procurement モデルへの追加

`database/models.py` の `Procurement` クラスに1フィールドを追加：

```python
JST = timezone(timedelta(hours=9))  # main.py 冒頭に既存の定数を使用

updated_at: Mapped[datetime] = mapped_column(
    DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST)
)
```

### 追加しないフィールド

- `sale_record_id`: SalesRecord との紐付けは `sku` JOIN で代替可能。歴史的経緯で InventoryItem にあるだけで Procurement では不要。

### InventoryItem → Procurement フィールド対応表

| InventoryItem フィールド | Procurement フィールド | 備考 |
|---|---|---|
| `id` | `id` | |
| `stock_number` | `stock_number` | ✅ Phase 2追加済み |
| `sku` | `sku` | ✅ |
| `title` | `title` | ✅ |
| `purchase_price_jpy` | `purchase_price_jpy` | ✅ |
| `consumption_tax_jpy` | `consumption_tax_jpy` | ✅ |
| `shipping_cost_jpy` | `shipping_cost_jpy` | ✅ |
| `purchase_date` | `purchase_date` | ✅ |
| `purchase_source` | `platform` | ✅ 同等（名前が違うだけ） |
| `purchase_url` | `url` | ✅ 同等 |
| `seller_id` | `seller_id` | ✅ |
| `seller_url` | `seller_url` | ✅ |
| `quantity` | `quantity` | ✅ |
| `location` | `location` | ✅ Phase 2追加済み |
| `condition` | `condition` | ✅ |
| `status` | `status` | ✅（ステータス値を拡張） |
| `ebay_item_id` | `ebay_item_id` | ✅ Phase 2追加済み |
| `ebay_order_id` | `ebay_order_id` | ✅ Phase 2追加済み |
| `ebay_price_usd` | `ebay_price_usd` | ✅ Phase 2追加済み |
| `listed_at` | `listed_at` | ✅ Phase 2追加済み |
| `sold_at` | `sold_at` | ✅ Phase 2追加済み |
| `shipped_at` | `shipped_at` | ✅ Phase 2追加済み |
| `sale_record_id` | —（不要） | SKU JOINで代替 |
| `notes` | `notes` | ✅ |
| `image_url` | `image_url` | ✅ |
| `screenshot_path` | `screenshot_path` | ✅ |
| `created_at` | `created_at` | ✅ |
| `updated_at` | `updated_at` | ❌ 要追加 |

### Procurement ステータス値の統一

InventoryItem のステータス値を Procurement に取り込む：

| 値 | 意味 |
|---|---|
| `purchased` | 購入済み（注文済み相当） |
| `received` | 入荷済み |
| `listed` | 出品中 |
| `sold` | 販売済み |
| `shipped` | 発送済み |
| `returned` | 返品 |
| `cancelled` | キャンセル |

---

## セクション2: APIエンドポイント

### 新規追加（`/api/procurements/*`）

| エンドポイント | 対応する `/api/stock/*` | 目的 |
|---|---|---|
| `GET /api/procurements/stats` | `/api/stock/stats` | KPI（件数・総原価・ステータス別） |
| `POST /api/procurements/auto-sku` | `/api/stock/auto-sku` | 管理番号自動採番（P-001形式） |
| `POST /api/procurements/bulk-delete-ids` | `/api/stock/bulk-delete-ids` | 複数件一括削除 |
| `POST /api/procurements/bulk-import` | `/api/stock/bulk-import` | TSV/CSV一括取込 |
| `POST /api/procurements/scrape/mercari` | `/api/stock/scrape/mercari` | メルカリスクレイプ起動 |
| `POST /api/procurements/scrape/mercari/import/{job_id}` | `/api/stock/scrape/mercari/import/{job_id}` | 結果をProcurementに保存 |
| `POST /api/procurements/scrape/yahoo` | `/api/stock/scrape/yahoo` | ヤフオクスクレイプ |
| `POST /api/procurements/scrape/yahoo/import/{job_id}` | 同上 import | |
| `POST /api/procurements/scrape/yahoo-flea` | `/api/stock/scrape/yahoo-flea` | Yahooフリマ |
| `POST /api/procurements/scrape/yahoo-flea/import/{job_id}` | 同上 import | |
| `POST /api/procurements/scrape/rakuma` | `/api/stock/scrape/rakuma` | ラクマ |
| `POST /api/procurements/scrape/rakuma/import/{job_id}` | 同上 import | |
| `POST /api/procurements/scrape/hardoff` | `/api/stock/scrape/hardoff` | ハードオフ |
| `POST /api/procurements/scrape/hardoff/import/{job_id}` | 同上 import | |
| `POST /api/procurements/scrape/surugaya` | `/api/stock/scrape/surugaya` | 駿河屋 |
| `POST /api/procurements/scrape/surugaya/import/{job_id}` | 同上 import | |

### スクレイプ status ポーリング（既存を流用）

`GET /api/stock/scrape/status/{job_id}` はジョブIDがグローバルなため新規作成不要。Procurement スクレイプでもそのまま使用する。

### Phase 3 で削除するエンドポイント

- `POST /api/stock/from-procurement/{proc_id}` → 在庫台帳廃止により不要

### `/api/stock/*` 全体の削除はPhase 4

在庫台帳タブを非表示にした後、動作確認が取れてから削除する。

### スクレイプ import 時のフィールドマッピング

スクレイプ結果を Procurement に保存する際のマッピング：

| スクレイプ結果フィールド | Procurement フィールド |
|---|---|
| title | title |
| price | purchase_price_jpy |
| url | url |
| image_url | image_url |
| seller_id | seller_id |
| platform（固定値） | platform |
| purchase_date（現在日時） | purchase_date |

---

## セクション3: UI・JS構成

### ファイル一覧

| ファイル | アクション | 内容 |
|---|---|---|
| `static/js/procurement-table.js` | **新規作成** | 仕入れ記録テーブル専用JS（~1000行） |
| `templates/pages/_sourcing_content.html` | **大幅改修** | カードUIをテーブルUIに置換 |
| `templates/pages/sourcing.html` | **修正** | 在庫台帳タブを `display:none` で非表示 |
| `main.py` | **追記** | 新エンドポイント群（stats/auto-sku/bulk/scrape） |
| `database/models.py` | **修正** | Procurementに `updated_at` を追加 |
| `tests/test_procurement_integration.py` | **追記** | 新機能テスト（stats/auto-sku/bulk-delete/scrape） |

### `procurement-table.js` 機能構成

stock.js の構造を参考に、Procurement 専用として再実装：

```
ソート状態管理 (procSortCol / procSortDir)
カラム定義 (PROC_COLUMNS) + ローカルストレージ保存
  - id列は常に非表示
  - デフォルト表示: No./商品名/SKU/原価/仕入日/プラットフォーム/ステータス
  - 追加可能: 保管場所/eBay ItemID/eBay 販売額/出品日/売却日/発送日/数量/状態
列ヘッダーのドラッグ並べ替え
為替レート取得（/api/exchange-rate）
stats KPI バー表示（/api/procurements/stats）
テーブル描画 renderProcRows()
  - ステータスバッジ
  - プラットフォームバッジ
  - eBay ItemID → ebay.com リンク
  - スクリーンショット列（有り/無し表示）
行クリックで詳細パネル表示（既存）
追加モーダル（既存UIを再利用）
編集モーダル（既存UIを再利用）
URL自動検出 ✅（Phase 2済み）
スクリーンショット D&D ✅（Phase 2済み）
スクレイピング UI
  - メルカリ/ヤフオク/ラクマ/Yahooフリマ/ハードオフ/駿河屋
  - 各プラットフォーム: 起動 → ポーリング → インポート確認 → 保存
一括削除（チェックボックス選択 + バルクバー）
一括インポート（TSV/CSV）
管理番号自動採番（P-001形式）
設定（スクリーンショット保存ディレクトリ）
```

### UIレイアウト

```
[KPIバー]
 総件数: 123 | 総原価: ¥456,000 | 出品中: 45 | 販売済: 30 | 発送済: 20

[ツールバー]
 [ステータス▼] [プラットフォーム▼] [検索...] [列選択▼] | [追加] [スクレイプ▼] [一括削除]

[テーブル]
 ☐ | No.↕ | 商品名↕ | SKU↕ | 原価↕ | 仕入日↕ | プラットフォーム↕ | ステータス↕ | ...
 ─────────────────────────────────────────────────────────────────────
 ☐ | P-001 | カメラ   | CAM1 | ¥3,000 | 2026-05-01 | メルカリ       | 出品中      |

[バルクアクションバー（選択時に浮上）]
 3件選択中 [削除]
```

在庫台帳タブは `display: none` で非表示（Phase 4 で HTML ごと削除）。

---

## セクション4: テスト方針

各機能に対して `test_procurement_integration.py` にテストを追加する。

| テスト | 内容 |
|---|---|
| `test_procurement_stats` | stats エンドポイントが件数・原価を正しく返す |
| `test_procurement_auto_sku` | P-001 → P-002 と連番で採番される |
| `test_procurement_bulk_delete` | 複数IDを一括削除できる |
| `test_procurement_bulk_import` | TSVを貼り付けてインポートできる |
| `test_procurement_scrape_mercari_mock` | スクレイプ起動→ポーリング→インポートの流れ |
| `test_procurement_updated_at` | レコード更新時に updated_at が変わる |

テストコマンド（ebay-agent/ ディレクトリから）:
```bash
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

---

## Phase 4（将来・本設計の対象外）

Phase 3 完了後、動作確認が取れたら：

1. `database/models.py` から `InventoryItem` クラスを削除
2. `main.py` から `/api/stock/*` エンドポイント全削除（~1200行）
3. `static/js/stock.js` を削除
4. `templates/pages/_in_ledger_content.html` を削除
5. `templates/pages/sourcing.html` から在庫台帳タブのHTMLを削除
6. DBマイグレーション: `inventory_items` テーブルをDROP

Phase 4 は別スペック・別プランとして実施する。
