"""Discovery Engine — eBay需要DBから新規利益商品を発見するシステム。

既存の在庫切れマッチングとは独立したパイプライン:
1. eBay売れ筋データを収集 → demand_items テーブル
2. 需要DBキーワードで日本マーケット検索
3. 利益計算 → LINE通知（新規出品候補）
4. ユーザー承認 → eShip登録 + eBay出品作成
"""
import json
import logging
import os
import re
import sys
import time
from typing import Optional

import aiosqlite

# Import deal-watcher config (must be before ebay-agent path is added to sys.path)
import config as _dw_config
# Alias for clarity — this is deal-watcher's config, NOT ebay-agent's
dw_config = _dw_config

logger = logging.getLogger(__name__)

# eBay Agent のクライアントを再利用
# Try multiple paths (service dir vs workspace)
_EBAY_AGENT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ebay-agent"),
    os.path.expanduser("~/Desktop/Claude Workspace/products/ebay-agent"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebay-agent"),
]
EBAY_AGENT_DIR = ""
for _p in _EBAY_AGENT_CANDIDATES:
    if os.path.isdir(os.path.join(_p, "ebay_core")):
        EBAY_AGENT_DIR = _p
        break
if EBAY_AGENT_DIR and EBAY_AGENT_DIR not in sys.path:
    sys.path.insert(0, EBAY_AGENT_DIR)

# Fee rates (same as ebay-agent config)
EBAY_FEE_RATE = 0.129
PAYONEER_FEE_RATE = 0.02
INTL_SHIPPING_JPY = 3000  # 国際送料の目安

# Condition mapping: JP marketplace keywords → eBay condition + price modifier
CONDITION_MODIFIERS = {
    # Good condition (full price)
    "動作確認済": (1.0, "Used"),
    "動作品": (1.0, "Used"),
    "完動品": (1.0, "Used"),
    "美品": (1.05, "Used"),
    "極美品": (1.1, "Used"),
    "新品": (1.2, "New"),
    "未使用": (1.15, "New"),
    "未開封": (1.2, "New"),
    # Degraded condition (discount)
    "ジャンク": (0.0, "For Parts"),  # skip
    "現状品": (0.5, "For Parts"),
    "動作未確認": (0.5, "For Parts"),
    "難あり": (0.4, "For Parts"),
    "訳あり": (0.5, "For Parts"),
    "部品取り": (0.0, "For Parts"),  # skip
}

# Demand DB categories to scan on eBay
# Format: (search_query, category_id, jp_search_terms)
SEED_CATEGORIES = [
    # Audio equipment
    ("vintage synthesizer", "38071", ["シンセサイザー", "synthesizer"]),
    ("vintage drum machine", "38072", ["ドラムマシン", "drum machine"]),
    ("reel to reel tape recorder", "175737", ["オープンリール", "reel to reel"]),
    ("vintage mixer audio", "64529", ["ミキサー", "mixer"]),
    ("multitrack recorder", "175737", ["MTR", "マルチトラック"]),
    ("vintage amplifier", "175735", ["アンプ", "amplifier"]),
    ("guitar effects pedal", "181222", ["エフェクター", "effects pedal"]),
    ("portable cassette recorder", "175737", ["カセット", "cassette recorder"]),
    # Japanese collectibles
    ("japanese samurai sword tsuba", "36280", ["鍔", "tsuba"]),
    ("japanese netsuke", "36280", ["根付", "netsuke"]),
    ("japanese inro", "36280", ["印籠", "inro"]),
]


# ── Demand DB management ──────────────────────────────────

async def init_demand_tables():
    """Create demand-related tables if not exist."""
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS demand_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_query TEXT NOT NULL,
                brand TEXT,
                model TEXT,
                category_id TEXT,
                avg_price_usd REAL,
                sold_count INTEGER DEFAULT 0,
                demand_score REAL DEFAULT 0,
                condition_typical TEXT,
                jp_search_terms TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1,
                UNIQUE(search_query, brand, model)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS discovery_candidates (
                id TEXT PRIMARY KEY,
                demand_item_id INTEGER,
                source_platform TEXT,
                source_title TEXT NOT NULL,
                source_price INTEGER,
                source_url TEXT NOT NULL,
                source_image_url TEXT,
                source_condition TEXT,
                ebay_est_price_usd REAL,
                est_profit_jpy INTEGER,
                brand TEXT,
                model TEXT,
                status TEXT DEFAULT 'pending',
                reject_note TEXT,
                reject_keywords TEXT,
                ebay_listing_id TEXT,
                eship_registered INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (demand_item_id) REFERENCES demand_items(id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_demand_score
            ON demand_items(demand_score DESC)
        """)
        await db.commit()


def _import_ebay_client():
    """Import ebay_core.client functions.

    In service environment, ebay_core/ is a local copy that imports from
    ebay_config.py (not config.py) to avoid naming collision.
    In workspace, ebay-agent dir is added to sys.path.
    """
    # Ensure ebay-agent is importable
    if EBAY_AGENT_DIR and EBAY_AGENT_DIR not in sys.path:
        sys.path.insert(0, EBAY_AGENT_DIR)

    from ebay_core.client import search_ebay_discover, get_recent_orders
    return search_ebay_discover, get_recent_orders


async def collect_demand_data(max_queries: int = 20):
    """Collect eBay sold/demand data and populate demand_items table.

    Uses eBay Browse API via ebay-agent's client to find high-demand products.
    """
    try:
        search_ebay_discover, _ = _import_ebay_client()
    except (ImportError, Exception) as e:
        logger.error(f"Cannot import ebay_core.client: {e}")
        return 0

    count = 0

    for query, cat_id, jp_terms in SEED_CATEGORIES[:max_queries]:
        try:
            result = search_ebay_discover(
                query=query,
                limit=50,
                category_id=cat_id,
            )
            items = result.get("items", [])
            total = result.get("total", 0)

            # Group by brand+model extracted from titles
            brand_model_groups = {}
            for item in items:
                title = item.get("title", "")
                brand, model = _extract_brand_model(title)
                if not brand:
                    continue

                key = f"{brand}|{model}" if model else brand
                if key not in brand_model_groups:
                    brand_model_groups[key] = {
                        "brand": brand,
                        "model": model,
                        "prices": [],
                        "sold_total": 0,
                        "conditions": [],
                    }
                grp = brand_model_groups[key]
                grp["prices"].append(item.get("price", 0))
                grp["sold_total"] += item.get("sold_quantity", 0)
                if item.get("condition"):
                    grp["conditions"].append(item["condition"])

            # Save to DB
            async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
                for key, grp in brand_model_groups.items():
                    if not grp["prices"]:
                        continue
                    avg_price = sum(grp["prices"]) / len(grp["prices"])
                    sold_count = grp["sold_total"]
                    # Demand score: combination of sold quantity and listing count
                    demand_score = sold_count * 2 + len(grp["prices"])

                    if demand_score < 2:
                        continue  # too low demand

                    condition = grp["conditions"][0] if grp["conditions"] else ""
                    search_q = f"{grp['brand']} {grp['model']}".strip()

                    await db.execute("""
                        INSERT INTO demand_items
                        (search_query, brand, model, category_id, avg_price_usd,
                         sold_count, demand_score, condition_typical, jp_search_terms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(search_query, brand, model) DO UPDATE SET
                            avg_price_usd = excluded.avg_price_usd,
                            sold_count = excluded.sold_count,
                            demand_score = excluded.demand_score,
                            last_updated = CURRENT_TIMESTAMP
                    """, (
                        search_q, grp["brand"], grp["model"], cat_id,
                        round(avg_price, 2), sold_count, round(demand_score, 1),
                        condition, json.dumps(jp_terms, ensure_ascii=False),
                    ))
                    count += 1
                await db.commit()

            logger.info(f"Demand scan: '{query}' → {len(brand_model_groups)} groups, {total} total on eBay")

        except Exception as e:
            logger.error(f"Demand collection error for '{query}': {e}")
            continue

    logger.info(f"Demand DB updated: {count} items")
    return count


async def collect_from_own_sales():
    """Collect demand data from own sales history (agent.db orders)."""
    try:
        _, get_recent_orders = _import_ebay_client()
    except (ImportError, Exception):
        logger.warning("Cannot import ebay_core.client for sales history")
        return 0

    try:
        orders = get_recent_orders(days=90)
    except Exception as e:
        logger.error(f"Failed to get own sales: {e}")
        return 0

    count = 0
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        for order in orders:
            title = order.get("title", "")
            price_usd = order.get("total", 0)
            brand, model = _extract_brand_model(title)
            if not brand or price_usd < 30:
                continue

            search_q = f"{brand} {model}".strip()
            # Own sales get high demand score boost
            await db.execute("""
                INSERT INTO demand_items
                (search_query, brand, model, category_id, avg_price_usd,
                 sold_count, demand_score, jp_search_terms)
                VALUES (?, ?, ?, '', ?, 1, 50, '[]')
                ON CONFLICT(search_query, brand, model) DO UPDATE SET
                    demand_score = demand_score + 20,
                    sold_count = sold_count + 1,
                    last_updated = CURRENT_TIMESTAMP
            """, (search_q, brand, model, price_usd))
            count += 1
        await db.commit()

    logger.info(f"Own sales demand update: {count} items")
    return count


# ── Discovery Scanner ────────────────────────────────────

async def run_discovery_scan(max_items: int = 30):
    """Scan Japanese marketplaces using demand DB keywords.

    Picks top-demand items, searches JP marketplaces, evaluates profit.
    """
    from scrapers import ALL_SCRAPERS
    from auto_sourcing import ACCESSORY_KEYWORDS, _matches_reject_pattern

    # Get top demand items
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM demand_items
            WHERE active = 1
            ORDER BY demand_score DESC
            LIMIT ?
        """, (max_items,))
        demand_items = [dict(row) for row in await cur.fetchall()]

    if not demand_items:
        logger.info("No demand items to scan")
        return 0

    import asyncio
    candidates_found = 0

    for demand in demand_items:
        search_query = demand["search_query"]
        avg_price_usd = demand.get("avg_price_usd", 0)
        if avg_price_usd < 30:
            continue

        # Get exchange rate
        rate = _get_exchange_rate()

        # Calculate max purchase price (in JPY) that would still be profitable
        # profit = (ebay_price * (1 - ebay_fee - payoneer_fee) * rate) - purchase_price - shipping
        max_purchase = (avg_price_usd * (1 - EBAY_FEE_RATE - PAYONEER_FEE_RATE) * rate
                        - INTL_SHIPPING_JPY - dw_config.AUTO_SOURCE_MIN_PROFIT)

        if max_purchase <= 0:
            continue

        # Search Japanese marketplaces
        tasks = [scraper.search(search_query) for scraper in ALL_SCRAPERS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for scraper, result in zip(ALL_SCRAPERS, results):
            if isinstance(result, Exception):
                continue

            for item in result:
                price = item.price or 0
                if price <= 0 or price > max_purchase:
                    continue

                title_lower = item.title.lower()

                # Skip accessories
                if any(kw.lower() in title_lower for kw in ACCESSORY_KEYWORDS):
                    continue

                # Skip junk items
                condition, modifier = _assess_condition(item.title)
                if modifier <= 0:
                    continue

                # Skip if matches user reject patterns
                if _matches_reject_pattern(item.title):
                    continue

                # Check if already discovered
                async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
                    cur = await db.execute(
                        "SELECT 1 FROM discovery_candidates WHERE source_url = ?",
                        (item.url,)
                    )
                    if await cur.fetchone():
                        continue

                # Calculate estimated profit
                est_profit = _calc_profit(avg_price_usd, price, rate)
                if est_profit < dw_config.AUTO_SOURCE_MIN_PROFIT:
                    continue

                # Check description for junk keywords (scrape detail page)
                from auto_sourcing import check_description_junk
                is_junk, _ = await check_description_junk(item.url)
                if is_junk:
                    continue

                # Save as discovery candidate
                candidate = {
                    "demand_item_id": demand["id"],
                    "source_platform": item.platform,
                    "source_title": item.title,
                    "source_price": price,
                    "source_url": item.url,
                    "source_image_url": item.image_url,
                    "source_condition": condition,
                    "ebay_est_price_usd": avg_price_usd,
                    "est_profit_jpy": est_profit,
                    "brand": demand.get("brand", ""),
                    "model": demand.get("model", ""),
                }
                cid = await _save_discovery_candidate(candidate)
                await _notify_discovery_candidate(candidate, cid)
                candidates_found += 1

        # Rate limit between demand items
        await asyncio.sleep(2)

    logger.info(f"Discovery scan complete: {candidates_found} candidates found")
    return candidates_found


# ── Profit Calculation ───────────────────────────────────

_exchange_rate_cache = {"rate": 150.0, "ts": 0}


def _get_exchange_rate() -> float:
    """Get USD/JPY exchange rate (cached for 1 hour)."""
    if time.time() - _exchange_rate_cache["ts"] < 3600:
        return _exchange_rate_cache["rate"]

    try:
        from ebay_core.client import _browse_headers
        import requests
        # Use a simple fallback
        _exchange_rate_cache["rate"] = 150.0  # reasonable default
        _exchange_rate_cache["ts"] = time.time()
    except Exception:
        pass

    # Try to get from eShip cache
    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".eship_profit_cache.json")
    try:
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                data = json.load(f)
            rate = data.get("exchange_rate", 0)
            if rate > 0:
                _exchange_rate_cache["rate"] = rate
                _exchange_rate_cache["ts"] = time.time()
    except Exception:
        pass

    return _exchange_rate_cache["rate"]


def _calc_profit(ebay_price_usd: float, purchase_price_jpy: int, rate: float) -> int:
    """Calculate estimated profit in JPY."""
    gross_usd = ebay_price_usd * (1 - EBAY_FEE_RATE - PAYONEER_FEE_RATE)
    gross_jpy = gross_usd * rate
    profit = gross_jpy - purchase_price_jpy - INTL_SHIPPING_JPY
    return round(profit)


def calc_optimal_price(
    purchase_price_jpy: int,
    rate: float,
    min_profit_jpy: int = 0,
    min_margin: float = 0,
    shipping_jpy: int = INTL_SHIPPING_JPY,
) -> dict:
    """Calculate optimal eBay USD price meeting both profit and margin constraints.

    Returns: {"price_usd", "profit_jpy", "margin", "constraint"}
    """
    if min_profit_jpy <= 0:
        min_profit_jpy = dw_config.AUTO_SOURCE_MIN_PROFIT
    if min_margin <= 0:
        min_margin = dw_config.MIN_PROFIT_MARGIN

    net_rate = 1 - EBAY_FEE_RATE - PAYONEER_FEE_RATE  # ~0.851

    # Price to achieve minimum profit
    price_for_profit = (purchase_price_jpy + shipping_jpy + min_profit_jpy) / (net_rate * rate)

    # Price to achieve minimum margin
    # margin = profit / (price_usd * rate)
    # Solving: price_usd = (purchase + shipping) / (rate * (net_rate - margin))
    denom = rate * (net_rate - min_margin)
    price_for_margin = (purchase_price_jpy + shipping_jpy) / denom if denom > 0 else price_for_profit

    optimal_price = max(price_for_profit, price_for_margin)
    actual_profit = _calc_profit(optimal_price, purchase_price_jpy, rate)
    actual_margin = actual_profit / (optimal_price * rate) if optimal_price > 0 else 0

    return {
        "price_usd": round(optimal_price, 2),
        "profit_jpy": round(actual_profit),
        "margin": round(actual_margin, 3),
        "constraint": "margin" if price_for_margin > price_for_profit else "profit",
    }


# ── Condition Assessment ─────────────────────────────────

def _assess_condition(title: str) -> tuple:
    """Assess item condition from title. Returns (condition_label, price_modifier)."""
    title_lower = title.lower()
    # Check Japanese keywords
    for kw, (modifier, label) in CONDITION_MODIFIERS.items():
        if kw in title or kw.lower() in title_lower:
            return label, modifier
    # Default: assume used/working
    return "Used", 0.8


# ── Brand/Model Extraction ──────────────────────────────

# Known audio/electronics brands
_BRANDS = {
    "akai", "roland", "korg", "yamaha", "boss", "tascam", "technics",
    "pioneer", "denon", "marantz", "sony", "panasonic", "jbl", "bose",
    "sennheiser", "shure", "audio-technica", "behringer", "moog",
    "sequential", "oberheim", "emu", "ensoniq", "casio", "fostex",
    "toa", "teac", "nakamichi", "accuphase", "luxman", "mcintosh",
    "fender", "gibson", "ibanez", "esp", "digitech", "line6", "line 6",
    "eventide", "tc electronic", "zoom", "alesis", "ampeg", "mesa boogie",
    "marshall", "vox", "orange", "peavey", "crown", "dbx", "lexicon",
    "teenage engineering", "elektron", "arturia", "novation", "dave smith",
    "nord", "kurzweil", "access", "waldorf", "clavia",
}


# Words that are NOT brands (common adjectives/descriptors/nouns in eBay titles)
_NOT_BRANDS = {
    # Adjectives
    "vintage", "antique", "rare", "used", "new", "working", "tested",
    "japan", "japanese", "original", "authentic", "genuine", "classic",
    "professional", "portable", "digital", "analog", "analogue", "electric",
    "electronic", "acoustic", "stereo", "mono", "mini", "micro", "pro",
    "custom", "limited", "edition", "special", "premium", "deluxe",
    "lot", "set", "bundle", "pair", "old", "retro", "modern",
    "small", "large", "big", "fine", "great", "nice", "good", "beautiful",
    "handmade", "carved", "signed", "painted", "engraved", "gilded",
    # Common nouns (not brands)
    "iron", "steel", "bronze", "brass", "copper", "silver", "gold", "wood",
    "boxwood", "ivory", "bone", "lacquer", "ceramic", "porcelain", "clay",
    "sword", "blade", "katana", "tsuba", "fuchi", "kashira", "menuki",
    "netsuke", "inro", "ojime", "sagemono", "okimono", "toggle",
    "samurai", "warrior", "dragon", "tiger", "crane", "flower", "bamboo",
    "edo", "meiji", "taisho", "showa", "period", "century", "era",
    "fuzz", "pedal", "guitar", "bass", "keyboard", "drum", "mixer",
    "amplifier", "speaker", "microphone", "cable", "adapter",
    "figure", "statue", "mask", "armor", "helmet", "plate", "bowl", "vase",
    "box", "case", "stand", "holder", "mount", "rack",
    "emu", "donner", "modtone", "sonicake",  # too generic/cheap brands
    "m-vave",
}


def _extract_brand_model(title: str) -> tuple:
    """Extract brand and model from an eBay title.

    Returns (brand, model) tuple. Brand is empty if not found.
    """
    title_lower = title.lower()

    brand = ""
    for b in _BRANDS:
        if b in title_lower:
            brand = b.title()
            break

    if not brand:
        # Try first non-descriptor word as brand
        words = title.split()
        for w in words:
            if w.lower() not in _NOT_BRANDS and len(w) >= 2 and w[0].isupper():
                brand = w
                break

    # Skip if brand is still a generic word
    if brand.lower() in _NOT_BRANDS:
        return "", ""

    # Extract model: alphanumeric token with digits
    model = ""
    tokens = re.findall(r'[A-Za-z0-9]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|[A-Za-z0-9]+', title)
    for token in tokens:
        if token.lower() == brand.lower():
            continue
        if re.search(r'\d', token) and len(token) >= 2:
            model = token
            break

    # Require model number for reliable matching
    # "Roland" alone is too broad; "Roland JP-8080" is specific
    if not model:
        return "", ""

    return brand, model


# ── Candidate Management ─────────────────────────────────

async def _save_discovery_candidate(candidate: dict) -> str:
    """Save discovery candidate to DB and return UUID."""
    import uuid
    cid = str(uuid.uuid4())[:8]
    try:
        async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO discovery_candidates
                (id, demand_item_id, source_platform, source_title, source_price,
                 source_url, source_image_url, source_condition,
                 ebay_est_price_usd, est_profit_jpy, brand, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, candidate["demand_item_id"], candidate["source_platform"],
                candidate["source_title"], candidate["source_price"],
                candidate["source_url"], candidate.get("source_image_url", ""),
                candidate.get("source_condition", ""),
                candidate["ebay_est_price_usd"], candidate["est_profit_jpy"],
                candidate.get("brand", ""), candidate.get("model", ""),
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save discovery candidate: {e}")
    return cid


async def _notify_discovery_candidate(candidate: dict, cid: str):
    """Send LINE Flex Message for a new discovery candidate."""
    from notifier import notify_line_flex, PLATFORM_LABELS

    platform_label = PLATFORM_LABELS.get(candidate["source_platform"], candidate["source_platform"])
    profit = candidate["est_profit_jpy"]
    price = candidate["source_price"]
    ebay_usd = candidate["ebay_est_price_usd"]
    brand = candidate.get("brand", "")
    model = candidate.get("model", "")
    product_name = f"{brand} {model}".strip() or candidate["source_title"][:40]

    base_url = f"http://192.168.68.57:{dw_config.PORT}"
    approve_url = f"{base_url}/discovery/approve/{cid}"
    reject_url = f"{base_url}/discovery/reject/{cid}"

    await notify_line_flex(
        alt_text=f"新規出品候補: {product_name} 利益¥{profit:,}",
        contents={
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "新規出品候補", "weight": "bold",
                     "size": "md", "color": "#0066FF"},
                    {"type": "text", "text": product_name[:50],
                     "size": "sm", "wrap": True, "weight": "bold"},
                    {"type": "text", "text": candidate["source_title"][:60],
                     "size": "xs", "color": "#888888", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
                        {"type": "text", "text": "仕入れ", "size": "sm",
                         "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"¥{price:,} ({platform_label})",
                         "size": "sm", "align": "end"},
                    ]},
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "eBay相場", "size": "sm",
                         "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"${ebay_usd:,.0f}",
                         "size": "sm", "align": "end"},
                    ]},
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "見込み利益", "size": "sm",
                         "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"¥{profit:,}", "size": "sm",
                         "weight": "bold", "color": "#1DB446", "align": "end"},
                    ]},
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "状態", "size": "sm",
                         "color": "#555555", "flex": 0},
                        {"type": "text", "text": candidate.get("source_condition", "不明"),
                         "size": "sm", "align": "end"},
                    ]},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary", "color": "#0066FF",
                         "action": {"type": "uri", "label": "出品する",
                                    "uri": approve_url}},
                        {"type": "button", "style": "secondary",
                         "action": {"type": "uri", "label": "商品を見る",
                                    "uri": candidate["source_url"]}},
                    ]},
                    {"type": "button", "style": "link", "height": "sm", "color": "#e74c3c",
                     "action": {"type": "uri", "label": "見送り（理由を入力）",
                                "uri": reject_url}},
                ],
            },
        },
    )
    logger.info(f"Discovery candidate: {product_name} ¥{price:,} → 利益¥{profit:,}")


# ── Auto-Listing Pipeline ───────────────────────────────

async def create_ebay_listing_from_candidate(candidate_id: str) -> dict:
    """Full pipeline: generate listing data → register eShip → create eBay draft.

    Returns {"status": "ok", ...} or {"status": "error", "message": ...}
    """
    # Load candidate
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)
        )
        row = await cur.fetchone()

    if not row:
        return {"status": "error", "message": "Candidate not found"}

    candidate = dict(row)
    brand = candidate.get("brand", "")
    model = candidate.get("model", "")
    product_name = f"{brand} {model}".strip()
    condition = candidate.get("source_condition", "Used")

    try:
        # Step 0: Scrape source listing for description and images
        from scrapers.detail import scrape_detail
        detail = await scrape_detail(candidate["source_url"])
        description_jp = ""
        image_urls_list = []
        if detail:
            description_jp = detail.description
            image_urls_list = detail.image_urls
            if detail.condition and not condition:
                condition = detail.condition
            logger.info(f"Scraped source: {len(description_jp)} chars, {len(image_urls_list)} images")

        # Step 1: Run agent team for listing generation
        from agents import run_agent_team
        team_result = await run_agent_team(
            product_name=product_name,
            purchase_price_jpy=candidate["source_price"],
            condition=condition,
            description_jp=description_jp,
            image_urls=image_urls_list or [candidate.get("source_image_url", "")],
        )
        listing_data = team_result["listing"]
        quality = team_result.get("quality", {})

        # Step 2: Register on eShip (new item)
        from eship import create_eship_item
        eship_title = listing_data["titles"][0]["title"] if listing_data.get("titles") else product_name
        eship_result = await create_eship_item(
            title=eship_title,
            supplier_url=candidate["source_url"],
            purchase_price=candidate["source_price"],
            platform=candidate["source_platform"],
            selling_price_usd=candidate.get("ebay_est_price_usd", 0),
            sku=sku,
            condition=condition,
            condition_description=quality.get("condition_notes_en", ""),
            image_url=image_urls_list[0] if image_urls_list else candidate.get("source_image_url", ""),
            memo=product_name[:200],
        )

        eship_ok = eship_result.get("status") == "ok"

        # Step 3: Create eBay draft listing
        _import_ebay_client()  # re-ensure config
        from ebay_core.client import create_inventory_item, create_offer
        import uuid

        sku = f"DW-{str(uuid.uuid4())[:6].upper()}"
        title = listing_data.get("title", "") or product_name
        if isinstance(listing_data.get("titles"), list) and listing_data["titles"]:
            title = listing_data["titles"][0].get("title", title)
        description = listing_data.get("description_html", "")
        aspects = listing_data.get("specs", {})
        category_id = listing_data.get("category_id", "") or candidate.get("category_id", "")

        # Use quality agent's condition or fallback
        ebay_condition = quality.get("ebay_condition", "USED_VERY_GOOD")

        # Create inventory item (draft — not published until confirmed)
        image_urls = image_urls_list[:12] if image_urls_list else [candidate.get("source_image_url", "")]
        image_urls = [u for u in image_urls if u]
        inv_result = create_inventory_item(
            sku=sku,
            product={
                "title": title,
                "description": description,
                "aspects": aspects,
                "imageUrls": image_urls,
            },
            condition=ebay_condition,
            quantity=1,
        )

        # Create offer (draft — not published)
        ebay_price = candidate.get("ebay_est_price_usd", 0)
        offer_result = create_offer(
            sku=sku,
            price_usd=ebay_price,
            category_id=category_id,
            listing_description=description,
        )

        offer_id = offer_result.get("offerId", "")

        # Update candidate status
        async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
            await db.execute("""
                UPDATE discovery_candidates
                SET status = 'listed', eship_registered = ?, ebay_listing_id = ?
                WHERE id = ?
            """, (1 if eship_ok else 0, offer_id, candidate_id))
            await db.commit()

        return {
            "status": "ok",
            "sku": sku,
            "title": title,
            "offer_id": offer_id,
            "eship_registered": eship_ok,
            "listing_data": {
                "description_preview": description[:200],
                "specs_count": len(aspects),
            },
        }

    except Exception as e:
        logger.error(f"Auto-listing pipeline error: {e}")
        return {"status": "error", "message": str(e)}
