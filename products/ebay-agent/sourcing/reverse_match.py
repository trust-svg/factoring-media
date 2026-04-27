"""国内逆検索マッチング

hot_expensive_items（eBayで売れている高額商品）の各行に対して
国内サイト（ヤフオク・メルカリ・ヤフーフリマ・ラクマ・駿河屋・オフモール）を
横断検索し、目標マージンを満たす無在庫出品候補を dropship_candidates に登録する。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import EBAY_FEE_RATE
from database.models import DropshipCandidate, HotExpensiveItem, get_db
from ebay_core.exchange_rate import get_usd_to_jpy, jpy_to_usd
from tools.handlers import _search_sources


logger = logging.getLogger(__name__)


# 無在庫特有コスト想定（国内送料+梱包+国際送料USD基準）
DEFAULT_DOMESTIC_SHIPPING_JPY = 1500  # 国内送料（仕入れ→倉庫）
DEFAULT_INTL_SHIPPING_USD = 40.0      # 国際発送（FedEx/DHL想定）
DEFAULT_PACKAGING_JPY = 1500          # 梱包材・作業費
DEFAULT_PAYONEER_RATE = 0.02           # Payoneer決済手数料
DEFAULT_TARGET_MARGIN = 0.25           # 25%以上で候補化

# ── 品質ガード ──────────────────────────────────────
# 売値の何%以下を「別商品の可能性」として除外するか
MIN_PRICE_RATIO = 0.15                # 例: $1763売値 → ¥42k未満は別物扱い
# 候補スコアの下限（scorerの100点満点）
MIN_MATCH_SCORE = 45.0                # 実運用で 45-52pt の本物が落ちていたため緩和（画像比較OFF時の暫定値）

# カテゴリ別 NGキーワード（タイトルに含まれたら除外）
# 本/CD/DVD/写真集など「本体ではない周辺メディア」を弾く
CATEGORY_NG_KEYWORDS: dict[str, list[str]] = {
    "Vintage Watch": [
        "cd", "lp", "dvd", "blu-ray", "ブルーレイ", "bd", "sacd",
        "本", "文庫", "書籍", "雑誌", "写真集",
        "カレンダー", "ポスター", "ステッカー", "シール",
    ],
    "Vintage Audio": [
        "cd", "lp", "dvd", "blu-ray", "ブルーレイ", "bd", "sacd",
        "文庫", "書籍", "雑誌", "写真集", "楽譜",
    ],
    "Vintage Camera": [
        "cd", "lp", "dvd", "文庫", "書籍", "雑誌", "写真集",
    ],
    "Synthesizer": [
        "cd", "lp", "dvd", "楽譜", "文庫", "書籍", "雑誌",
    ],
    "Samurai Armor": [
        "cd", "lp", "dvd", "文庫", "書籍", "雑誌",
        "プラモ", "フィギュア", "ポスター", "ミニチュア", "置物",
    ],
    "Japanese Sword": [
        "cd", "lp", "dvd", "文庫", "書籍", "プラモ", "フィギュア",
        "レプリカ", "模造", "玩具",
    ],
}

# カテゴリ別 推奨巡回サイト（不要site を絞って誤検知を減らす）
# 空/未定義カテゴリは全有効サイトを巡回（後方互換）
CATEGORY_SITE_FILTER: dict[str, list[str]] = {
    "Vintage Watch":  ["yahoo_auctions", "mercari", "paypay_flea", "rakuma"],
    "Vintage Audio":  ["yahoo_auctions", "mercari", "paypay_flea", "rakuma"],
    "Vintage Camera": ["yahoo_auctions", "mercari", "paypay_flea", "rakuma"],
    "Synthesizer":    ["yahoo_auctions", "mercari", "paypay_flea", "rakuma"],
    "Samurai Armor":  ["yahoo_auctions", "mercari", "paypay_flea", "rakuma"],
    "Japanese Sword": ["yahoo_auctions", "mercari"],
}


def _title_has_ng_keyword(title: str, category: str) -> bool:
    """タイトルにカテゴリNGキーワードが含まれているか判定。"""
    ng = CATEGORY_NG_KEYWORDS.get(category, [])
    if not ng:
        return False
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in ng)


def max_source_jpy_for_margin(
    sale_usd: float,
    target_margin: float = DEFAULT_TARGET_MARGIN,
    intl_shipping_usd: float = DEFAULT_INTL_SHIPPING_USD,
    domestic_shipping_jpy: int = DEFAULT_DOMESTIC_SHIPPING_JPY,
    packaging_jpy: int = DEFAULT_PACKAGING_JPY,
    payoneer_rate: float = DEFAULT_PAYONEER_RATE,
) -> int:
    """目標マージンを満たすために許容できる国内仕入価格の上限 (JPY)。"""
    rate = get_usd_to_jpy()
    ebay_fees = sale_usd * EBAY_FEE_RATE
    payoneer_fee = sale_usd * payoneer_rate
    net_rev_usd = sale_usd - ebay_fees - payoneer_fee - intl_shipping_usd
    allowed_cost_usd = net_rev_usd - (sale_usd * target_margin)
    if allowed_cost_usd <= 0:
        return 0
    allowed_cost_jpy = int(allowed_cost_usd * rate) - domestic_shipping_jpy - packaging_jpy
    return max(allowed_cost_jpy, 0)


def compute_projected_margin(
    source_jpy: int,
    sale_usd: float,
    intl_shipping_usd: float = DEFAULT_INTL_SHIPPING_USD,
    domestic_shipping_jpy: int = DEFAULT_DOMESTIC_SHIPPING_JPY,
    packaging_jpy: int = DEFAULT_PACKAGING_JPY,
    payoneer_rate: float = DEFAULT_PAYONEER_RATE,
) -> dict:
    """仕入JPY + 販売USD から想定利益・マージンを計算。"""
    rate = get_usd_to_jpy()
    total_cost_jpy = source_jpy + domestic_shipping_jpy + packaging_jpy
    total_cost_usd = jpy_to_usd(total_cost_jpy)
    ebay_fees_usd = sale_usd * EBAY_FEE_RATE
    payoneer_fee_usd = sale_usd * payoneer_rate
    profit_usd = (
        sale_usd
        - ebay_fees_usd
        - payoneer_fee_usd
        - intl_shipping_usd
        - total_cost_usd
    )
    margin_pct = (profit_usd / sale_usd * 100) if sale_usd > 0 else 0.0
    return {
        "exchange_rate": rate,
        "profit_usd": round(profit_usd, 2),
        "margin_pct": round(margin_pct, 1),
        "total_cost_usd": round(total_cost_usd, 2),
    }


async def match_single(
    hot: HotExpensiveItem,
    target_margin: float = DEFAULT_TARGET_MARGIN,
    top_n_per_item: int = 3,
    min_match_score: float = MIN_MATCH_SCORE,
    min_price_ratio: float = MIN_PRICE_RATIO,
) -> list[dict]:
    """HotExpensiveItem 1件に対する国内マッチ。候補 dict のリストを返す。

    品質ガード:
      1. 価格下限: 売値の min_price_ratio 未満は別商品として除外
      2. カテゴリNG: CD/本/フィギュア等の誤検知カテゴリを除外
      3. スコア下限: min_match_score 未満は信頼性低として除外
      4. サイト絞り込み: CATEGORY_SITE_FILTER でカテゴリ別に巡回先を限定
    """
    if hot.median_price_usd <= 0:
        return []

    max_jpy = max_source_jpy_for_margin(hot.median_price_usd, target_margin=target_margin)
    if max_jpy <= 0:
        logger.warning(
            "[reverse_match] max_jpy=0 for query=%r median=$%.0f — skip",
            hot.query, hot.median_price_usd,
        )
        return []

    # 画像URLが無いと精度が大きく下がるので警告
    if not hot.image_url:
        logger.warning(
            "[reverse_match] image_url 未設定 for query=%r — 画像比較スキップ",
            hot.query,
        )

    # カテゴリ別サイト絞り込み
    sites_filter = CATEGORY_SITE_FILTER.get(hot.category or "", [])

    search_params = {
        "keyword": hot.query,
        "max_price_jpy": max_jpy,
        "junk_ok": False,
        "ebay_image_url": hot.image_url or "",
        "top_n": top_n_per_item,
    }
    if sites_filter:
        search_params["sites"] = sites_filter

    try:
        result = await _search_sources(search_params)
    except Exception as e:
        logger.error("[reverse_match] search_sources failed: %s (query=%r)", e, hot.query)
        return []

    # 価格下限（売値の X% 未満は別商品の可能性）
    rate = get_usd_to_jpy()
    min_jpy = int(hot.median_price_usd * rate * min_price_ratio)

    candidates = result.get("best_candidates", [])
    matches: list[dict] = []
    rejected_reasons: dict[str, int] = {}

    for cand in candidates:
        price_jpy = int(cand.get("price_jpy", 0))
        title = cand.get("title", "")
        score = float(cand.get("score", 0))

        # ガード1: 価格範囲外
        if price_jpy <= 0 or price_jpy > max_jpy:
            rejected_reasons["price_out_of_range"] = rejected_reasons.get("price_out_of_range", 0) + 1
            continue

        # ガード2: 価格下限（売値の X% 未満）
        if price_jpy < min_jpy:
            rejected_reasons["price_too_low"] = rejected_reasons.get("price_too_low", 0) + 1
            logger.info(
                "  [reject] 価格下限 ¥%d < ¥%d (売値%.0f%%): %s",
                price_jpy, min_jpy, min_price_ratio * 100, title[:60],
            )
            continue

        # ガード3: カテゴリNGキーワード
        if _title_has_ng_keyword(title, hot.category or ""):
            rejected_reasons["ng_keyword"] = rejected_reasons.get("ng_keyword", 0) + 1
            logger.info("  [reject] NGキーワード [%s]: %s", hot.category, title[:60])
            continue

        # ガード4: スコア下限
        if score < min_match_score:
            rejected_reasons["low_score"] = rejected_reasons.get("low_score", 0) + 1
            logger.info("  [reject] スコア %.1f < %.1f: %s", score, min_match_score, title[:60])
            continue

        calc = compute_projected_margin(price_jpy, hot.median_price_usd)
        if calc["margin_pct"] / 100 < target_margin:
            rejected_reasons["low_margin"] = rejected_reasons.get("low_margin", 0) + 1
            continue

        matches.append({
            "hot_item_id": hot.id,
            "jp_platform": cand.get("platform", ""),
            "jp_url": cand.get("url", ""),
            "jp_title": title[:500],
            "jp_price_jpy": price_jpy,
            "jp_condition": cand.get("condition", ""),
            "jp_image_url": cand.get("image_url", ""),
            "ebay_target_price_usd": hot.median_price_usd,
            "projected_profit_usd": calc["profit_usd"],
            "projected_margin_pct": calc["margin_pct"],
            "exchange_rate": calc["exchange_rate"],
            "match_score": score,
        })

    if rejected_reasons:
        logger.info(
            "[reverse_match] query=%r: 採用 %d / 却下 %s",
            hot.query, len(matches), rejected_reasons,
        )

    return matches


async def find_jp_candidates(
    db: Session,
    hot_items: Optional[list[HotExpensiveItem]] = None,
    target_margin: float = DEFAULT_TARGET_MARGIN,
    top_n_per_item: int = 3,
    dedupe_hours: int = 24,
) -> list[DropshipCandidate]:
    """未処理の hot_expensive_items を国内で逆検索して候補を登録。

    dedupe_hours 以内に同じ jp_url で候補登録済みなら重複スキップ。
    """
    if hot_items is None:
        cutoff = datetime.utcnow() - timedelta(days=14)
        hot_items = list(db.execute(
            select(HotExpensiveItem)
            .where(
                HotExpensiveItem.status == "new",
                HotExpensiveItem.discovered_at >= cutoff,
            )
            .order_by(HotExpensiveItem.discovered_at.desc())
        ).scalars().all())

    dedupe_cutoff = datetime.utcnow() - timedelta(hours=dedupe_hours)
    saved: list[DropshipCandidate] = []

    for hot in hot_items:
        matches = await match_single(hot, target_margin=target_margin, top_n_per_item=top_n_per_item)
        for m in matches:
            existing = db.execute(
                select(DropshipCandidate).where(
                    DropshipCandidate.jp_url == m["jp_url"],
                    DropshipCandidate.created_at >= dedupe_cutoff,
                )
            ).scalars().first()
            if existing:
                continue
            cand = DropshipCandidate(**m)
            db.add(cand)
            saved.append(cand)

        if matches:
            hot.status = "matched"

    db.commit()
    return saved


def list_pending(db: Session, limit: int = 20) -> list[DropshipCandidate]:
    """pending ステータスの候補を想定利益順に返す。"""
    return list(db.execute(
        select(DropshipCandidate)
        .where(DropshipCandidate.status == "pending")
        .order_by(
            DropshipCandidate.projected_profit_usd.desc(),
            DropshipCandidate.created_at.desc(),
        )
        .limit(limit)
    ).scalars().all())


if __name__ == "__main__":
    async def _main():
        db = get_db()
        results = await find_jp_candidates(db)
        print(f"マッチング完了: {len(results)}候補")
        for r in results[:10]:
            print(
                f"  [{r.jp_platform}] ¥{r.jp_price_jpy:,} → "
                f"${r.ebay_target_price_usd:.0f} "
                f"(利益 ${r.projected_profit_usd:.0f} / {r.projected_margin_pct:.1f}%)"
            )
            print(f"     {r.jp_title[:80]}")
    asyncio.run(_main())
