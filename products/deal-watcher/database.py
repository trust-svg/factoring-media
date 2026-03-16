import os
import sqlite3
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
        await db.commit()


async def get_keywords(active_only=True):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cur = await db.execute("SELECT * FROM keywords WHERE active=1 ORDER BY name")
        else:
            cur = await db.execute("SELECT * FROM keywords ORDER BY name")
        return await cur.fetchall()


async def add_keyword(name: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO keywords (name) VALUES (?)", (name,))
        await db.commit()


async def toggle_keyword(keyword_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE keywords SET active = 1 - active WHERE id = ?", (keyword_id,))
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


async def save_listing(platform: str, external_id: str, title: str,
                       price, url: str, image_url,
                       keyword_id: int) -> bool:
    """Save listing. Returns True if newly inserted."""
    if await listing_exists(platform, external_id):
        return False
    async with aiosqlite.connect(DB) as db:
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
        cur = await db.execute("""
            SELECT l.*, k.name as keyword
            FROM listings l JOIN keywords k ON l.keyword_id = k.id
            ORDER BY l.found_at DESC LIMIT ?
        """, (limit,))
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
            cur2 = await db.execute(f"""
                SELECT l.* FROM listings l
                WHERE l.keyword_id = ? {hidden_filter}
                ORDER BY l.price ASC NULLS LAST
            """, (g["id"],))
            items = await cur2.fetchall()
            result.append({
                "keyword_id": g["id"],
                "keyword": g["name"],
                "count": g["listing_count"],
                "min_price": g["min_price"],
                "max_price": g["max_price"],
                "latest_found": g["latest_found"],
                "listings": [dict(i) for i in items],
            })
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
        await db.execute("UPDATE listings SET hidden = 1 WHERE keyword_id = ?", (keyword_id,))
        await db.commit()


async def get_hidden_count():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM listings WHERE COALESCE(hidden, 0) = 1")
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
    cur = conn.execute("SELECT sku, listing_id, title, price_usd, quantity FROM listings")
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
