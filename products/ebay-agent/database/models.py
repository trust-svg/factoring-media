"""統合データベースモデル

ebay-listing-optimizer の既存モデルを拡張し、
仕入れ候補・価格履歴・売上記録を追加。
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    pass


# ── 出品管理 ──────────────────────────────────────────────

class Listing(Base):
    """eBay出品データ"""
    __tablename__ = "listings"

    sku: Mapped[str] = mapped_column(String(128), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    category_id: Mapped[str] = mapped_column(String(32), default="")
    category_name: Mapped[str] = mapped_column(String(128), default="")
    condition: Mapped[str] = mapped_column(String(64), default="")
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    item_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    offer_id: Mapped[str] = mapped_column(String(64), default="")
    seo_score: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_type: Mapped[str] = mapped_column(String(16), default="stocked", index=True)
    # source_type: stocked / dropship_jp / dropship_ebay_reverse
    shopify_product_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    shopify_variant_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    shopify_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── SEO最適化 ─────────────────────────────────────────────

class Optimization(Base):
    """AI最適化提案"""
    __tablename__ = "optimizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    original_title: Mapped[str] = mapped_column(String(80), default="")
    suggested_title: Mapped[str] = mapped_column(String(80), default="")
    original_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── 仕入れ候補 ────────────────────────────────────────────

class SourceCandidate(Base):
    """日本マーケットプレイスの仕入れ候補"""
    __tablename__ = "source_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")
    search_keyword: Mapped[str] = mapped_column(String(256), default="")
    platform: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    condition: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    is_junk: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="found")
    # status: found -> purchased -> shipped -> received
    found_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 仕入れ実績 ────────────────────────────────────────────

class Procurement(Base):
    """仕入れ実績 — SourceCandidate → 購入 → 受取 → Listing紐付け"""
    __tablename__ = "procurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")
    source_candidate_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    platform: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    purchase_price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    other_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    purchase_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="purchased")
    # status: purchased -> shipped -> received -> listed
    consumption_tax_jpy: Mapped[int] = mapped_column(Integer, default=0)  # 消費税額（輸出免税還付用）
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 価格履歴 ──────────────────────────────────────────────

class PriceHistory(Base):
    """競合価格トラッキング"""
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    our_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    avg_competitor_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    lowest_competitor_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    num_competitors: Mapped[int] = mapped_column(Integer, default=0)
    exchange_rate: Mapped[float] = mapped_column(Float, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 売上記録 ──────────────────────────────────────────────

class SalesRecord(Base):
    """売上・利益追跡（全コスト詳細）"""
    __tablename__ = "sales_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    item_id: Mapped[str] = mapped_column(String(64), default="")              # eBay Item ID
    sku: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    buyer_name: Mapped[str] = mapped_column(String(128), default="")          # バイヤー名
    buyer_country: Mapped[str] = mapped_column(String(64), default="")        # 送付先国

    # 売上
    sale_price_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # 仕入原価（国内）
    source_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    consumption_tax_jpy: Mapped[int] = mapped_column(Integer, default=0)  # 消費税額（還付計算用）
    shipping_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)     # 国内送料

    # 国際発送
    intl_shipping_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    shipping_method: Mapped[str] = mapped_column(String(32), default="")   # EMS/ePacket/FedEx等

    # eBay手数料（合算）
    ebay_fees_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Payoneer
    payoneer_fee_usd: Mapped[float] = mapped_column(Float, default=0.0)   # 売上 × 2%
    payoneer_rate: Mapped[float] = mapped_column(Float, default=0.0)       # Payoneer実効レート
    received_jpy: Mapped[int] = mapped_column(Integer, default=0)          # 実際の円着金額

    # 関税
    customs_duty_jpy: Mapped[int] = mapped_column(Integer, default=0)      # 関税
    # その他経費
    other_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)        # 梱包材等
    cost_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 経費メモ

    # 追跡番号（CPaaS送料突き合わせ用）
    tracking_number: Mapped[str] = mapped_column(String(64), default="", index=True)

    # 為替
    exchange_rate: Mapped[float] = mapped_column(Float, default=0.0)       # 売上日TTMレート

    # 利益（自動計算）
    total_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)        # 全JPYコスト合算
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)      # 全コストUSD換算
    net_profit_usd: Mapped[float] = mapped_column(Float, default=0.0)      # 最終純利益(USD)
    net_profit_jpy: Mapped[int] = mapped_column(Integer, default=0)        # 最終純利益(JPY)
    profit_margin_pct: Mapped[float] = mapped_column(Float, default=0.0)   # 利益率

    # 進捗ステータス（eShip準拠: 未注文/注文済/発送済/納品済/キャンセル/返金）
    progress: Mapped[str] = mapped_column(String(16), default="")
    # eBayマーケットプレイス（US/UK/DE/FR/CA/AU等）
    marketplace: Mapped[str] = mapped_column(String(8), default="")      # 購入元サイト
    listing_site: Mapped[str] = mapped_column(String(8), default="")     # 出品先サイト
    ship_by_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 発送期限

    # 旧互換
    profit_usd: Mapped[float] = mapped_column(Float, default=0.0)

    sold_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 月間固定費 ────────────────────────────────────────────

class MonthlyExpense(Base):
    """月間固定費（ストア購読・ツール・梱包材等）"""
    __tablename__ = "monthly_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year_month: Mapped[str] = mapped_column(String(7), index=True)  # 2026-03
    category: Mapped[str] = mapped_column(String(32), default="other")
    # category: store_subscription / tools / packaging / storage / insurance / other
    description: Mapped[str] = mapped_column(String(256), default="")
    amount_jpy: Mapped[int] = mapped_column(Integer, default=0)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    is_recurring: Mapped[int] = mapped_column(Integer, default=0)  # 1=毎月自動発生
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── リサーチ結果 ──────────────────────────────────────────

class ResearchResult(Base):
    """需要分析・商品リサーチ結果"""
    __tablename__ = "research_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(256), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    avg_sold_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sell_through_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_source_price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    estimated_margin_usd: Mapped[float] = mapped_column(Float, default=0.0)
    num_sold_last_30d: Mapped[int] = mapped_column(Integer, default=0)
    num_active_listings: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    researched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 変更履歴 ──────────────────────────────────────────────

class ChangeHistory(Base):
    """出品変更ログ"""
    __tablename__ = "change_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    field_changed: Mapped[str] = mapped_column(String(32), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    success: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ── Instagram投稿 ────────────────────────────────────────

class InstagramPost(Base):
    """Instagram投稿管理"""
    __tablename__ = "instagram_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]")
    content_type: Mapped[str] = mapped_column(String(32), default="single")
    # content_type: single / carousel / reel_script / story
    tone: Mapped[str] = mapped_column(String(32), default="showcase")
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    slide_suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    cta: Mapped[str] = mapped_column(String(256), default="")
    ig_post_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # status: draft -> scheduled -> published -> archived
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    link_clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 仕入れ台帳（在庫管理統合） ────────────────────────────

class InventoryItem(Base):
    """仕入れ台帳 — 全仕入れ商品を一元管理（有在庫・無在庫問わず）

    ステータスフロー:
      注文済み → 入荷済み → 出品中 → 販売済み → 発送済み
                                    → キャンセル
                          → 返品
    """
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_number: Mapped[str] = mapped_column(String(32), index=True, default="")  # 在庫管理番号（例: A-001）
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")          # eBay SKU（出品後に紐付け）
    title: Mapped[str] = mapped_column(String(512), default="")
    purchase_price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    consumption_tax_jpy: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)             # 国内送料
    purchase_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    purchase_source: Mapped[str] = mapped_column(String(64), default="")            # メルカリ/ヤフオク等
    purchase_url: Mapped[str] = mapped_column(Text, default="")
    seller_id: Mapped[str] = mapped_column(String(128), default="")                # 出品者ID/名前
    seller_url: Mapped[str] = mapped_column(Text, default="")                      # 出品者ページURL
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    location: Mapped[str] = mapped_column(String(128), default="")                  # 保管場所
    condition: Mapped[str] = mapped_column(String(32), default="")                  # 新品/中古A/中古B/ジャンク
    # ステータス: ordered/received/listed/sold/shipped/returned/cancelled
    status: Mapped[str] = mapped_column(String(16), default="ordered")
    ebay_item_id: Mapped[str] = mapped_column(String(64), default="")
    ebay_order_id: Mapped[str] = mapped_column(String(64), default="", index=True)   # eBay Order Number
    ebay_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    listed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sale_record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # sales_records.id
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[str] = mapped_column(Text, default="")
    screenshot_path: Mapped[str] = mapped_column(Text, default="")                  # 仕入元スクリーンショット保存パス
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Shopify連携 ───────────────────────────────────────────

class ShopifyConfig(Base):
    """Shopify設定（discount_rate等をDB管理）"""
    __tablename__ = "shopify_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── バイヤーメッセージ ────────────────────────────────

class BuyerMessage(Base):
    """eBayバイヤーメッセージ（ローカルキャッシュ）"""
    __tablename__ = "buyer_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ebay_message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    external_message_id: Mapped[str] = mapped_column(String(128), default="")
    item_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    order_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    sender: Mapped[str] = mapped_column(String(128), default="", index=True)
    recipient: Mapped[str] = mapped_column(String(128), default="")
    direction: Mapped[str] = mapped_column(String(8), default="inbound")  # inbound / outbound
    subject: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    body_translated: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_read: Mapped[int] = mapped_column(Integer, default=0)
    responded: Mapped[int] = mapped_column(Integer, default=0)
    has_attachment: Mapped[int] = mapped_column(Integer, default=0)
    attachment_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    draft_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_tone: Mapped[str] = mapped_column(String(32), default="")
    draft_category: Mapped[str] = mapped_column(String(32), default="")
    # センチメント分析 + 緊急度
    sentiment: Mapped[str] = mapped_column(String(16), default="")  # positive / neutral / negative / angry
    urgency: Mapped[str] = mapped_column(String(16), default="")    # low / medium / high / critical
    sentiment_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 分析理由
    # 返信時間トラッキング
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    response_time_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 返信所要時間（分）
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── メッセージテンプレート ────────────────────────────

class MessageTemplate(Base):
    """返信テンプレート"""
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    body_en: Mapped[str] = mapped_column(Text, default="")
    body_ja: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="custom")
    # category: greeting / shipping / return / thanks / offer / negotiation / custom
    variables_json: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── 自動メッセージルール ──────────────────────────────

class AutoMessageRule(Base):
    """自動メッセージ送信ルール"""
    __tablename__ = "auto_message_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    # event_type: feedback_received / fixed_price_transaction / item_shipped /
    #   item_delivered / best_offer_declined / best_offer_received /
    #   after_delivery_n_days / outside_business_hours
    name: Mapped[str] = mapped_column(String(256), default="")
    template_id: Mapped[int] = mapped_column(Integer, default=0)  # FK to message_templates
    repeat_buyer_template_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(16), default="manual")  # manual | auto
    send_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── 未返信候補スキップ記録 ─────────────────────────────

class NoReplyCandidateSkip(Base):
    """未返信自動返信の候補スキップ/対応済み記録"""
    __tablename__ = "no_reply_candidate_skips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_message_id: Mapped[int] = mapped_column(Integer, index=True)
    buyer_username: Mapped[str] = mapped_column(String(128), default="")
    item_id: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(16), default="skip")  # skip | sent | excluded
    skipped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── バイヤー除外リスト ────────────────────────────────

class BuyerExclude(Base):
    """自動メッセージ除外バイヤー"""
    __tablename__ = "buyer_excludes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 自動メッセージログ ────────────────────────────────

class AutoMessageLog(Base):
    """自動メッセージ送信ログ"""
    __tablename__ = "auto_message_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(32), default="")
    buyer_username: Mapped[str] = mapped_column(String(128), default="")
    item_id: Mapped[str] = mapped_column(String(64), default="")
    order_id: Mapped[str] = mapped_column(String(64), default="")
    message_body: Mapped[str] = mapped_column(Text, default="")
    is_repeat_buyer: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 分析レポート ──────────────────────────────────────

class AnalyticsReport(Base):
    """週次・月次分析レポート"""
    __tablename__ = "analytics_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(16), index=True)  # weekly / monthly
    period_start: Mapped[datetime] = mapped_column(DateTime)
    period_end: Mapped[datetime] = mapped_column(DateTime)
    period_label: Mapped[str] = mapped_column(String(32), default="")  # "2026-W12" or "2026-03"

    # KPI サマリー (JSON)
    kpi_json: Mapped[str] = mapped_column(Text, default="{}")
    # トップ商品 (JSON)
    top_products_json: Mapped[str] = mapped_column(Text, default="[]")
    # ワースト商品 (JSON)
    worst_products_json: Mapped[str] = mapped_column(Text, default="[]")
    # 在庫分析 (JSON)
    inventory_json: Mapped[str] = mapped_column(Text, default="{}")
    # 仕入れ分析 (JSON)
    procurement_json: Mapped[str] = mapped_column(Text, default="{}")
    # カテゴリ別 (JSON)
    category_json: Mapped[str] = mapped_column(Text, default="[]")
    # バイヤー国別 (JSON)
    buyer_country_json: Mapped[str] = mapped_column(Text, default="[]")
    # 価格競争力 (JSON)
    price_competitiveness_json: Mapped[str] = mapped_column(Text, default="{}")
    # 前期比較 (JSON)
    comparison_json: Mapped[str] = mapped_column(Text, default="{}")
    # AI改善提案 (JSON)
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    # ツール開発提案 (JSON)
    tool_suggestions_json: Mapped[str] = mapped_column(Text, default="[]")

    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 死に筒リフレッシュ（S2施策） ─────────────────────────

class ListingRefreshBackup(Base):
    """死に筒Revise前のバックアップ（ロールバック用）"""
    __tablename__ = "listing_refresh_backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    listing_id: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(16), default="revise")  # revise / es2s
    old_title: Mapped[str] = mapped_column(String(200), default="")
    new_title: Mapped[str] = mapped_column(String(200), default="")
    old_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    new_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    old_item_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    new_item_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    # 品質ガードの通過内訳
    quality_checks_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # status: pending / dry_run / applied / rolled_back / failed / skipped
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ListingRefreshRun(Base):
    """日次リフレッシュ実行ログ（配信パターン可視化）"""
    __tablename__ = "listing_refresh_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheduled_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    hour_jst: Mapped[int] = mapped_column(Integer, default=0)
    sku: Mapped[str] = mapped_column(String(128), default="")
    backup_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="")
    # outcome: applied / skipped_quality / skipped_quota / dry_run / error
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 無在庫出品パイプライン（高額商品拡張） ─────────────────

class HotExpensiveItem(Base):
    """eBayで売れている高額商品（Sold由来の候補リスト）"""
    __tablename__ = "hot_expensive_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    category: Mapped[str] = mapped_column(String(128), default="", index=True)
    category_id: Mapped[str] = mapped_column(String(32), default="")
    query: Mapped[str] = mapped_column(String(256), default="")  # 元検索キーワード
    median_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    min_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    max_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sold_qty_30d: Mapped[int] = mapped_column(Integer, default=0)
    active_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_listing_id: Mapped[str] = mapped_column(String(64), default="")
    sample_url: Mapped[Text] = mapped_column(Text, default="")
    image_url: Mapped[Text] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    # status: new / matched / ignored / duplicate
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DropshipCandidate(Base):
    """国内逆検索マッチ結果（eBay売れ筋×国内仕入れ先）"""
    __tablename__ = "dropship_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hot_item_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)  # HotExpensiveItem.id
    source_type: Mapped[str] = mapped_column(String(24), default="dropship_ebay_reverse")
    # source_type: dropship_ebay_reverse (eBay→JP) / dropship_jp (JP→eBay)
    jp_platform: Mapped[str] = mapped_column(String(32), default="")  # yahoo_auction / mercari / paypay_flea / rakuma / surugaya / offmall
    jp_url: Mapped[Text] = mapped_column(Text, default="")
    jp_title: Mapped[str] = mapped_column(String(512), default="")
    jp_price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    jp_condition: Mapped[str] = mapped_column(String(64), default="")
    jp_image_url: Mapped[Text] = mapped_column(Text, default="")
    ebay_target_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    projected_profit_usd: Mapped[float] = mapped_column(Float, default=0.0)
    projected_margin_pct: Mapped[float] = mapped_column(Float, default=0.0)
    exchange_rate: Mapped[float] = mapped_column(Float, default=0.0)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)  # タイトル類似度等
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # status: pending / approved / listed / sold / rejected / expired
    telegram_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    listed_sku: Mapped[str] = mapped_column(String(128), default="", index=True)
    listed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ── DB初期化 ──────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """DELETEジャーナルモード: コンテナ再作成時のWAL未永続化による
    データロストを防ぐため、WALではなくDELETEモードを使用。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=DELETE")
    cursor.execute("PRAGMA synchronous=FULL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine)


def _migrate_shopify_columns(engine_instance) -> None:
    """既存のlistingsテーブルにカラムを追加（冪等）"""
    from sqlalchemy import text
    with engine_instance.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(listings)"))
        existing = {row[1] for row in result.fetchall()}
        stmts = []
        if "shopify_product_id" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN shopify_product_id TEXT")
        if "shopify_variant_id" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN shopify_variant_id TEXT")
        if "shopify_synced_at" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN shopify_synced_at DATETIME")
        if "source_type" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'stocked'")
        for stmt in stmts:
            conn.execute(text(stmt))
        if "source_type" in existing or any("source_type" in s for s in stmts):
            # インデックスは冪等なのでCREATE INDEX IF NOT EXISTS
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_listings_source_type ON listings(source_type)"))
        if stmts:
            conn.commit()


def init_db():
    """テーブル作成"""
    Base.metadata.create_all(engine)
    _migrate_shopify_columns(engine)


def get_db() -> Session:
    """DBセッションを取得"""
    return SessionLocal()
