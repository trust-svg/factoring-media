"""サイトレジストリ — 巡回先サイトの設定を一元管理

仕入れ検索の3原則:
  1. 巡回先サイトを先に絞る → このファイルで有効/無効・優先度を管理
  2. 各サイトで読む情報を絞る → extract_fields で取得項目を明示
  3. 商品画像を判別する処理を入れる → supports_image フラグ
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── サイト定義 ──────────────────────────────────────────────
# enabled: False にすると巡回しない（コード変更不要で切替可能）
# priority: 小さいほど先に巡回（安定性・信頼度順）
# reliability: 検索精度の目安（0.0〜1.0）。スコアリング時に重み付けに使用
# max_results: サイトあたりの取得上限
# rate_limit_sec: リクエスト間隔（秒）
# scraper_type: "requests" or "playwright"
# supports_image: 画像URLを取得可能か
# extract_fields: このサイトから取得する項目（統一スキーマ準拠）

SITE_REGISTRY: dict[str, dict] = {
    "yahoo_auctions": {
        "enabled": True,
        "display_name": "ヤフオク",
        "priority": 1,
        "reliability": 0.85,
        "max_results": 20,
        "rate_limit_sec": 2.0,
        "scraper_type": "requests",
        "scraper_class": "scrapers.yahoo_auction.YahooAuctionScraper",
        "supports_image": True,
        "extract_fields": [
            "title", "price_jpy", "shipping_jpy", "condition",
            "image_url", "product_url", "seller_id",
        ],
        "notes": "最大手オークション。requests で安定動作。",
    },
    "offmall": {
        "enabled": True,
        "display_name": "オフモール（ブックオフ）",
        "priority": 2,
        "reliability": 0.80,
        "max_results": 15,
        "rate_limit_sec": 2.0,
        "scraper_type": "requests",
        "scraper_class": "scrapers.offmall.OffmallScraper",
        "supports_image": True,
        "extract_fields": [
            "title", "price_jpy", "condition",
            "image_url", "product_url",
        ],
        "notes": "ブックオフ公式EC。コンディション表記が統一的。",
    },
    "surugaya": {
        "enabled": True,
        "display_name": "駿河屋",
        "priority": 3,
        "reliability": 0.75,
        "max_results": 15,
        "rate_limit_sec": 2.0,
        "scraper_type": "requests",
        "scraper_class": "scrapers.surugaya.SurugayaScraper",
        "supports_image": True,
        "extract_fields": [
            "title", "price_jpy", "condition",
            "image_url", "product_url",
        ],
        "notes": "ホビー・ゲーム・AV機器に強い。",
    },
    "mercari": {
        "enabled": True,
        "display_name": "メルカリ",
        "priority": 4,
        "reliability": 0.70,
        "max_results": 15,
        "rate_limit_sec": 3.0,
        "scraper_type": "playwright",
        "scraper_class": "scrapers.mercari.MercariScraper",
        "supports_image": True,
        "extract_fields": [
            "title", "price_jpy", "condition",
            "image_url", "product_url",
        ],
        "notes": "Playwright 必須。Cookie 永続化あり。個人出品のため品質ばらつき大。",
    },
    "paypay_flea": {
        "enabled": True,
        "display_name": "Yahoo!フリマ（PayPayフリマ）",
        "priority": 5,
        "reliability": 0.65,
        "max_results": 10,
        "rate_limit_sec": 3.0,
        "scraper_type": "playwright",
        "scraper_class": "scrapers.paypay_flea.PayPayFleaScraper",
        "supports_image": True,
        "extract_fields": [
            "title", "price_jpy", "condition",
            "image_url", "product_url",
        ],
        "notes": "Playwright 必須。メルカリと重複商品あり。",
    },
    "rakuma": {
        "enabled": False,
        "display_name": "ラクマ",
        "priority": 6,
        "reliability": 0.60,
        "max_results": 10,
        "rate_limit_sec": 3.0,
        "scraper_type": "playwright",
        "scraper_class": "scrapers.rakuma.RakumaScraper",
        "supports_image": True,
        "extract_fields": [
            "title", "price_jpy", "condition",
            "image_url", "product_url",
        ],
        "notes": "出品数少なめ。デフォルト無効（必要時にダッシュボードからON）。",
    },
}


def get_enabled_sites() -> list[dict]:
    """有効なサイトを優先度順で返す"""
    sites = []
    for site_id, config in SITE_REGISTRY.items():
        if config["enabled"]:
            sites.append({"id": site_id, **config})
    sites.sort(key=lambda s: s["priority"])
    return sites


def get_site(site_id: str) -> dict | None:
    """サイトIDから設定を取得"""
    config = SITE_REGISTRY.get(site_id)
    if config:
        return {"id": site_id, **config}
    return None


def set_site_enabled(site_id: str, enabled: bool) -> bool:
    """サイトの有効/無効を切り替える"""
    if site_id not in SITE_REGISTRY:
        return False
    SITE_REGISTRY[site_id]["enabled"] = enabled
    logger.info(f"サイト '{site_id}' を {'有効' if enabled else '無効'} に変更")
    return True


def get_registry_summary() -> dict:
    """レジストリの要約を返す（ダッシュボード用）"""
    enabled = get_enabled_sites()
    return {
        "total_sites": len(SITE_REGISTRY),
        "enabled_sites": len(enabled),
        "enabled_list": [
            {
                "id": s["id"],
                "name": s["display_name"],
                "priority": s["priority"],
                "reliability": s["reliability"],
                "scraper_type": s["scraper_type"],
            }
            for s in enabled
        ],
        "disabled_list": [
            {"id": sid, "name": cfg["display_name"]}
            for sid, cfg in SITE_REGISTRY.items()
            if not cfg["enabled"]
        ],
    }
