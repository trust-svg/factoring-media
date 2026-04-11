# Shopify Integration Design — ebay-agent

Date: 2026-04-12

## 概要

eBay輸出ビジネスのマルチチャネル化。eBay出品済み商品をShopify自社ストアにも自動同期し、同梱カードからのリピーターを手数料なしで受け入れる。

**ゴール:**
- eBay新規出品 → Shopifyに自動同期（価格5%引き）
- どちらかで売れた → 両方の在庫を即座に0にする
- 割引率をClaude経由でいつでも変更できる

---

## アーキテクチャ

```
仕入れ（JP） → eBay出品（SKU）
                    ↓ 自動（check_inventoryトリガー）
              Shopify出品（eBay価格 × (1 - discount_rate)）
                    ↕
              在庫双方向同期
              ・Shopify売れ → eBay在庫0（webhook）
              ・eBay売れ → Shopify在庫0（30分スケジューラー）
```

### 追加ファイル構成

```
products/ebay-agent/
  shopify/
    __init__.py
    client.py       Shopify Admin REST API ラッパー（スロットリング込み）
    sync.py         双方向同期ロジック
  database/
    models.py       既存ファイルに追記
  main.py           既存ファイルに追記（webhookエンドポイント）
  tools/
    registry.py     既存ファイルに追記（新ツール定義）
    handlers.py     既存ファイルに追記（新ツール実装）
  config.py         既存ファイルに追記（Shopify設定値）
```

---

## データベース変更

### Listingモデルへの追加カラム

```python
shopify_product_id: Mapped[Optional[str]]   # Shopify product GID (gid://shopify/Product/...)
shopify_synced_at:  Mapped[Optional[datetime]]  # 最終同期日時
```

### 新テーブル: ShopifyConfig

```python
class ShopifyConfig(Base):
    __tablename__ = "shopify_config"

    key:        str       # "discount_rate" | "enabled"
    value:      str       # "0.05" | "true"
    updated_at: datetime
```

用途: `set_shopify_discount`ツールで割引率をDB経由で変更し、再起動不要で反映。

---

## Shopifyモジュール

### shopify/client.py

Shopify Admin REST API（2024-01バージョン）のラッパー。全APIコール間に0.5秒スロットリングを挟む（2 req/秒制限対応）。

```python
class ShopifyClient:
    async def create_product(listing: Listing, price_usd: float) -> str
        # 商品作成 + 画像をShopifyにアップロードしてホスト
        # 戻り値: shopify_product_id

    async def update_product_price(product_id: str, price_usd: float) -> None
        # 価格更新（eBay価格変更時に連動）

    async def set_inventory_zero(product_id: str) -> None
        # 在庫を0にする（sold out）

    async def delete_product(product_id: str) -> None
        # 商品削除（手動削除用）

    async def _upload_images(product_id: str, image_urls: list[str]) -> None
        # eBayのCDN画像をShopifyにコピーしてホスト（URL永続化対策）
```

### shopify/sync.py

```python
async def push_listing_to_shopify(sku: str) -> None
    # 1件のListingをShopifyに同期（未同期の場合のみ作成）
    # discount_rateはShopifyConfigから取得

async def push_all_unsynced() -> dict
    # shopify_product_idがNullの全ListingをShopify同期
    # 戻り値: {"success": N, "failed": M}

async def close_shopify_for_sold_items() -> int
    # eBayで売れたアイテム（quantityが0になったListing）の
    # Shopify在庫を0にする
    # 戻り値: 処理件数

def get_shopify_price(ebay_price_usd: float, discount_rate: float) -> float
    # round(ebay_price_usd * (1 - discount_rate), 2)
```

---

## Webhookエンドポイント

### POST /shopify/webhook/order-created

**main.py**に追加。

```
処理フロー:
1. X-Shopify-Hmac-Sha256ヘッダーを検証（SHOPIFY_WEBHOOK_SECRETで）
2. ペイロードのline_itemsからSKUを抽出
3. 各SKUに対して:
   a. eBay在庫を0に（update_listing経由）
   b. Shopify在庫を0に（念のため）
   c. ListingのfetchedをDB更新
4. 200 OKを返す（Shopifyはタイムアウト5秒以内に200が必要）
```

失敗時はログに記録してSlack/LINE通知（既存のLINE通知機構を流用）。

---

## スケジューラー変更

**main.py**の`_start_scheduler()`に追加:

```python
# eBay売上 → Shopify在庫クローズ（30分間隔）
scheduler.add_job(
    auto_sync_and_close_shopify,
    "interval",
    minutes=30,
    id="shopify_sold_sync",
    name="Shopify在庫クローズ",
)
```

`comms/scheduled_jobs.py`に`auto_sync_and_close_shopify`を実装:
1. `sync_sales(days=1)`で直近1日の売上をeBayから取得
2. `close_shopify_for_sold_items()`で対応するShopify在庫を0に

---

## 既存ツールへの変更

### update_listing ハンドラ（handlers.py）

eBay価格変更後、Shopify価格も自動更新:

```python
# update_listingの既存処理の後に追加
if price_usd and listing.shopify_product_id:
    discount_rate = get_config_value("discount_rate", default=0.05)
    shopify_price = get_shopify_price(price_usd, discount_rate)
    await client.update_product_price(listing.shopify_product_id, shopify_price)
```

---

## 新Claudeツール

| ツール名 | 説明 | 破壊的操作 |
|---|---|---|
| `sync_all_to_shopify` | 未同期eBay出品を一括Shopify同期 | No |
| `set_shopify_discount` | 割引率変更（例: 0.05 → 0.03） | No |
| `get_shopify_status` | 同期状況一覧（同期済み件数・未同期件数等） | No |
| `remove_from_shopify` | 特定SKUをShopifyから削除 | **Yes** |

---

## 環境変数（.envに追加）

```
SHOPIFY_SHOP_DOMAIN=xxxx.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxx
SHOPIFY_WEBHOOK_SECRET=xxxx
SHOPIFY_DISCOUNT_RATE=0.05
```

---

## Shopify側の手動設定タスク（コード外）

1. Shopify Basic プラン契約（$29/月）
2. Admin APIアクセストークン発行（スコープ: `write_products`, `read_orders`, `write_inventory`）
3. 国際送料プロファイルの設定
4. Shopify Payments または決済ゲートウェイの設定
5. Webhookの登録: `orders/create` → `https://ebay.trustlink-tk.com/shopify/webhook/order-created`

---

## リスクと対策

| リスク | 対策 |
|---|---|
| オーバーセル（eBay売れ→Shopify更新遅延） | 30分スケジューラー + Shopify webhookの二重カバー |
| eBay画像URL失効 | Shopify側に画像をアップロードしてホスト |
| Shopify APIレート制限 | 0.5秒スロットリング（2 req/秒以内） |
| Webhook受信失敗（サーバーダウン等） | LINEで失敗通知 + Shopifyの自動リトライ（最大19回）に委ねる |
