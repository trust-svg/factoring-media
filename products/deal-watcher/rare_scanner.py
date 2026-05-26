"""Rare item scanner — one-of-a-kind collectibles on Yahoo Auctions / Mercari.

Daily operation: scan_rare_items() runs every 30 min via APScheduler.
Market research:  ebay_market_research() runs weekly (Sunday 9:00 JST) or on-demand.
                  Queries eBay for high-value signed/promo/original items and sends
                  a Telegram report to guide what to look for on Yahoo Auctions.
"""

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Optional

import config
import database as db
from notifier import _send_telegram, PLATFORM_LABELS

logger = logging.getLogger(__name__)

# ── Search config ──────────────────────────────────────────

# One-of-a-kind indicator keywords (at least one must appear in the title)
RARE_KEYWORDS = [
    "直筆",
    "サイン",
    "非売品",
    "プロモ",
    "複製原画",
    "セル画",
    "作家物",
    "一点物",
    "手書き",
    "贈呈品",
    "展示品",
    "抽選",
    "見本品",
    "試作品",
    "限定生産",
    "受注生産",
]

# Disqualifiers
RARE_EXCLUDE_KEYWORDS = [
    "ジャンク",
    "難あり",
    "動作未確認",
    "破損",
    "汚れ",
    "欠品",
    "シミ",
    "傷あり",
    "訳あり",
    "不動",
    "補修",
    "修繕",
]

# 4 genuinely one-of-a-kind categories
GENRE_CONFIG: dict = {
    "signed_items": {
        "label": "サイン品",
        "search_queries": [
            "直筆サイン アーティスト",
            "サイン入り 直筆 作家",
            "直筆 漫画家 サイン",
            "手書きサイン 芸能人",
            "直筆サイン ドラゴンボール",
            "直筆サイン ワンピース",
            "直筆サイン 鬼滅の刃",
            "直筆サイン 進撃の巨人",
            "直筆サイン ナルト",
            "直筆サイン セーラームーン",
            "直筆サイン エヴァンゲリオン",
            "直筆サイン ジブリ",
        ],
        "min_price": 10_000,
        "max_price": 2_000_000,
    },
    "original_art": {
        "label": "原画・セル画",
        "search_queries": [
            "セル画 アニメ",
            "原画 直筆 イラスト",
            "複製原画 限定",
            "直筆 イラスト 作家",
            "漫画家 肉筆 原稿",
            "動画 背景 セル",
            "ドラゴンボール セル画",
            "ワンピース 原画",
            "セーラームーン セル画",
            "ガンダム セル画",
            "エヴァンゲリオン 原画",
            "ジブリ 複製原画",
        ],
        "min_price": 10_000,
        "max_price": 5_000_000,
    },
    "promo_items": {
        "label": "非売品・プロモ",
        "search_queries": [
            "非売品 限定品",
            "プロモ 非売品",
            "見本品 非売品",
            "展示品 非売品",
            "贈呈品 記念品",
            "抽選 当選品 非売品",
        ],
        "min_price": 5_000,
        "max_price": 1_000_000,
    },
    "traditional_craft": {
        "label": "伝統工芸・作家物",
        "search_queries": [
            "陶芸 作家物 サイン",
            "作家 陶器 一点物",
            "漆器 作家物",
            "蒔絵 作家",
            "陶磁器 作家 証明書",
            "作家 木彫 一点物",
        ],
        "min_price": 10_000,
        "max_price": 5_000_000,
    },
}

# ── eBay market research config ────────────────────────────

# (eBay query, category_id or None)
EBAY_RESEARCH_QUERIES = [
    ("signed autographed japan", None),
    ("hand signed japan artist", None),
    ("original animation cel japan anime", "550"),
    ("original art illustration japan signed", None),
    ("promo only not for sale japan collectible", None),
    ("japanese pottery ceramic signed artist", None),
    ("japanese lacquer signed artisan", None),
    ("manga artist autograph signed original", None),
    ("anime figure signed limited promo japan", None),
    ("dragon ball signed autograph toriyama", None),
    ("one piece signed original art oda", None),
    ("studio ghibli original art signed miyazaki", None),
    ("sailor moon animation cel original", "550"),
    ("evangelion original art signed japan", None),
]

EBAY_MIN_PRICE_USD = 200  # Filter: only items priced $200+
EBAY_MIN_SOLD = 1  # Filter: must have at least 1 sold

# ── eBay demand check helpers ──────────────────────────────

_TITLE_MAP = {
    "ドラゴンボール": "dragon ball",
    "ワンピース": "one piece",
    "鬼滅の刃": "demon slayer",
    "進撃の巨人": "attack on titan",
    "ナルト": "naruto",
    "セーラームーン": "sailor moon",
    "エヴァンゲリオン": "evangelion",
    "ジブリ": "ghibli",
    "ガンダム": "gundam",
    "ポケモン": "pokemon",
    "ジョジョ": "jojo",
    "ブリーチ": "bleach",
    "デスノート": "death note",
    "鋼の錬金術師": "fullmetal alchemist",
    "ハンターハンター": "hunter x hunter",
    "ルパン三世": "lupin the third",
    "北斗の拳": "fist of the north star",
    "うる星やつら": "urusei yatsura",
    "となりのトトロ": "my neighbor totoro",
    "千と千尋": "spirited away",
    "もののけ姫": "princess mononoke",
    "天空の城ラピュタ": "castle in the sky",
    "鉄腕アトム": "astro boy",
    "ゴジラ": "godzilla",
    "ドラえもん": "doraemon",
}

_RARE_SUFFIX_MAP = {
    "直筆サイン": "signed autograph",
    "手書きサイン": "signed autograph",
    "セル画": "animation cel",
    "複製原画": "reproduction art",
    "原画": "original art",
    "肉筆": "original handwritten",
    "非売品": "promo not for sale",
    "一点物": "one of a kind",
    "サイン": "signed",
}


def _build_ebay_query(title: str, hint_query: str) -> str:
    """Build an eBay-friendly English query from a Japanese item title."""
    title_part = ""
    for jp, en in _TITLE_MAP.items():
        if jp in title or jp in hint_query:
            title_part = en
            break

    suffix_part = ""
    for jp, en in _RARE_SUFFIX_MAP.items():
        if jp in title or jp in hint_query:
            suffix_part = en
            break

    if title_part and suffix_part:
        return f"{title_part} {suffix_part}"
    if title_part:
        return f"{title_part} japan signed"
    if suffix_part:
        return f"japan {suffix_part}"
    return "japan rare collectible signed"


async def check_ebay_demand(title: str, hint_query: str) -> dict:
    """Check eBay demand for an item. Uses 24h cache; returns demand info dict."""
    _empty: dict = {
        "found": False,
        "min_usd": None,
        "max_usd": None,
        "listing_count": 0,
        "has_sold": False,
        "query": "",
    }

    ebay_query = _build_ebay_query(title, hint_query)
    _empty["query"] = ebay_query

    cached = await db.get_demand_cache(ebay_query)
    if cached:
        return {
            "found": cached["listing_count"] > 0,
            "min_usd": cached["min_usd"],
            "max_usd": cached["max_usd"],
            "listing_count": cached["listing_count"],
            "has_sold": bool(cached["has_sold"]),
            "query": ebay_query,
        }

    try:
        search_fn = _import_ebay_search()
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: search_fn(query=ebay_query, limit=20)),
            timeout=30,
        )
        items = result.get("items", []) if result else []
        prices = [
            item.get("price", 0) for item in items if (item.get("price") or 0) > 0
        ]
        has_sold = any((item.get("sold_quantity") or 0) > 0 for item in items)
        min_usd = min(prices) if prices else None
        max_usd = max(prices) if prices else None
        listing_count = len(items)

        await db.save_demand_cache(
            ebay_query, min_usd, max_usd, listing_count, has_sold
        )
        return {
            "found": listing_count > 0,
            "min_usd": min_usd,
            "max_usd": max_usd,
            "listing_count": listing_count,
            "has_sold": has_sold,
            "query": ebay_query,
        }
    except Exception as e:
        logger.debug(f"[demand_check] '{ebay_query}': {e}")
        return _empty


# ── AI demand scoring ─────────────────────────────────────


async def ai_score_demand(
    title: str,
    price_jpy: int,
    genre: str,
    demand: dict,
) -> dict:
    """Use Claude Haiku to judge if item has genuine overseas demand.

    Returns {"approved": bool, "reason": str}.
    Fails open: errors → approved=True so notifications are never silently dropped.
    """
    import anthropic

    if demand.get("found"):
        min_u = demand.get("min_usd") or 0
        max_u = demand.get("max_usd") or 0
        sold_str = "、成約実績あり" if demand.get("has_sold") else ""
        demand_str = (
            f"eBay: {demand['listing_count']}件出品、"
            f"価格帯 ${min_u:.0f}〜${max_u:.0f}{sold_str}"
        )
    else:
        demand_str = "eBay: データなし"

    prompt = f"""以下のヤフオク/メルカリ商品がeBayで海外コレクターに需要があるか判断してください。

商品タイトル: {title}
仕入れ価格: ¥{price_jpy:,}
ジャンル: {genre}
{demand_str}

判断基準（すべて満たすとYES）:
・海外（米国・欧州）で認知されているIP/ブランドか
・一点物・サイン品・原画など本物の希少性があるか
・eBay最高値が仕入れ価格の2倍以上か、または$100以上の成約実績があるか
・大量生産品・コピー品・格安グッズではないか

YES または NO で回答し、理由を15字以内で続けてください。
例: YES 鳥山明サインは欧米需要高
例: NO eBay最高値が仕入れより安い
例: NO 量産グッズで希少性なし"""

    try:
        client = anthropic.Anthropic()
        loop = asyncio.get_event_loop()
        msg = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=60,
                    messages=[{"role": "user", "content": prompt}],
                ),
            ),
            timeout=30,
        )
        raw = msg.content[0].text.strip()
        approved = raw.upper().startswith("YES")
        reason = raw[3:].strip().lstrip("、").strip() if len(raw) > 3 else raw
        return {"approved": approved, "reason": reason}
    except Exception as e:
        logger.debug(f"[ai_score] failed: {e}")
        return {"approved": True, "reason": "AI判定エラー"}


# ── 30-min scanner ─────────────────────────────────────────


async def _scan_rare_items_inner():
    """Inner scan logic. Called with a 20-min timeout by scan_rare_items()."""
    from scrapers.yahoo_auction import YahooAuctionScraper
    from scrapers.mercari import MercariScraper

    ya = YahooAuctionScraper()
    mc = MercariScraper()
    found_count = 0

    for genre_key, cfg in GENRE_CONFIG.items():
        for query in cfg["search_queries"]:
            try:
                results = await asyncio.gather(
                    ya.search(query), mc.search(query), return_exceptions=True
                )
            except Exception as e:
                logger.error(f"[rare_scan] gather error for '{query}': {e}")
                continue

            for result in results:
                if isinstance(result, Exception):
                    logger.debug(f"[rare_scan] scraper error: {result}")
                    continue

                for item in result:
                    if item.price is None:
                        continue
                    if not (cfg["min_price"] <= item.price <= cfg["max_price"]):
                        continue
                    if not any(kw in item.title for kw in RARE_KEYWORDS):
                        continue
                    if any(kw in item.title for kw in RARE_EXCLUDE_KEYWORDS):
                        continue
                    if await db.is_rare_url_seen(item.url):
                        continue

                    cid = uuid.uuid4().hex[:8]
                    await db.save_rare_candidate(
                        id=cid,
                        title=item.title,
                        price_jpy=item.price,
                        platform=item.platform,
                        url=item.url,
                        image_url=item.image_url,
                        genre=genre_key,
                    )
                    demand = await check_ebay_demand(item.title, query)
                    await db.record_candidate_demand(
                        cid,
                        demand["query"],
                        demand["min_usd"],
                        demand["max_usd"],
                        demand["listing_count"],
                        demand["has_sold"],
                    )
                    ai = await ai_score_demand(
                        item.title, item.price, cfg["label"], demand
                    )
                    await db.record_candidate_ai_score(
                        cid, ai["approved"], ai["reason"]
                    )
                    if not ai["approved"]:
                        logger.info(
                            f"[rare_scan] AI filtered: {item.title[:40]} → {ai['reason']}"
                        )
                        continue
                    await _send_rare_notification(
                        cid,
                        item.title,
                        item.price,
                        item.platform,
                        item.url,
                        cfg["label"],
                        demand,
                        ai["reason"],
                    )
                    found_count += 1

            await asyncio.sleep(1.5)

    # Also scan user-defined keywords (no RARE_KEYWORDS filter — user knows what they want)
    user_keywords = await db.get_rare_keywords(active_only=True)
    for kw in user_keywords:
        query = kw["name"]
        try:
            results = await asyncio.gather(
                ya.search(query), mc.search(query), return_exceptions=True
            )
        except Exception as e:
            logger.error(f"[rare_scan] user keyword '{query}': {e}")
            continue

        for result in results:
            if isinstance(result, Exception):
                continue
            for item in result:
                if item.price is None or item.price < 1_000:
                    continue
                if any(kw2 in item.title for kw2 in RARE_EXCLUDE_KEYWORDS):
                    continue
                if await db.is_rare_url_seen(item.url):
                    continue

                cid = uuid.uuid4().hex[:8]
                await db.save_rare_candidate(
                    id=cid,
                    title=item.title,
                    price_jpy=item.price,
                    platform=item.platform,
                    url=item.url,
                    image_url=item.image_url,
                    genre="custom",
                )
                demand = await check_ebay_demand(item.title, query)
                await db.record_candidate_demand(
                    cid,
                    demand["query"],
                    demand["min_usd"],
                    demand["max_usd"],
                    demand["listing_count"],
                    demand["has_sold"],
                )
                ai = await ai_score_demand(item.title, item.price, "custom", demand)
                await db.record_candidate_ai_score(cid, ai["approved"], ai["reason"])
                if not ai["approved"]:
                    logger.info(
                        f"[rare_scan] AI filtered: {item.title[:40]} → {ai['reason']}"
                    )
                    continue
                await _send_rare_notification(
                    cid,
                    item.title,
                    item.price,
                    item.platform,
                    item.url,
                    f"🔍 {query}",
                    demand,
                    ai["reason"],
                )
                found_count += 1

        await asyncio.sleep(1.5)

    logger.info(f"[rare_scan] complete: {found_count} new items")


async def scan_rare_items():
    """Entry point for APScheduler. Wraps inner scan with a 20-min hard timeout."""
    try:
        await asyncio.wait_for(_scan_rare_items_inner(), timeout=20 * 60)
    except asyncio.TimeoutError:
        logger.warning(
            "[rare_scan] timed out after 20 min — aborting to unblock scheduler"
        )


async def _send_rare_notification(
    cid: str,
    title: str,
    price_jpy: int,
    platform: str,
    source_url: str,
    genre_label: str,
    demand: Optional[dict] = None,
    ai_reason: str = "",
):
    platform_label = PLATFORM_LABELS.get(platform, platform)

    if demand and demand.get("found"):
        min_u = demand.get("min_usd")
        max_u = demand.get("max_usd")
        price_range = (
            f"${min_u:,.0f}〜${max_u:,.0f}"
            if min_u and max_u
            else f"${max_u:,.0f}"
            if max_u
            else "—"
        )
        if demand.get("has_sold"):
            demand_line = f"\n🔥 eBay: {price_range} (成約あり)"
        else:
            count = demand.get("listing_count", 0)
            demand_line = f"\n📦 eBay: {price_range} ({count}件出品)"
    else:
        demand_line = "\n❓ eBay需要: データなし"

    ai_line = f"\n✅ {ai_reason}" if ai_reason else ""

    text = (
        f"🎯 <b>レアアイテム発見！</b>\n"
        f"[{genre_label}]\n"
        f"{title}\n"
        f"💰 ¥{price_jpy:,}\n"
        f"🏪 {platform_label}"
        f"{demand_line}"
        f"{ai_line}"
    )
    base = os.getenv("PUBLIC_BASE_URL", f"http://192.168.68.57:{config.PORT}")
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "📦 出品する", "url": f"{base}/rare/list/{cid}"},
                {"text": "🚢 eShip登録", "url": f"{base}/rare/eship/{cid}"},
            ],
            [{"text": "🔗 商品ページ", "url": source_url}],
        ]
    }
    await _send_telegram(text, reply_markup=reply_markup)


# ── Weekly eBay market research ────────────────────────────


async def ebay_market_research():
    """Query eBay for high-value one-of-a-kind items and send a Telegram report.

    Used to identify what types of signed/promo/original items are selling well,
    so that Yahoo Auctions searches can be tuned accordingly.
    Runs weekly (Sunday 9:00 JST) or via POST /rare/ebay-research.
    """
    try:
        search_fn = _import_ebay_search()
    except Exception as e:
        await _send_telegram(f"⚠️ eBay市場調査: ebay-agentに接続できません\n{e}")
        return

    hits: list[dict] = []

    for query, cat_id in EBAY_RESEARCH_QUERIES:
        try:
            kwargs = {"query": query, "limit": 30}
            if cat_id:
                kwargs["category_id"] = cat_id
            result = search_fn(**kwargs)
            items = result.get("items", [])

            for item in items:
                price = item.get("price", 0) or 0
                sold = item.get("sold_quantity", 0) or 0
                if price < EBAY_MIN_PRICE_USD:
                    continue
                if sold < EBAY_MIN_SOLD:
                    continue
                hits.append(
                    {
                        "title": item.get("title", ""),
                        "price_usd": price,
                        "sold": sold,
                        "url": item.get("url", ""),
                        "query": query,
                    }
                )
        except Exception as e:
            logger.error(f"[ebay_research] query '{query}': {e}")
            continue

        await asyncio.sleep(1)

    if not hits:
        await _send_telegram(
            "🔍 eBay市場調査: 条件に合う商品が見つかりませんでした ($200+ / 成約あり)"
        )
        return

    # Sort by price descending, take top 15
    hits.sort(key=lambda x: x["price_usd"], reverse=True)
    top = hits[:15]

    # Build report
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"🔍 <b>eBay 一点物市場調査 {date_str}</b>",
        f"$200以上・成約あり: {len(hits)}件中 TOP{len(top)}",
    ]
    lines.append("")

    for i, h in enumerate(top, 1):
        title_short = h["title"][:50]
        jp_hint = _suggest_jp_keyword(h["title"])
        lines.append(f"{i}. <b>{title_short}</b>")
        lines.append(f"   💰 ${h['price_usd']:,.0f}  成約{h['sold']}件")
        if jp_hint:
            lines.append(f"   🔎 YA検索ヒント: {jp_hint}")
        lines.append("")

    # Category breakdown
    from collections import Counter

    query_counts = Counter(h["query"].split()[0] for h in hits)
    top_types = " / ".join(f"{k}:{v}" for k, v in query_counts.most_common(4))
    lines.append(f"📊 傾向: {top_types}")

    await _send_telegram("\n".join(lines))
    logger.info(f"[ebay_research] report sent: {len(hits)} hits, top {len(top)} shown")


def _suggest_jp_keyword(english_title: str) -> Optional[str]:
    """Extract a rough Japanese search hint from an eBay English title."""
    _NOISE = {
        "signed",
        "autographed",
        "autograph",
        "hand",
        "original",
        "japan",
        "japanese",
        "vintage",
        "rare",
        "limited",
        "the",
        "a",
        "an",
        "for",
        "sale",
        "not",
        "only",
        "promo",
        "promotional",
        "sample",
        "with",
        "and",
        "or",
        "by",
        "from",
        "new",
        "used",
        "mint",
        "lot",
        "set",
        "collection",
        "collector",
        "item",
        "very",
        "good",
        "excellent",
        "perfect",
        "condition",
        "art",
        "print",
        "photo",
        "picture",
        "animation",
        "cel",
        "anime",
        "manga",
    }
    words = english_title.split()
    meaningful = [
        w.rstrip(".,!?")
        for w in words
        if w.lower().rstrip(".,!?") not in _NOISE and len(w) >= 3
    ]
    # Keep first 3 meaningful words
    return " ".join(meaningful[:3]) if meaningful else ""


def _import_ebay_search():
    """Import search_ebay_discover from ebay-agent's ebay_core.client."""
    import os

    ebay_agent_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "ebay-agent",
    )
    ebay_agent_dir = os.path.abspath(ebay_agent_dir)
    if ebay_agent_dir not in sys.path:
        sys.path.insert(0, ebay_agent_dir)
    from ebay_core.client import search_ebay_discover  # noqa: PLC0415

    return search_ebay_discover
