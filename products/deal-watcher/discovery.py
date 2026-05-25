"""Discovery Engine — eBay需要DBから新規利益商品を発見するシステム。

既存の在庫切れマッチングとは独立したパイプライン:
1. eBay売れ筋データを収集 → demand_items テーブル
2. 需要DBキーワードで日本マーケット検索
3. 利益計算 → LINE通知（新規出品候補）
4. ユーザー承認 → eShip登録 + eBay出品作成
"""

import asyncio
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

# Fee rates (eShip準拠)
EBAY_FEE_RATE = 0.0935  # eBay FVF（eShip実績: 9.35%）
PAYONEER_FEE_RATE = 0.02  # Payoneer withdrawal fee
PROMOTED_RATE = 0.02  # Promoted listing rate (General 2% fixed)
PAYONEER_FX_MARGIN = 0.01  # Payoneer為替マージン (~1% below market rate)
INTL_SHIPPING_JPY = 5000  # FedEx国際送料のデフォルト（小型商品）
TARIFF_RATE = 0.135  # 関税（eShip実績: 13.5%）

# FedEx送料テーブル（eShip実績ベース、重量→送料）
SHIPPING_BY_WEIGHT = [
    (1500, 3793),  # ~1.5kg: BOSS DR-550
    (3000, 4319),  # ~3kg: Yamaha YPC-32, VOX ToneLab
    (5000, 5430),  # ~5kg: Pioneer CDJ-200, JBL
    (6000, 5955),  # ~6kg: BOSS RC-600
    (7000, 7460),  # ~7kg: DJM-3000, Trumpet
    (8500, 8613),  # ~8.5kg: DJM-900NXS2, Roland MV-1
    (12000, 14305),  # ~12kg: Sony CDP
    (17000, 18611),  # ~17kg: Silent Guitar
    (25000, 27688),  # ~25kg: Acoustic Guitar
    (55000, 63994),  # ~55kg: Samurai Armor
]


def _estimate_shipping(weight_g: int = 0, title: str = "") -> int:
    """Estimate FedEx shipping cost based on weight or product keywords."""
    if weight_g <= 0:
        # Estimate weight from product keywords
        title_lower = title.lower()
        # Ordered list: more specific matches first
        heavy_keywords = [
            # Small items FIRST (prevent false match with larger categories)
            ("pedal", 2000),
            ("effects pedal", 2000),
            ("stomp", 2000),
            ("effect unit", 2000),
            ("multi-effects", 2000),
            ("drum machine", 3000),
            ("drum pad", 3000),
            ("groovebox", 3000),
            ("minidisc", 3000),
            ("md deck", 3000),
            ("md player", 3000),
            ("walkman", 1500),
            ("portable", 2000),
            ("microphone", 2000),
            ("headphone", 1500),
            ("watch", 500),
            ("pen", 500),
            ("netsuke", 500),
            ("inro", 500),
            ("flute", 3000),
            ("piccolo", 3000),
            # Medium items
            ("sampler", 4000),
            ("sequencer", 4000),
            ("trumpet", 6000),
            ("saxophone", 8000),
            ("tape deck", 7000),
            ("cassette deck", 5000),
            ("dj controller", 7000),
            ("mixer", 7000),
            # Key count (specific sizes)
            ("88-key", 35000),
            ("76-key", 30000),
            ("61-key", 25000),
            ("49-key", 12000),
            ("37-key", 8000),
            ("25-key", 5000),
            # Large items
            ("armor", 55000),
            ("yoroi", 55000),
            ("reel to reel", 15000),
            ("bass guitar", 25000),
            ("guitar amp", 12000),
            ("guitar", 25000),
            ("piano", 20000),
            ("turntable", 12000),
            ("record player", 12000),
            ("speaker", 12000),
            ("subwoofer", 15000),
            ("amplifier", 8000),
            ("receiver", 8000),
            ("amp ", 8000),
            ("keyboard", 15000),
            ("organ", 20000),
            ("synthesizer", 10000),
            ("synth", 8000),
            ("cd player", 12000),
            ("drum kit", 15000),
            ("drum set", 15000),
        ]
        for kw, w in heavy_keywords:
            if kw in title_lower:
                weight_g = w
                break
        if weight_g <= 0:
            weight_g = 3000  # Default: 3kg for unknown items

    # Look up shipping cost
    for max_weight, cost in SHIPPING_BY_WEIGHT:
        if weight_g <= max_weight:
            return cost
    return SHIPPING_BY_WEIGHT[-1][1]  # Max


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
    # Audio equipment (existing)
    ("vintage synthesizer", "38071", ["シンセサイザー", "synthesizer"]),
    ("vintage drum machine", "38072", ["ドラムマシン", "drum machine"]),
    ("reel to reel tape recorder", "175737", ["オープンリール", "reel to reel"]),
    ("vintage mixer audio", "64529", ["ミキサー", "mixer"]),
    ("multitrack recorder", "175737", ["MTR", "マルチトラック"]),
    ("vintage amplifier", "175735", ["アンプ", "amplifier"]),
    ("guitar effects pedal", "181222", ["エフェクター", "effects pedal"]),
    ("portable cassette recorder", "175737", ["カセット", "cassette recorder"]),
    # Musical instruments (NEW)
    ("electric guitar japan", "33034", ["エレキギター", "electric guitar"]),
    ("acoustic guitar japan", "33021", ["アコースティックギター", "acoustic guitar"]),
    ("electric bass japan", "4713", ["ベース", "bass guitar"]),
    ("keyboard workstation", "38068", ["キーボード", "ワークステーション"]),
    ("digital piano", "38070", ["電子ピアノ", "digital piano"]),
    ("electronic drums", "38069", ["電子ドラム", "electronic drums"]),
    ("wind instrument japan", "10181", ["管楽器", "wind instrument"]),
    ("violin japan", "10179", ["バイオリン", "violin"]),
    # DJ equipment (NEW)
    ("DJ controller", "116874", ["DJコントローラー", "DJ controller"]),
    ("DJ turntable", "48458", ["ターンテーブル", "turntable"]),
    ("DJ mixer", "48457", ["DJミキサー", "DJ mixer"]),
    ("CDJ player", "48457", ["CDJ", "CDJ player"]),
    # Audio components (NEW)
    ("minidisc recorder", "175737", ["MDレコーダー", "minidisc"]),
    ("CD player hifi", "175738", ["CDプレーヤー", "CD player"]),
    ("receiver amplifier", "175735", ["レシーバー", "receiver"]),
    ("bookshelf speakers hifi", "14990", ["スピーカー", "speakers"]),
    ("headphones audiophile", "112529", ["ヘッドホン", "headphones"]),
    ("microphone vintage", "67828", ["マイク", "microphone"]),
    # Camera equipment (NEW)
    ("camera lens japan", "3323", ["カメラレンズ", "camera lens"]),
    ("film camera japan", "15230", ["フィルムカメラ", "film camera"]),
    ("vintage camera nikon", "15230", ["ニコン", "Nikon camera"]),
    # Watches (NEW)
    ("casio g-shock japan", "31387", ["G-SHOCK", "casio watch"]),
    # S-rank: High value + few sellers
    ("nakaya fountain pen", "118888", ["中屋万年筆", "Nakaya"]),
    ("namiki fountain pen", "118888", ["並木万年筆", "Namiki", "PILOT蒔絵"]),
    ("pilot namiki maki-e", "118888", ["パイロット蒔絵", "maki-e pen"]),
    # A-rank: High margin + niche
    ("japanese woodblock print ukiyo-e", "360", ["浮世絵", "木版画", "ukiyo-e"]),
    ("japanese scroll painting kakejiku", "36280", ["掛軸", "kakejiku", "掛け軸"]),
    ("japanese tea ceremony chawan", "36280", ["茶碗", "抹茶碗", "茶道具"]),
    ("shakuhachi flute japan", "10181", ["尺八", "shakuhachi"]),
    ("koto japanese instrument", "10179", ["琴", "koto"]),
    ("shamisen japanese", "10179", ["三味線", "shamisen"]),
    # B-rank: Stable high value
    ("shimano reel japan", "36147", ["シマノ リール", "Shimano reel"]),
    ("daiwa reel japan", "36147", ["ダイワ リール", "Daiwa reel"]),
    ("seiko vintage watch japan", "31387", ["セイコー 腕時計", "Seiko watch"]),
    ("orient watch japan", "31387", ["オリエント 腕時計", "Orient watch"]),
    ("sailor fountain pen", "118888", ["セーラー万年筆", "Sailor pen"]),
    ("pilot fountain pen japan", "118888", ["パイロット万年筆", "Pilot pen"]),
    ("platinum fountain pen", "118888", ["プラチナ万年筆", "Platinum pen"]),
    ("mamiya camera japan", "15230", ["マミヤ カメラ", "Mamiya"]),
    ("olympus camera japan", "15230", ["オリンパス カメラ", "Olympus"]),
    # Japanese crafts & collectibles
    ("japanese samurai sword tsuba", "36280", ["鍔", "tsuba"]),
    ("japanese netsuke", "36280", ["根付", "netsuke"]),
    ("japanese inro", "36280", ["印籠", "inro"]),
    ("japanese iron kettle tetsubin", "36280", ["鉄瓶", "南部鉄器", "tetsubin"]),
    ("japanese lacquerware", "36280", ["漆器", "蒔絵", "lacquerware"]),
    ("japanese bonsai tools", "118856", ["盆栽 道具", "bonsai tools"]),
    # Japanese tools
    ("japanese plane kanna woodworking", "13889", ["鉋", "カンナ", "kanna"]),
    ("japanese chisel nomi", "13889", ["鑿", "ノミ", "chisel"]),
    ("japanese sharpening stone whetstone", "20759", ["砥石", "whetstone"]),
    # High-end audio (not in main scan)
    ("luxman amplifier japan", "175735", ["ラックスマン", "Luxman"]),
    ("accuphase amplifier", "175735", ["アキュフェーズ", "Accuphase"]),
    ("sansui amplifier vintage", "175735", ["サンスイ", "Sansui"]),
    ("nakamichi cassette deck", "175737", ["ナカミチ", "Nakamichi"]),
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
                    # Use master's search_query format if available
                    try:
                        from auto_sourcing import _load_master_index

                        midx = _load_master_index()
                        m = midx["by_brand_model"].get(
                            (grp["brand"].lower(), grp["model"].lower())
                        )
                        search_q = (
                            m["search_query"]
                            if m
                            else f"{grp['brand']} {grp['model']}".strip()
                        )
                    except Exception:
                        search_q = f"{grp['brand']} {grp['model']}".strip()

                    await db.execute(
                        """
                        INSERT INTO demand_items
                        (search_query, brand, model, category_id, avg_price_usd,
                         sold_count, demand_score, condition_typical, jp_search_terms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(search_query, brand, model) DO UPDATE SET
                            avg_price_usd = excluded.avg_price_usd,
                            sold_count = excluded.sold_count,
                            demand_score = excluded.demand_score,
                            last_updated = CURRENT_TIMESTAMP
                    """,
                        (
                            search_q,
                            grp["brand"],
                            grp["model"],
                            cat_id,
                            round(avg_price, 2),
                            sold_count,
                            round(demand_score, 1),
                            condition,
                            json.dumps(jp_terms, ensure_ascii=False),
                        ),
                    )
                    count += 1
                await db.commit()

            logger.info(
                f"Demand scan: '{query}' → {len(brand_model_groups)} groups, {total} total on eBay"
            )

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
            await db.execute(
                """
                INSERT INTO demand_items
                (search_query, brand, model, category_id, avg_price_usd,
                 sold_count, demand_score, jp_search_terms)
                VALUES (?, ?, ?, '', ?, 1, 50, '[]')
                ON CONFLICT(search_query, brand, model) DO UPDATE SET
                    demand_score = demand_score + 20,
                    sold_count = sold_count + 1,
                    last_updated = CURRENT_TIMESTAMP
            """,
                (search_q, brand, model, price_usd),
            )
            count += 1
        await db.commit()

    logger.info(f"Own sales demand update: {count} items")

    # Also boost demand_score for all product_master items (our own listings)
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        boosted = await db.execute("""
            UPDATE demand_items SET demand_score = MAX(demand_score, 50)
            WHERE EXISTS (
                SELECT 1 FROM product_master p
                WHERE LOWER(p.brand) = LOWER(demand_items.brand)
                AND LOWER(p.model) = LOWER(demand_items.model)
            )
        """)
        await db.commit()
        logger.info(f"Product master demand boost applied")

    return count


async def collect_competitor_products(max_pages: int = 5):
    """Collect products from competitor sellers on eBay.

    Searches for products similar to ours that OTHER sellers are selling
    but we are NOT. These become discovery candidates.
    """
    try:
        search_ebay_discover, _ = _import_ebay_client()
    except (ImportError, Exception) as e:
        logger.warning(f"Cannot import ebay_core for competitor scan: {e}")
        return 0

    # Get our own listings for exclusion
    from auto_sourcing import _load_master_index

    master_idx = _load_master_index()
    our_models = set()
    for brand_l, model_l in master_idx["by_brand_model"]:
        our_models.add((brand_l, model_l))

    # Search categories we're active in, looking for products we don't have
    competitor_queries = [
        "vintage synthesizer japan",
        "guitar effects pedal japan",
        "DJ controller japan",
        "turntable japan",
        "amplifier receiver japan",
        "cassette recorder japan",
        "drum machine japan",
        "sampler groovebox japan",
        "electric guitar japan fender",
        "electric guitar japan ibanez",
        "bass guitar japan",
        "keyboard workstation japan yamaha",
        "minidisc player japan",
        "reel to reel japan",
    ]

    count = 0
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        for query in competitor_queries[:max_pages]:
            try:
                result = search_ebay_discover(query=query, limit=30)
                items = result.get("items", [])

                for item in items:
                    title = item.get("title", "")
                    price = item.get("price", 0)
                    if price < 50:
                        continue

                    brand, model = _extract_brand_model(title)
                    if not brand or not model:
                        continue

                    # Skip if we already sell this
                    if (brand.lower(), model.lower()) in our_models:
                        continue

                    # Use master search_query format if available
                    m = master_idx["by_brand_model"].get((brand.lower(), model.lower()))
                    search_q = m["search_query"] if m else f"{brand} {model}".strip()

                    jp_terms = json.dumps([search_q], ensure_ascii=False)
                    await db.execute(
                        """
                        INSERT INTO demand_items
                        (search_query, brand, model, avg_price_usd, demand_score,
                         jp_search_terms, active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(search_query, brand, model) DO UPDATE SET
                            demand_score = MAX(demand_score, excluded.demand_score),
                            last_updated = CURRENT_TIMESTAMP
                    """,
                        (search_q, brand, model, price, 3, jp_terms),
                    )
                    count += 1

                await db.commit()
            except Exception as e:
                logger.error(f"Competitor scan error for '{query}': {e}")
                continue

    logger.info(f"Competitor products found: {count} new items")
    return count


# ── Discovery Scanner ────────────────────────────────────


async def run_discovery_scan(max_items: int = 30):
    """Scan Japanese marketplaces using demand DB keywords.

    Picks top-demand items, searches JP marketplaces, evaluates profit.
    """
    from scrapers import ALL_SCRAPERS
    from auto_sourcing import ACCESSORY_KEYWORDS, _matches_reject_pattern

    # Get demand items — mix top-scored + random for broader coverage
    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Top half by score, bottom half random
        half = max_items // 2
        top = await db.execute_fetchall(
            """
            SELECT * FROM demand_items WHERE active = 1
            ORDER BY demand_score DESC LIMIT ?
        """,
            (half,),
        )
        rand = await db.execute_fetchall(
            """
            SELECT * FROM demand_items WHERE active = 1
            ORDER BY RANDOM() LIMIT ?
        """,
            (max_items - half,),
        )
        # Merge and deduplicate
        seen = set()
        demand_items = []
        for row in list(top) + list(rand):
            d = dict(row)
            if d["id"] not in seen:
                seen.add(d["id"])
                demand_items.append(d)

    if not demand_items:
        logger.info("No demand items to scan")
        return 0

    import asyncio

    candidates_found = 0
    MAX_NOTIFY_PER_PRODUCT = 3  # Only notify top 3 cheapest per brand+model

    # Build list of existing eBay listings to exclude from discovery
    # These should be handled by auto_sourcing (仕入れ候補), not discovery (新規出品候補)
    existing_ebay_tokens = []  # list of token sets
    existing_ebay_titles = []  # raw titles for fallback matching
    try:
        import sqlite3 as _sqlite3
        from auto_sourcing import AGENT_DB, _extract_model_tokens

        if os.path.exists(AGENT_DB):
            _conn = _sqlite3.connect(AGENT_DB)
            _rows = _conn.execute("SELECT title FROM listings").fetchall()
            _conn.close()
            for (_title,) in _rows:
                existing_ebay_titles.append(_title.lower())
                tokens = _extract_model_tokens(_title)
                if tokens:
                    existing_ebay_tokens.append(tokens)
            logger.info(
                f"Excluding {len(existing_ebay_titles)} existing eBay products from discovery"
            )
    except Exception as e:
        logger.warning(f"Could not load eBay listings for exclusion: {e}")

    # Also load product_master for precise eBay lookup
    from auto_sourcing import _load_master_index

    master_idx = _load_master_index()

    def _is_on_ebay(search_query: str, brand: str, model: str) -> bool:
        """Check if this product already exists on eBay."""
        # 1. Product master check (most precise)
        master = master_idx["by_brand_model"].get((brand.lower(), model.lower()))
        if master and master.get("ebay_sku"):
            return True  # Has SKU = definitely on eBay

        # 2. Brand+model string match in eBay titles
        brand_l = brand.lower()
        model_l = model.lower()
        if brand_l and model_l and len(model_l) >= 2:
            for title in existing_ebay_titles:
                if brand_l in title and model_l in title:
                    return True

        # 3. Token-based subset match (fallback)
        from auto_sourcing import _extract_model_tokens

        demand_tokens = _extract_model_tokens(search_query)
        if demand_tokens:
            for ebay_tokens in existing_ebay_tokens:
                if demand_tokens.issubset(ebay_tokens):
                    return True

        return False

    for demand in demand_items:
        search_query = demand["search_query"]
        avg_price_usd = demand.get("avg_price_usd", 0)
        if avg_price_usd < 30:
            continue

        brand = demand.get("brand", "")
        model = demand.get("model", "")

        # Skip generic model names that match unrelated products (e.g. "Icon", "Net", "80", "Model")
        GENERIC_MODELS = {
            "icon",
            "net",
            "80",
            "model",
            "modèle",
        }
        if model.lower() in GENERIC_MODELS:
            logger.debug(f"Skipping generic model name: {brand} {model}")
            continue

        # Skip if this product already exists on eBay (handled by auto_sourcing)
        if _is_on_ebay(search_query, brand, model):
            continue

        # Get exchange rate
        rate = _get_exchange_rate()

        # Calculate max purchase price (in JPY) that would still be profitable
        effective_rate = rate * (1 - PAYONEER_FX_MARGIN)
        total_fee = EBAY_FEE_RATE + PAYONEER_FEE_RATE + PROMOTED_RATE + TARIFF_RATE
        max_purchase = (
            avg_price_usd * (1 - total_fee) * effective_rate
            - INTL_SHIPPING_JPY
            - dw_config.AUTO_SOURCE_MIN_PROFIT
        )

        if max_purchase <= 0:
            continue

        # Search Japanese marketplaces
        tasks = [scraper.search(search_query) for scraper in ALL_SCRAPERS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all valid candidates for this demand item, then sort by price
        demand_candidates = []

        for scraper, result in zip(ALL_SCRAPERS, results):
            if isinstance(result, Exception):
                continue

            for item in result:
                price = item.price or 0
                if price <= 0 or price > max_purchase:
                    continue

                title_lower = item.title.lower()

                # Model verification: use master data if available, else token fallback
                demand_brand = demand.get("brand", "").lower()
                demand_model = demand.get("model", "").lower()
                master = master_idx["by_brand_model"].get((demand_brand, demand_model))

                if master:
                    # Master-based: model string must appear in source title
                    if master["model"].lower() not in title_lower:
                        continue
                    if master["search_mode"] == "brand_model":
                        if master["brand"].lower() not in title_lower:
                            continue
                else:
                    # Fallback: token-based matching
                    if demand_brand and demand_brand not in title_lower:
                        continue
                    if demand_model and len(demand_model) >= 2:
                        from auto_sourcing import _extract_model_tokens

                        source_tokens = _extract_model_tokens(item.title)
                        demand_tokens = _extract_model_tokens(
                            f"{demand_brand} {demand_model}"
                        )
                        if demand_tokens and not demand_tokens.issubset(source_tokens):
                            continue

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
                        (item.url,),
                    )
                    if await cur.fetchone():
                        continue

                # Calculate estimated profit
                est_profit = _calc_profit(avg_price_usd, price, rate, title=item.title)
                if est_profit < dw_config.AUTO_SOURCE_MIN_PROFIT:
                    continue

                demand_candidates.append(
                    {
                        "item": item,
                        "price": price,
                        "condition": condition,
                        "est_profit": est_profit,
                    }
                )

        # Sort by price ascending (cheapest first) and process
        demand_candidates.sort(key=lambda x: x["price"])
        notified_count = 0

        for dc in demand_candidates:
            item = dc["item"]
            price = dc["price"]
            condition = dc["condition"]
            est_profit = dc["est_profit"]

            # Check description for junk keywords (only for top candidates to save time)
            if notified_count < MAX_NOTIFY_PER_PRODUCT:
                from auto_sourcing import check_description_junk

                is_junk, _ = await check_description_junk(item.url)
                if is_junk:
                    continue

            # Image similarity check (pHash) — skip if images don't match
            if item.image_url and notified_count < MAX_NOTIFY_PER_PRODUCT:
                try:
                    from image_compare import compare_product_images

                    ebay_img_url = demand.get("image_url", "")
                    if ebay_img_url:
                        similar = await compare_product_images(
                            ebay_img_url, item.image_url
                        )
                        if not similar:
                            logger.info(
                                f"Image mismatch: {item.title[:40]} vs {demand_brand} {demand_model}"
                            )
                            continue
                except ImportError:
                    pass
                except Exception as e:
                    logger.debug(f"Image compare error: {e}")

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

            # Only notify top 3 cheapest per product, save the rest silently
            if notified_count < MAX_NOTIFY_PER_PRODUCT:
                await _notify_discovery_candidate(candidate, cid)
                notified_count += 1

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
    cache_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".eship_profit_cache.json"
    )
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


def _calc_profit(
    ebay_price_usd: float,
    purchase_price_jpy: int,
    rate: float,
    shipping_jpy: int = 0,
    title: str = "",
) -> int:
    """Calculate estimated profit in JPY (matching eShip calculation).

    Accounts for: eBay FVF, Payoneer fee, Promoted rate, tariff, Payoneer FX margin, shipping.
    """
    total_fee_rate = EBAY_FEE_RATE + PAYONEER_FEE_RATE + PROMOTED_RATE + TARIFF_RATE
    effective_rate = rate * (1 - PAYONEER_FX_MARGIN)
    gross_jpy = ebay_price_usd * (1 - total_fee_rate) * effective_rate
    ship = shipping_jpy if shipping_jpy > 0 else _estimate_shipping(title=title)
    profit = gross_jpy - purchase_price_jpy - ship
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
    price_for_profit = (purchase_price_jpy + shipping_jpy + min_profit_jpy) / (
        net_rate * rate
    )

    # Price to achieve minimum margin
    # margin = profit / (price_usd * rate)
    # Solving: price_usd = (purchase + shipping) / (rate * (net_rate - margin))
    denom = rate * (net_rate - min_margin)
    price_for_margin = (
        (purchase_price_jpy + shipping_jpy) / denom if denom > 0 else price_for_profit
    )

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
    "akai",
    "roland",
    "korg",
    "yamaha",
    "boss",
    "tascam",
    "technics",
    "pioneer",
    "denon",
    "marantz",
    "sony",
    "panasonic",
    "jbl",
    "bose",
    "sennheiser",
    "shure",
    "audio-technica",
    "behringer",
    "moog",
    "sequential",
    "oberheim",
    "emu",
    "ensoniq",
    "casio",
    "fostex",
    "toa",
    "teac",
    "nakamichi",
    "accuphase",
    "luxman",
    "mcintosh",
    "fender",
    "gibson",
    "ibanez",
    "esp",
    "digitech",
    "line6",
    "line 6",
    "eventide",
    "tc electronic",
    "zoom",
    "alesis",
    "ampeg",
    "mesa boogie",
    "marshall",
    "vox",
    "orange",
    "peavey",
    "crown",
    "dbx",
    "lexicon",
    "teenage engineering",
    "elektron",
    "arturia",
    "novation",
    "dave smith",
    "nord",
    "kurzweil",
    "access",
    "waldorf",
    "clavia",
}


# Words that are NOT brands (common adjectives/descriptors/nouns in eBay titles)
_NOT_BRANDS = {
    # Adjectives
    "vintage",
    "antique",
    "rare",
    "used",
    "new",
    "working",
    "tested",
    "japan",
    "japanese",
    "original",
    "authentic",
    "genuine",
    "classic",
    "professional",
    "portable",
    "digital",
    "analog",
    "analogue",
    "electric",
    "electronic",
    "acoustic",
    "stereo",
    "mono",
    "mini",
    "micro",
    "pro",
    "custom",
    "limited",
    "edition",
    "special",
    "premium",
    "deluxe",
    "lot",
    "set",
    "bundle",
    "pair",
    "old",
    "retro",
    "modern",
    "small",
    "large",
    "big",
    "fine",
    "great",
    "nice",
    "good",
    "beautiful",
    "handmade",
    "carved",
    "signed",
    "painted",
    "engraved",
    "gilded",
    # Common nouns (not brands)
    "iron",
    "steel",
    "bronze",
    "brass",
    "copper",
    "silver",
    "gold",
    "wood",
    "boxwood",
    "ivory",
    "bone",
    "lacquer",
    "ceramic",
    "porcelain",
    "clay",
    "sword",
    "blade",
    "katana",
    "tsuba",
    "fuchi",
    "kashira",
    "menuki",
    "netsuke",
    "inro",
    "ojime",
    "sagemono",
    "okimono",
    "toggle",
    "samurai",
    "warrior",
    "dragon",
    "tiger",
    "crane",
    "flower",
    "bamboo",
    "edo",
    "meiji",
    "taisho",
    "showa",
    "period",
    "century",
    "era",
    "fuzz",
    "pedal",
    "guitar",
    "bass",
    "keyboard",
    "drum",
    "mixer",
    "amplifier",
    "speaker",
    "microphone",
    "cable",
    "adapter",
    "figure",
    "statue",
    "mask",
    "armor",
    "helmet",
    "plate",
    "bowl",
    "vase",
    "box",
    "case",
    "stand",
    "holder",
    "mount",
    "rack",
    "emu",
    "donner",
    "modtone",
    "sonicake",  # too generic/cheap brands
    "m-vave",
}


def _extract_brand_model(title: str) -> tuple:
    """Extract brand and model from an eBay title.

    Priority:
    1. Match against product_master (authoritative Excel data)
    2. Fallback to heuristic extraction

    Returns (brand, model) tuple. Brand is empty if not found.
    """
    title_lower = title.lower()

    # 1. Try product_master lookup first (most accurate)
    try:
        from auto_sourcing import _load_master_index

        master_idx = _load_master_index()
        # Check each master entry: does its brand+model appear in this title?
        best_match = None
        best_model_len = 0
        for (brand_l, model_l), master in master_idx["by_brand_model"].items():
            if brand_l in title_lower and model_l in title_lower:
                # Prefer longer model matches (more specific)
                if len(model_l) > best_model_len:
                    best_match = master
                    best_model_len = len(model_l)
        if best_match:
            return best_match["brand"], best_match["model"]
    except Exception:
        pass

    # 2. Fallback: heuristic extraction
    brand = ""
    for b in _BRANDS:
        if b in title_lower:
            brand = b.title()
            break

    if not brand:
        words = title.split()
        for w in words:
            if w.lower() not in _NOT_BRANDS and len(w) >= 2 and w[0].isupper():
                brand = w
                break

    if brand.lower() in _NOT_BRANDS:
        return "", ""

    model = ""
    tokens = re.findall(
        r"[A-Za-z0-9]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|[A-Za-z0-9]+", title
    )
    for token in tokens:
        if token.lower() == brand.lower():
            continue
        if re.search(r"\d", token) and len(token) >= 2:
            model = token
            break

    if not model:
        return "", ""

    return brand, model


# ── eBay Listing Template ─────────────────────────────────

CONDITION_DESCRIPTION = (
    "This item has been tested and confirmed to be in basic working order. "
    "It is a used item, but overall it is in relatively good condition for its age.\n"
    "There may be minor signs of use such as small scratches, scuffs, or slight wear "
    "consistent with normal use. Please check the photos carefully, as they are part of "
    "the description. If you have any questions, feel free to contact me."
)

LISTING_TEMPLATE = """<div style="border: 1px solid #000; border-radius: 5px; margin: 0 auto; width: 100%; padding: 0 20px 10px; background: #fff; box-sizing: border-box; word-break: break-word;">

  <h1 style="font-size: 26px; margin: 30px 0; text-align: center; color: #000; font-weight: bold;">{title}</h1>

  <section>
    <h2 style="margin: 0 0 10px 0; background-color: #3565f2; color: #fff; font-size: 22px; line-height: 1.2; text-align: left; padding: 10px 20px; font-weight: bold;">Description</h2>
    <div>
      <p style="line-height: 24px; font-size: 18px; margin: 0 0 20px 0; color: #333; text-align: left;">
        {description}
      </p>
    </div>
  </section>

  <aside>
    <div>
      <h2 style="margin: 0 0 10px 0; background-color: #3565f2; color: #fff; font-size: 22px; line-height: 1.2; text-align: left; padding: 10px 20px; font-weight: bold;">Shipping</h2>
      <p style="line-height: 24px; font-size: 18px; margin: 0 0 20px 0; color: #333; text-align: left;">We will ship by DHL or FedEx or UPS or Japan Post</p>
    </div>

    <div>
      <h2 style="margin: 0 0 10px 0; background-color: #3565f2; color: #fff; font-size: 22px; line-height: 1.2; text-align: left; padding: 10px 20px; font-weight: bold;">International Buyers - Please Note:</h2>
      <p><strong>1. Buyers in the United States</strong><br>
Import duties and taxes are already included in the item price and shipping cost. You do not need to pay any additional customs duties, so please feel confident when making your purchase.</p><p><strong>2. Buyers outside the United States</strong><br>
Import duties and taxes are not included in the item price or shipping cost. Please check with your country's customs office to determine these additional costs prior to bidding or buying.<br>
We are flexible with pricing, so please feel free to contact us for consultation.</p><p><strong>3. Remote Area Deliveries</strong><br>
If the delivery address is in a remote area, additional charges may be applied by FedEx or DHL. In such cases, you may be asked to pay an additional fee of approximately USD 15-20. Thank you for your understanding.</p>
    </div>
  </aside>

</div>"""


def _apply_listing_template(title: str, description_html: str) -> str:
    """Apply the eBay listing HTML template with title and AI-generated description.

    description_html can be either:
    - Rich HTML from AI (with <br>, <b>, emojis, 【】) — used as-is
    - Plain text — converted to HTML with <br>
    """
    # If description has no HTML tags, convert newlines to <br>
    if "<br>" not in description_html and "<b>" not in description_html:
        description_html = description_html.replace("\n", "<br>\n")
    return LISTING_TEMPLATE.format(title=title, description=description_html)


# ── Candidate Management ─────────────────────────────────


async def _save_discovery_candidate(candidate: dict) -> str:
    """Save discovery candidate to DB and return UUID."""
    import uuid

    cid = str(uuid.uuid4())[:8]
    try:
        async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO discovery_candidates
                (id, demand_item_id, source_platform, source_title, source_price,
                 source_url, source_image_url, source_condition,
                 ebay_est_price_usd, est_profit_jpy, brand, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    cid,
                    candidate["demand_item_id"],
                    candidate["source_platform"],
                    candidate["source_title"],
                    candidate["source_price"],
                    candidate["source_url"],
                    candidate.get("source_image_url", ""),
                    candidate.get("source_condition", ""),
                    candidate["ebay_est_price_usd"],
                    candidate["est_profit_jpy"],
                    candidate.get("brand", ""),
                    candidate.get("model", ""),
                ),
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save discovery candidate: {e}")
    return cid


async def _notify_discovery_candidate(candidate: dict, cid: str):
    """Send LINE Flex Message for a new discovery candidate."""
    from notifier import notify_line_flex, PLATFORM_LABELS

    platform_label = PLATFORM_LABELS.get(
        candidate["source_platform"], candidate["source_platform"]
    )
    profit = candidate["est_profit_jpy"]
    price = candidate["source_price"]
    ebay_usd = candidate["ebay_est_price_usd"]
    brand = candidate.get("brand", "")
    model = candidate.get("model", "")
    product_name = f"{brand} {model}".strip() or candidate["source_title"][:40]

    base_url = f"https://dw.trustlink-tk.com"
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
                    {
                        "type": "text",
                        "text": "新規出品候補",
                        "weight": "bold",
                        "size": "md",
                        "color": "#0066FF",
                    },
                    {
                        "type": "text",
                        "text": product_name[:50],
                        "size": "sm",
                        "wrap": True,
                        "weight": "bold",
                    },
                    {
                        "type": "text",
                        "text": candidate["source_title"][:60],
                        "size": "xs",
                        "color": "#888888",
                        "wrap": True,
                    },
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "仕入れ",
                                "size": "sm",
                                "color": "#555555",
                                "flex": 0,
                            },
                            {
                                "type": "text",
                                "text": f"¥{price:,} ({platform_label})",
                                "size": "sm",
                                "align": "end",
                            },
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "eBay相場",
                                "size": "sm",
                                "color": "#555555",
                                "flex": 0,
                            },
                            {
                                "type": "text",
                                "text": f"${ebay_usd:,.0f}",
                                "size": "sm",
                                "align": "end",
                            },
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "見込み利益",
                                "size": "sm",
                                "color": "#555555",
                                "flex": 0,
                            },
                            {
                                "type": "text",
                                "text": f"¥{profit:,}",
                                "size": "sm",
                                "weight": "bold",
                                "color": "#1DB446",
                                "align": "end",
                            },
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "状態",
                                "size": "sm",
                                "color": "#555555",
                                "flex": 0,
                            },
                            {
                                "type": "text",
                                "text": candidate.get("source_condition", "不明"),
                                "size": "sm",
                                "align": "end",
                            },
                        ],
                    },
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#0066FF",
                                "action": {
                                    "type": "uri",
                                    "label": "出品する",
                                    "uri": approve_url,
                                },
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "action": {
                                    "type": "uri",
                                    "label": "商品を見る",
                                    "uri": candidate["source_url"],
                                },
                            },
                        ],
                    },
                    {
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "color": "#e74c3c",
                        "action": {
                            "type": "uri",
                            "label": "見送り（理由を入力）",
                            "uri": reject_url,
                        },
                    },
                ],
            },
        },
    )
    logger.info(f"Discovery candidate: {product_name} ¥{price:,} → 利益¥{profit:,}")


# ── White-Background Image Processing ──────────────────


def _referer_for(image_url: str) -> str:
    """フリマサイト画像URLに必要な Referer を返す。"""
    url = (image_url or "").lower()
    if "auctions.c.yimg.jp" in url or "auctions.yahoo" in url:
        return "https://auctions.yahoo.co.jp/"
    if "mercdn.net" in url or "mercari" in url:
        return "https://jp.mercari.com/"
    if "paypayfleamarket" in url or "paypay-pf" in url:
        return "https://paypayfleamarket.yahoo.co.jp/"
    if "fril.jp" in url or "rakuma" in url:
        return "https://fril.jp/"
    if "rakuten" in url:
        return "https://item.rakuten.co.jp/"
    if "hardoff" in url or "netmall" in url:
        return "https://netmall.hardoff.co.jp/"
    if "ebayimg.com" in url:
        return "https://www.ebay.com/"
    return ""


def _apply_white_bg_photoroom(image_url: str) -> Optional[bytes]:
    """Photoroom APIで背景除去 → 白背景合成 → JPEG bytes を返す。

    PHOTOROOM_API_KEY が未設定 or API失敗時は None を返す（呼び元でフォールバック）。
    """
    import io
    import requests as _req
    from PIL import Image

    api_key = os.environ.get("PHOTOROOM_API_KEY", "")
    if not api_key:
        logger.warning("PHOTOROOM_API_KEY not set — white-bg disabled")
        return None

    try:
        # Download source image with proper Referer for フリマサイト
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        ref = _referer_for(image_url)
        if ref:
            headers["Referer"] = ref
        dl = _req.get(image_url, timeout=20, headers=headers)
        if dl.status_code != 200:
            logger.warning(
                f"Image download failed {dl.status_code} for {image_url[:120]}"
            )
            return None
        src_bytes = dl.content
        if len(src_bytes) < 1024:
            logger.warning(
                f"Image too small ({len(src_bytes)} bytes) — likely error page: {image_url[:120]}"
            )
            return None

        # Call Photoroom segment API (returns transparent PNG)
        resp = _req.post(
            "https://sdk.photoroom.com/v1/segment",
            headers={"x-api-key": api_key, "Accept": "image/png"},
            files={"image_file": ("image.png", io.BytesIO(src_bytes), "image/png")},
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning(f"Photoroom API error {resp.status_code}: {resp.text[:200]}")
            return None

        # Composite transparent PNG onto white canvas → JPEG
        rgba = Image.open(io.BytesIO(resp.content)).convert("RGBA")

        # Crop to subject bounding box with small margin
        bbox = rgba.split()[3].getbbox()
        if bbox:
            w, h = rgba.size
            margin = int(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.06)
            x1, y1 = max(0, bbox[0] - margin), max(0, bbox[1] - margin)
            x2, y2 = min(w, bbox[2] + margin), min(h, bbox[3] + margin)
            rgba = rgba.crop((x1, y1, x2, y2))

        # Pad to 1:1 square
        sw, sh = rgba.size
        side = max(sw, sh)
        padded = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        padded.paste(rgba, ((side - sw) // 2, (side - sh) // 2), rgba)

        # Enforce eBay minimum (500px) — upscale small images to 800px
        if side < 800:
            padded = padded.resize((800, 800), Image.LANCZOS)
        # Limit to 2000px (eBay max before auto-downscale)
        elif side > 2000:
            padded = padded.resize((2000, 2000), Image.LANCZOS)

        # Composite onto white
        canvas = Image.new("RGB", padded.size, (255, 255, 255))
        canvas.paste(padded, (0, 0), padded.split()[3])

        out = io.BytesIO()
        canvas.save(out, format="JPEG", quality=92, optimize=True)
        logger.info("White-bg processed successfully")
        return out.getvalue()

    except Exception as e:
        logger.warning(f"White-bg processing failed: {e}")
        return None


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
            logger.info(
                f"Scraped source: {len(description_jp)} chars, {len(image_urls_list)} images"
            )

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

        # Generate SKU: roki + YYMMDD + HHMM
        from datetime import datetime as _dt

        _now = _dt.now()
        sku = f"roki{_now.strftime('%y%m%d%H%M')}"

        # Step 2: Create eBay listing via Trading API (eShip compatible)
        _import_ebay_client()
        from ebay_core.client import add_fixed_price_item, suggest_category
        from ebay_core.client import (
            add_to_promoted_listing,
            set_store_category,
            _guess_store_category_id,
        )

        title = listing_data.get("title", "") or product_name
        if isinstance(listing_data.get("titles"), list) and listing_data["titles"]:
            title = listing_data["titles"][0].get("title", title)
        # eBay title max 80 characters
        if len(title) > 80:
            title = title[:77].rsplit(" ", 1)[0]

        # Get AI-generated description (already HTML with emojis, <br>, <b>, 【】)
        ai_description = listing_data.get("description_html", "") or listing_data.get(
            "description", ""
        )
        description = _apply_listing_template(title, ai_description)

        # Build item specifics
        raw_specs = listing_data.get("specs", {})
        aspects = {}
        for k, v in raw_specs.items():
            vals = v if isinstance(v, list) else [str(v)]
            aspects[k] = [val[:65] for val in vals]
        if "UPC" not in aspects:
            aspects["UPC"] = ["Does Not Apply"]
        if "EAN" not in aspects:
            aspects["EAN"] = ["Does Not Apply"]

        category_id = listing_data.get("category_id", "") or candidate.get(
            "category_id", ""
        )
        if not category_id:
            cat_query_parts = []
            for key in ("Brand", "brand", "MPN", "Model", "model", "Type", "type"):
                val = raw_specs.get(key, "")
                if val and str(val).lower() not in (
                    "unbranded",
                    "does not apply",
                    "n/a",
                    "",
                ):
                    cat_query_parts.append(str(val))
            cat_suggestion = listing_data.get("category_suggestion", "")
            if cat_suggestion:
                cat_query_parts.append(cat_suggestion)
            cat_query = " ".join(cat_query_parts) if cat_query_parts else title
            logger.info(f"Category query: '{cat_query}' (from specs)")
            category_id = suggest_category(cat_query)

        # Use ALL images from source listing (up to 24)
        image_urls = (
            image_urls_list[:24]
            if image_urls_list
            else [candidate.get("source_image_url", "")]
        )
        image_urls = [u for u in image_urls if u]
        logger.info(f"Listing images: {len(image_urls)} photos")

        # White-background processing: apply to ALL images, upload to eBay hosting
        if image_urls:
            from ebay_core.client import upload_picture_to_ebay

            eps_urls = []
            for i, orig_url in enumerate(image_urls[:10]):
                wb_bytes = _apply_white_bg_photoroom(orig_url)
                if wb_bytes:
                    fname = "white_bg.jpg" if i == 0 else f"white_bg_{i}.jpg"
                    eps_url = upload_picture_to_ebay(wb_bytes, fname)
                    if eps_url:
                        eps_urls.append(eps_url)
                        continue
                    logger.warning(f"White-bg EPS upload failed for img {i}")

                # White-bg failed for this image — upload original to EPS as fallback
                # (must be EPS — mixing self-hosted + EPS is prohibited)
                try:
                    import requests as _requests

                    img_resp = _requests.get(
                        orig_url,
                        timeout=15,
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Referer": _referer_for(orig_url),
                        },
                    )
                    img_resp.raise_for_status()
                    eps_url = upload_picture_to_ebay(img_resp.content, f"img_{i}.jpg")
                    if eps_url:
                        eps_urls.append(eps_url)
                except Exception as e:
                    logger.warning(f"Fallback original upload failed (img {i}): {e}")

            if eps_urls:
                image_urls = eps_urls
                white_bg_count = sum(
                    1 for u in eps_urls if "white_bg" in str(u).lower() or True
                )  # all EPS now
                logger.info(
                    f"Images uploaded to EPS: {len(eps_urls)} total "
                    f"(white-bg processed: target {min(len(image_urls), 10)})"
                )
            else:
                logger.warning("All image processing failed — using original URLs")

        ebay_price = candidate.get("ebay_est_price_usd", 0)
        dims = listing_data.get("dimensions_cm", {})

        # Trading API: AddFixedPriceItem with auto-fix retry
        listing_id = ""
        for attempt in range(5):
            result = add_fixed_price_item(
                title=title,
                description_html=description,
                category_id=category_id or "38071",  # fallback: Musical Instruments
                price_usd=ebay_price,
                condition_id=3000,  # Used
                condition_description=CONDITION_DESCRIPTION,
                image_urls=image_urls,
                item_specifics=aspects,
                sku=sku,
                quantity=0,  # Out of stock (draft-like)
            )

            if result.get("success"):
                listing_id = result.get("item_id", "")
                logger.info(
                    f"Trading API listing created (attempt {attempt + 1}): ItemID={listing_id}"
                )

                # Promoted Listing
                add_to_promoted_listing(listing_id, 2.0)

                # Store category
                store_cat = _guess_store_category_id(title, description)
                if store_cat:
                    set_store_category(listing_id, store_cat)
                break

            # Auto-fix errors
            error_text = result.get("error", "")
            # Clean encoding artifacts (Â, Â\xa0, etc.)
            error_text = (
                error_text.replace("\u00c2", "").replace("\u00a0", " ").replace("Â", "")
            )
            logger.info(
                f"Trading API error (attempt {attempt + 1}): {error_text[:300]}"
            )

            # Fix: missing item specifics
            if "is missing" in error_text.lower():
                import re as _re

                _missing = _re.findall(
                    r"item specific ([\w\s/&]+?) is missing", error_text, _re.IGNORECASE
                )
                if not _missing:
                    _missing = _re.findall(r"\"([\w\s/&]+?)\" is missing", error_text)
                if _missing:
                    for field in _missing:
                        aspects[field.strip()] = ["N/A"]
                        logger.info(f"Auto-fix: added missing aspect '{field.strip()}'")
                    continue

            # Fix: value too long
            if (
                "too long" in error_text.lower()
                or "too many characters" in error_text.lower()
            ):
                import re as _re

                _long = _re.findall(r"([\w\s/&]+?)'s value", error_text)
                if _long:
                    for f in _long:
                        f = f.strip()
                        if f in aspects:
                            aspects[f] = [v[:65] for v in aspects[f]]
                            logger.info(f"Auto-fix: trimmed aspect '{f}'")
                    continue

            # Fix: invalid category
            if "category" in error_text.lower() and (
                "invalid" in error_text.lower() or "not valid" in error_text.lower()
            ):
                new_cat = suggest_category(title)
                if new_cat and new_cat != category_id:
                    logger.info(f"Auto-fix: category {category_id} → {new_cat}")
                    category_id = new_cat
                    continue

            # Fix: item specifics renamed by eBay — progressively strip specs and retry
            if (
                "item specific" in error_text.lower()
                and "renamed" in error_text.lower()
            ):
                if aspects:
                    logger.info(
                        "Auto-fix: stripped all item specifics, retrying with empty set"
                    )
                    aspects = {}
                    continue

            logger.error(f"Trading API failed (unknown): {error_text[:200]}")
            break

        ebay_ok = bool(listing_id)
        if not listing_id:
            logger.error(f"All listing attempts failed for {sku}")

        if ebay_ok:
            # Step 3: Register on eShip as background task (only when eBay succeeded)
            from eship import create_eship_item

            eship_title = listing_data.get("title", "") or product_name
            if isinstance(listing_data.get("titles"), list) and listing_data["titles"]:
                eship_title = listing_data["titles"][0].get("title", eship_title)

            # Build eShip params for background task
            eship_params = {
                "title": eship_title,
                "supplier_url": candidate["source_url"],
                "purchase_price": candidate["source_price"],
                "platform": candidate["source_platform"],
                "selling_price_usd": candidate.get("ebay_est_price_usd", 0),
                "sku": sku,
                "ebay_item_id": listing_id,
                "condition": condition,
                "condition_description": quality.get("condition_notes_en", ""),
                "image_url": image_urls_list[0]
                if image_urls_list
                else candidate.get("source_image_url", ""),
                "category_id": category_id,
                "height_cm": dims.get("height", 0),
                "length_cm": dims.get("length", 0),
                "width_cm": dims.get("width", 0),
                "memo": product_name[:200],
            }

            async def _register_eship_background(params, cid):
                """Background task: register on eShip and update DB + notify."""
                try:
                    result = await create_eship_item(**params)
                    ok = result.get("status") == "ok"
                    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db2:
                        await db2.execute(
                            "UPDATE discovery_candidates SET eship_registered = ? WHERE id = ?",
                            (1 if ok else 0, cid),
                        )
                        await db2.commit()
                    if ok:
                        logger.info(
                            f"eShip background: registered {params['title'][:40]}"
                        )
                    else:
                        logger.warning(
                            f"eShip background failed: {result.get('message', '')}"
                        )
                        # Notify via Telegram
                        from notifier import notify_telegram_text

                        await notify_telegram_text(
                            f"⚠️ eShip登録失敗: {params['title'][:30]}\n/listings で手動登録してください"
                        )
                except Exception as e:
                    logger.error(f"eShip background error: {e}")
                    from notifier import notify_telegram_text

                    await notify_telegram_text(
                        f"⚠️ eShip登録失敗: {params['title'][:30]}\n{str(e)[:50]}"
                    )

            # Launch eShip registration in background (don't wait)
            asyncio.create_task(_register_eship_background(eship_params, candidate_id))
            logger.info(f"eShip registration queued in background for {sku}")
        else:
            logger.warning(
                f"Skipping eShip registration: eBay listing failed for {sku}"
            )

        # Mark as listed based on eBay result (eShip will update async)
        new_status = "listed" if ebay_ok else "error"

        async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
            await db.execute(
                """
                UPDATE discovery_candidates
                SET status = ?, ebay_listing_id = ?
                WHERE id = ?
            """,
                (new_status, listing_id or "", candidate_id),
            )
            await db.commit()

        if not ebay_ok:
            return {
                "status": "error",
                "message": f"eBay出品失敗: Trading API error (see logs)",
            }

        return {
            "status": "ok",
            "sku": sku,
            "title": title,
            "offer_id": "",
            "listing_id": listing_id,
            "ebay_created": bool(listing_id),
            "eship_registered": "processing",  # Background task
            "ebay_registered": ebay_ok,
            "eship_inventory_id": "",
            "listing_data": {
                "description_preview": description[:200],
                "specs_count": len(aspects),
            },
        }

    except Exception as e:
        logger.error(f"Auto-listing pipeline error: {e}")
        return {"status": "error", "message": str(e)}


async def create_eship_item_from_candidate(candidate_id: str) -> bool:
    """Retry eShip registration for a discovery candidate. Returns True on success."""
    import aiosqlite
    from eship import create_eship_item

    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)
        )
        row = await cur.fetchone()

    if not row:
        logger.error(f"eShip retry: candidate not found: {candidate_id}")
        return False

    candidate = dict(row)
    brand = candidate.get("brand", "")
    model = candidate.get("model", "")
    product_name = f"{brand} {model}".strip()
    ebay_item_id = candidate.get("ebay_listing_id") or str(int(time.time()))

    params = {
        "title": product_name,
        "supplier_url": candidate.get("source_url", ""),
        "purchase_price": candidate.get("source_price", 0),
        "platform": candidate.get("source_platform", ""),
        "selling_price_usd": candidate.get("ebay_est_price_usd", 0),
        "sku": candidate.get("sku", f"roki{candidate_id[:8]}"),
        "ebay_item_id": ebay_item_id,
        "condition": candidate.get("source_condition", "Used"),
        "condition_description": "",
        "image_url": candidate.get("source_image_url", ""),
        "category_id": candidate.get("category_id", ""),
        "height_cm": 0,
        "length_cm": 0,
        "width_cm": 0,
        "memo": product_name[:200],
    }

    try:
        result = await create_eship_item(**params)
        ok = result.get("status") == "ok"
        async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE discovery_candidates SET eship_registered = ? WHERE id = ?",
                (1 if ok else 0, candidate_id),
            )
            await db.commit()
        return ok
    except Exception as e:
        logger.error(f"create_eship_item_from_candidate error [{candidate_id}]: {e}")
        return False


async def apply_white_bg_to_ebay_listing(
    item_id: str, source_listing_url: str = ""
) -> dict:
    """eBay出品の画像を白背景EPS化して差し替える共通関数。

    source_listing_url がある場合:
      → 仕入れ元ページをスクレイピングして画像を取得（eBay既存画像は破棄）
    ない場合:
      → GetItem でeBay既存画像を取得して1枚目を白背景化
    """
    import requests as _req
    from ebay_core.client import (
        get_item_pictures,
        revise_fixed_price_item_pictures,
        upload_picture_to_ebay,
    )

    if not item_id:
        return {"status": "error", "message": "eBay ItemID が指定されていません"}

    # 画像ソースの決定
    if source_listing_url:
        # 仕入れ元ページをスクレイピング
        from scrapers.detail import scrape_detail

        detail = await scrape_detail(source_listing_url)
        source_imgs = detail.image_urls if detail and detail.image_urls else []
        if not source_imgs:
            return {
                "status": "error",
                "message": f"仕入れ元ページから画像を取得できませんでした: {source_listing_url}",
            }
        logger.info(f"Scraped {len(source_imgs)} images from {source_listing_url}")
    else:
        # eBay既存画像を使用（discovery_candidates フロー用）
        source_imgs = get_item_pictures(item_id)
        if not source_imgs:
            return {"status": "error", "message": "処理対象の画像URLが見つかりません"}

    # 全画像を白背景処理してEPSアップロード（最大10枚）
    eps_urls = []
    for i, url in enumerate(source_imgs[:10]):
        wb = _apply_white_bg_photoroom(url)
        if not wb:
            logger.warning(f"White-bg failed for img {i}, skipping: {url}")
            continue
        fname = "white_bg.jpg" if i == 0 else f"white_bg_{i}.jpg"
        u = upload_picture_to_ebay(wb, fname)
        if u:
            eps_urls.append(u)
        else:
            logger.warning(f"EPS upload failed for img {i}")

    if not eps_urls:
        return {
            "status": "error",
            "message": "白背景処理・EPSアップロードがすべて失敗しました",
        }

    revised = revise_fixed_price_item_pictures(item_id, eps_urls)
    if not revised:
        return {
            "status": "error",
            "message": "eBay 画像更新（ReviseFixedPriceItem）に失敗しました",
        }

    logger.info(
        f"Images updated for item {item_id}: {len(eps_urls)} EPS pics from {'source' if source_listing_url else 'ebay'}"
    )
    return {"status": "ok", "item_id": item_id, "pics_count": len(eps_urls)}


async def create_ebay_listing_from_rare_candidate(cid: str) -> dict:
    """Full pipeline for a rare_candidates row: same as create_ebay_listing_from_candidate.

    Scrapes source URL → runs agent team → creates eBay listing → registers eShip (bg).
    """
    import aiosqlite

    async with aiosqlite.connect(dw_config.DATABASE_PATH) as _db:
        _db.row_factory = aiosqlite.Row
        cur = await _db.execute("SELECT * FROM rare_candidates WHERE id = ?", (cid,))
        row = await cur.fetchone()

    if not row:
        return {"status": "error", "message": "候補が見つかりません"}

    c = dict(row)
    product_name = c["title"]
    purchase_price_jpy = c.get("price_jpy") or 0
    source_url = c["url"]
    source_platform = c.get("platform", "")
    condition = "Used"

    try:
        # Step 0: Scrape source listing
        from scrapers.detail import scrape_detail

        detail = await scrape_detail(source_url)
        description_jp = ""
        image_urls_list = []
        if detail:
            description_jp = detail.description
            image_urls_list = detail.image_urls
            if detail.condition:
                condition = detail.condition

        # Step 1: Agent team (research + quality + pricing + listing)
        from agents import run_agent_team

        team_result = await run_agent_team(
            product_name=product_name,
            purchase_price_jpy=purchase_price_jpy,
            condition=condition,
            description_jp=description_jp,
            image_urls=image_urls_list
            or ([c["image_url"]] if c.get("image_url") else []),
        )
        listing_data = team_result["listing"]
        quality = team_result.get("quality", {})
        ebay_price = team_result["pricing"].get("price_usd", 0) or (
            (c.get("demand_usd_max") or 0) * 0.85
        )

        # SKU: roki + YYMMDDHHM
        from datetime import datetime as _dt

        sku = f"roki{_dt.now().strftime('%y%m%d%H%M')}"

        # Step 2: Create eBay listing via Trading API
        _import_ebay_client()
        from ebay_core.client import add_fixed_price_item, suggest_category
        from ebay_core.client import (
            add_to_promoted_listing,
            set_store_category,
            _guess_store_category_id,
        )

        title = listing_data.get("title", "") or product_name
        if isinstance(listing_data.get("titles"), list) and listing_data["titles"]:
            title = listing_data["titles"][0].get("title", title)
        if len(title) > 80:
            title = title[:77].rsplit(" ", 1)[0]

        ai_description = listing_data.get("description_html", "") or listing_data.get(
            "description", ""
        )
        description = _apply_listing_template(title, ai_description)

        raw_specs = listing_data.get("specs", {})
        aspects: dict = {}
        for k, v in raw_specs.items():
            vals = v if isinstance(v, list) else [str(v)]
            aspects[k] = [val[:65] for val in vals]
        aspects.setdefault("UPC", ["Does Not Apply"])
        aspects.setdefault("EAN", ["Does Not Apply"])

        category_id = listing_data.get("category_id", "")
        if not category_id:
            cat_query = listing_data.get("category_suggestion", "") or title
            category_id = suggest_category(cat_query)

        image_urls = (
            image_urls_list[:24]
            if image_urls_list
            else ([c["image_url"]] if c.get("image_url") else [])
        )
        image_urls = [u for u in image_urls if u]

        # White-background processing
        if image_urls:
            from ebay_core.client import upload_picture_to_ebay

            eps_urls = []
            for i, orig_url in enumerate(image_urls[:10]):
                wb_bytes = _apply_white_bg_photoroom(orig_url)
                if wb_bytes:
                    fname = "white_bg.jpg" if i == 0 else f"white_bg_{i}.jpg"
                    eps_url = upload_picture_to_ebay(wb_bytes, fname)
                    if eps_url:
                        eps_urls.append(eps_url)
                        continue
                try:
                    import requests as _requests

                    img_resp = _requests.get(
                        orig_url,
                        timeout=15,
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Referer": _referer_for(orig_url),
                        },
                    )
                    img_resp.raise_for_status()
                    eps_url = upload_picture_to_ebay(img_resp.content, f"img_{i}.jpg")
                    if eps_url:
                        eps_urls.append(eps_url)
                except Exception as _e:
                    logger.warning(f"Fallback upload failed (img {i}): {_e}")
            if eps_urls:
                image_urls = eps_urls

        dims = listing_data.get("dimensions_cm", {})
        listing_id = ""
        for attempt in range(5):
            result = add_fixed_price_item(
                title=title,
                description_html=description,
                category_id=category_id or "38071",
                price_usd=ebay_price,
                condition_id=3000,
                condition_description=CONDITION_DESCRIPTION,
                image_urls=image_urls,
                item_specifics=aspects,
                sku=sku,
                quantity=0,
            )
            if result.get("success"):
                listing_id = result.get("item_id", "")
                add_to_promoted_listing(listing_id, 2.0)
                store_cat = _guess_store_category_id(title, description)
                if store_cat:
                    set_store_category(listing_id, store_cat)
                break

            error_text = (
                result.get("error", "")
                .replace("Â", "")
                .replace(" ", " ")
                .replace("Â", "")
            )
            import re as _re

            if "is missing" in error_text.lower():
                missing = _re.findall(
                    r"item specific ([\w\s/&]+?) is missing", error_text, _re.IGNORECASE
                ) or _re.findall(r'"([\w\s/&]+?)" is missing', error_text)
                for field in missing:
                    aspects[field.strip()] = ["N/A"]
                continue
            if (
                "too long" in error_text.lower()
                or "too many characters" in error_text.lower()
            ):
                for f in _re.findall(r"([\w\s/&]+?)'s value", error_text):
                    if f.strip() in aspects:
                        aspects[f.strip()] = [v[:65] for v in aspects[f.strip()]]
                continue
            if "category" in error_text.lower() and (
                "invalid" in error_text.lower() or "not valid" in error_text.lower()
            ):
                new_cat = suggest_category(title)
                if new_cat and new_cat != category_id:
                    category_id = new_cat
                    continue
            if (
                "item specific" in error_text.lower()
                and "renamed" in error_text.lower()
            ):
                aspects = {}
                continue
            break

        ebay_ok = bool(listing_id)

        # Step 3: eShip registration (background)
        if ebay_ok:
            from eship import create_eship_item

            eship_params = {
                "title": title,
                "supplier_url": source_url,
                "purchase_price": purchase_price_jpy,
                "platform": source_platform,
                "selling_price_usd": ebay_price,
                "sku": sku,
                "ebay_item_id": listing_id,
                "condition": condition,
                "condition_description": quality.get("condition_notes_en", ""),
                "image_url": image_urls_list[0]
                if image_urls_list
                else (c.get("image_url") or ""),
                "category_id": category_id,
                "height_cm": dims.get("height", 0),
                "length_cm": dims.get("length", 0),
                "width_cm": dims.get("width", 0),
                "memo": product_name[:200],
            }

            async def _bg_eship(params, _cid):
                try:
                    res = await create_eship_item(**params)
                    ok = res.get("status") == "ok"
                    if not ok:
                        from notifier import notify_telegram_text

                        await notify_telegram_text(
                            f"⚠️ eShip登録失敗(rare): {params['title'][:30]}\n{res.get('message', '')}"
                        )
                except Exception as _e:
                    from notifier import notify_telegram_text

                    await notify_telegram_text(
                        f"⚠️ eShip登録失敗(rare): {params['title'][:30]}\n{str(_e)[:50]}"
                    )

            asyncio.create_task(_bg_eship(eship_params, cid))

        # Update rare_candidates
        new_status = "listed" if ebay_ok else "error"
        async with aiosqlite.connect(dw_config.DATABASE_PATH) as _db2:
            await _db2.execute(
                "UPDATE rare_candidates SET status=?, ebay_listing_id=? WHERE id=?",
                (new_status, listing_id or "", cid),
            )
            await _db2.commit()

        if not ebay_ok:
            return {
                "status": "error",
                "message": "eBay出品失敗: Trading API error (see logs)",
            }

        return {
            "status": "ok",
            "sku": sku,
            "title": title,
            "listing_id": listing_id,
            "ebay_created": True,
            "eship_registered": "processing",
        }

    except Exception as _e:
        logger.error(f"Rare listing pipeline error: {_e}")
        return {"status": "error", "message": str(_e)}


async def update_ebay_images_white_bg(candidate_id: str) -> dict:
    """discovery_candidates の候補IDからeBay出品画像を白背景化して差し替える。"""
    import aiosqlite

    async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)
        )
        row = await cur.fetchone()

    if not row:
        return {"status": "error", "message": "候補が見つかりません"}

    candidate = dict(row)
    item_id = candidate.get("ebay_listing_id", "")
    if not item_id:
        return {"status": "error", "message": "eBay ItemID が未登録です"}

    # discovery_candidates はeBay既存画像を白背景化（source_listing_url なし）
    return await apply_white_bg_to_ebay_listing(item_id)
