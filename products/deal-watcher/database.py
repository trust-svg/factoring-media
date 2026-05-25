import os
import sqlite3
from typing import Optional
import aiosqlite
import config

DB = config.DATABASE_PATH
EBAY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebay_agent.db")


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                price INTEGER,
                url TEXT NOT NULL,
                image_url TEXT,
                keyword_id INTEGER NOT NULL,
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (keyword_id) REFERENCES keywords(id),
                UNIQUE(platform, external_id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_listings_found
            ON listings(found_at DESC)
        """)
        # Add hidden column if missing (for archive/sold-out)
        try:
            await db.execute("ALTER TABLE listings ADD COLUMN hidden INTEGER DEFAULT 0")
        except Exception:
            pass  # column already exists
        # Auto-sourcing candidates (for LINE one-tap eShip registration)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS eship_candidates (
                id TEXT PRIMARY KEY,
                ebay_title TEXT NOT NULL,
                ebay_price_usd REAL,
                sku TEXT,
                listing_id TEXT,
                source_url TEXT NOT NULL,
                source_price INTEGER,
                source_platform TEXT,
                profit_jpy INTEGER,
                status TEXT DEFAULT 'pending',
                reject_note TEXT,
                reject_keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add reject columns if missing (migration for existing DBs)
        for col in ("reject_note", "reject_keywords"):
            try:
                await db.execute(f"ALTER TABLE eship_candidates ADD COLUMN {col} TEXT")
            except Exception:
                pass
        # Learning data (feedback on non-candidate listings)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS learning_data (
                id TEXT PRIMARY KEY,
                listing_title TEXT NOT NULL,
                listing_price INTEGER,
                platform TEXT,
                url TEXT,
                rejection_reason TEXT,
                user_action TEXT DEFAULT 'pending',
                user_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Product master — authoritative brand/model reference from Excel
        await db.execute("""
            CREATE TABLE IF NOT EXISTS product_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                search_query TEXT NOT NULL,
                search_mode TEXT DEFAULT 'model_only',
                ebay_sku TEXT,
                ebay_listing_id TEXT,
                ebay_price_usd REAL,
                category TEXT,
                condition TEXT,
                active INTEGER DEFAULT 1,
                UNIQUE(brand, model)
            )
        """)
        # Add master_id to keywords (migration)
        try:
            await db.execute("ALTER TABLE keywords ADD COLUMN master_id INTEGER")
        except Exception:
            pass
        # Add OOS keyword metadata columns (Phase 1+2 integration)
        for col_def in (
            "source TEXT",
            "ebay_item_id TEXT",
            "ebay_price_usd REAL",
            "ebay_title TEXT",
        ):
            try:
                await db.execute(f"ALTER TABLE keywords ADD COLUMN {col_def}")
            except Exception:
                pass
        # Rare item keyword watchlist
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rare_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Rare item scanner candidates
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rare_candidates (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                price_jpy INTEGER,
                platform TEXT,
                url TEXT NOT NULL UNIQUE,
                image_url TEXT,
                genre TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add demand + AI score + listing columns to rare_candidates (migration)
        for col_def in (
            "ebay_query TEXT",
            "demand_usd_min REAL",
            "demand_usd_max REAL",
            "demand_listing_count INTEGER DEFAULT 0",
            "demand_has_sold INTEGER DEFAULT 0",
            "ai_approved INTEGER DEFAULT 1",
            "ai_reason TEXT",
            "ebay_listing_id TEXT",
        ):
            try:
                await db.execute(f"ALTER TABLE rare_candidates ADD COLUMN {col_def}")
            except Exception:
                pass
        # eBay demand result cache (24h TTL)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ebay_demand_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                min_usd REAL,
                max_usd REAL,
                listing_count INTEGER DEFAULT 0,
                has_sold INTEGER DEFAULT 0,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_demand_cache_query
            ON ebay_demand_cache(query, checked_at DESC)
        """)
        await db.commit()


async def get_rare_keywords(active_only: bool = False):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cur = await db.execute(
                "SELECT * FROM rare_keywords WHERE active=1 ORDER BY name"
            )
        else:
            cur = await db.execute("SELECT * FROM rare_keywords ORDER BY name")
        return await cur.fetchall()


async def add_rare_keyword(name: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO rare_keywords (name) VALUES (?)", (name.strip(),)
        )
        await db.commit()


async def toggle_rare_keyword(kid: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE rare_keywords SET active = 1 - active WHERE id = ?", (kid,)
        )
        await db.commit()


async def delete_rare_keyword(kid: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM rare_keywords WHERE id = ?", (kid,))
        await db.commit()


async def save_rare_candidate(
    id: str,
    title: str,
    price_jpy: int,
    platform: str,
    url: str,
    image_url: Optional[str],
    genre: str,
):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """INSERT OR IGNORE INTO rare_candidates
               (id, title, price_jpy, platform, url, image_url, genre)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, title, price_jpy, platform, url, image_url, genre),
        )
        await db.commit()


async def get_rare_candidate(cid: str) -> Optional[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM rare_candidates WHERE id = ?", (cid,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_rare_status(cid: str, status: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE rare_candidates SET status = ? WHERE id = ?", (status, cid)
        )
        await db.commit()


async def is_rare_url_seen(url: str) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT 1 FROM rare_candidates WHERE url = ?", (url,))
        return await cur.fetchone() is not None


async def get_demand_cache(query: str) -> Optional[dict]:
    """Return cached eBay demand result if checked within the last 24h."""
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM ebay_demand_cache
               WHERE query = ? AND checked_at > datetime('now', '-24 hours')
               ORDER BY checked_at DESC LIMIT 1""",
            (query,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def save_demand_cache(
    query: str,
    min_usd: Optional[float],
    max_usd: Optional[float],
    listing_count: int,
    has_sold: bool,
):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """INSERT INTO ebay_demand_cache (query, min_usd, max_usd, listing_count, has_sold)
               VALUES (?, ?, ?, ?, ?)""",
            (query, min_usd, max_usd, listing_count, int(has_sold)),
        )
        await db.commit()


async def record_candidate_demand(
    cid: str,
    ebay_query: str,
    demand_usd_min: Optional[float],
    demand_usd_max: Optional[float],
    demand_listing_count: int,
    demand_has_sold: bool,
):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """UPDATE rare_candidates
               SET ebay_query=?, demand_usd_min=?, demand_usd_max=?,
                   demand_listing_count=?, demand_has_sold=?
               WHERE id=?""",
            (
                ebay_query,
                demand_usd_min,
                demand_usd_max,
                demand_listing_count,
                int(demand_has_sold),
                cid,
            ),
        )
        await db.commit()


async def record_candidate_ai_score(cid: str, approved: bool, reason: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE rare_candidates SET ai_approved=?, ai_reason=? WHERE id=?",
            (int(approved), reason, cid),
        )
        await db.commit()


async def get_demand_stats() -> list:
    """Aggregated demand stats + user action rates per eBay query (for learning dashboard)."""
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT
                   ebay_query,
                   ROUND(AVG(demand_usd_max), 0) as avg_max_usd,
                   MAX(demand_usd_max)            as top_usd,
                   SUM(demand_has_sold)           as has_sold_count,
                   COUNT(CASE WHEN status='listed'    THEN 1 END) as listed,
                   COUNT(CASE WHEN status='eshipped'  THEN 1 END) as eshipped,
                   COUNT(CASE WHEN status='rejected'  THEN 1 END) as rejected,
                   COUNT(*)                       as total
               FROM rare_candidates
               WHERE ebay_query IS NOT NULL
               GROUP BY ebay_query
               ORDER BY avg_max_usd DESC""",
        )
        return await cur.fetchall()


async def get_keywords(active_only=True):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cur = await db.execute(
                "SELECT * FROM keywords WHERE active=1 ORDER BY name"
            )
        else:
            cur = await db.execute("SELECT * FROM keywords ORDER BY name")
        return await cur.fetchall()


async def add_oos_keyword(
    name: str, ebay_item_id: str, ebay_price_usd: float, ebay_title: str
) -> str:
    """Add or update an OOS (out-of-stock) keyword with direct eBay item metadata.

    Returns 'added', 'updated', or 'skipped'.
    """
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, ebay_item_id FROM keywords WHERE name=?", (name,)
        )
        existing = await cur.fetchone()
        if existing:
            if existing[1] == ebay_item_id:
                return "skipped"
            await db.execute(
                """UPDATE keywords
                   SET source='oos', ebay_item_id=?, ebay_price_usd=?, ebay_title=?, active=1
                   WHERE name=?""",
                (ebay_item_id, ebay_price_usd, ebay_title, name),
            )
            await db.commit()
            return "updated"
        else:
            await db.execute(
                """INSERT INTO keywords (name, source, ebay_item_id, ebay_price_usd, ebay_title, active)
                   VALUES (?, 'oos', ?, ?, ?, 1)""",
                (name, ebay_item_id, ebay_price_usd, ebay_title),
            )
            await db.commit()
            return "added"


async def add_keyword(name: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO keywords (name) VALUES (?)", (name,))
        await db.commit()


async def toggle_keyword(keyword_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE keywords SET active = 1 - active WHERE id = ?", (keyword_id,)
        )
        await db.commit()


async def delete_keyword(keyword_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
        await db.commit()


async def listing_exists(platform: str, external_id: str) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT 1 FROM listings WHERE platform=? AND external_id=?",
            (platform, external_id),
        )
        return await cur.fetchone() is not None


async def save_listing(
    platform: str,
    external_id: str,
    title: str,
    price,
    url: str,
    image_url,
    keyword_id: int,
) -> bool:
    """Save listing. Returns True if newly inserted OR price dropped significantly."""
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, price FROM listings WHERE platform=? AND external_id=?",
            (platform, external_id),
        )
        existing = await cur.fetchone()

        if existing:
            old_price = existing[1] or 0
            new_price = price or 0
            # Detect significant price drop (>10% decrease)
            if old_price > 0 and new_price > 0 and new_price < old_price * 0.9:
                await db.execute(
                    "UPDATE listings SET price=?, found_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_price, existing[0]),
                )
                await db.commit()
                return True  # Treat as "new" for auto-sourcing evaluation
            return False

        await db.execute(
            """INSERT OR IGNORE INTO listings
               (platform, external_id, title, price, url, image_url, keyword_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (platform, external_id, title, price, url, image_url, keyword_id),
        )
        await db.commit()
    return True


async def get_recent_listings(limit=100):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT l.*, k.name as keyword
            FROM listings l JOIN keywords k ON l.keyword_id = k.id
            ORDER BY l.found_at DESC LIMIT ?
        """,
            (limit,),
        )
        return await cur.fetchall()


async def get_grouped_listings(show_hidden=False):
    """Get listings grouped by keyword, with count and cheapest price."""
    hidden_filter = "" if show_hidden else "AND COALESCE(l.hidden, 0) = 0"
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(f"""
            SELECT k.id, k.name,
                   COUNT(l.id) as listing_count,
                   MIN(l.price) as min_price,
                   MAX(l.price) as max_price,
                   MAX(l.found_at) as latest_found
            FROM keywords k
            JOIN listings l ON l.keyword_id = k.id
            WHERE 1=1 {hidden_filter}
            GROUP BY k.id
            ORDER BY MAX(l.found_at) DESC
        """)
        groups = await cur.fetchall()

        result = []
        for g in groups:
            cur2 = await db.execute(
                f"""
                SELECT l.* FROM listings l
                WHERE l.keyword_id = ? {hidden_filter}
                ORDER BY l.price ASC NULLS LAST
            """,
                (g["id"],),
            )
            items = await cur2.fetchall()
            result.append(
                {
                    "keyword_id": g["id"],
                    "keyword": g["name"],
                    "count": g["listing_count"],
                    "min_price": g["min_price"],
                    "max_price": g["max_price"],
                    "latest_found": g["latest_found"],
                    "listings": [dict(i) for i in items],
                }
            )
        return result


async def hide_listing(listing_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE listings SET hidden = 1 WHERE id = ?", (listing_id,))
        await db.commit()


async def unhide_listing(listing_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE listings SET hidden = 0 WHERE id = ?", (listing_id,))
        await db.commit()


async def hide_keyword_listings(keyword_id: int):
    """Hide all listings for a keyword."""
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE listings SET hidden = 1 WHERE keyword_id = ?", (keyword_id,)
        )
        await db.commit()


async def get_hidden_count():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM listings WHERE COALESCE(hidden, 0) = 1"
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_keyword_count():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM keywords WHERE active=1")
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_listing_count():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM listings")
        row = await cur.fetchone()
        return row[0] if row else 0


def get_ebay_info():
    """Get eBay listing info (price, quantity, title) keyed by keyword-matching.
    Returns dict: keyword_lower -> {price_usd, quantity, title, sku, listing_id}
    """
    if not os.path.exists(EBAY_DB):
        return {}

    conn = sqlite3.connect(EBAY_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT sku, listing_id, title, price_usd, quantity FROM listings"
    )
    rows = cur.fetchall()
    conn.close()

    result = {}
    for row in rows:
        title = row["title"] or ""
        result[row["sku"]] = {
            "title": title,
            "title_lower": title.lower(),
            "price_usd": row["price_usd"],
            "quantity": row["quantity"],
            "sku": row["sku"],
            "listing_id": row["listing_id"],
        }
    return result


def match_ebay_keyword(keyword, ebay_data):
    """Find best matching eBay listing for a deal-watcher keyword."""
    kw_lower = keyword.lower()
    best = None
    best_score = 0

    for sku, info in ebay_data.items():
        title_lower = info["title_lower"]
        # Check if all keyword words appear in eBay title
        kw_words = kw_lower.split()
        if all(w in title_lower for w in kw_words):
            score = len(kw_words)
            if score > best_score:
                best_score = score
                best = info

    return best
