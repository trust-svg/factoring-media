"""Auto-sourcing: evaluate new listings and send to eShip if profitable."""
import json
import logging
import os
import re
import time
from typing import Optional, Tuple

import config

logger = logging.getLogger(__name__)

# Path to eShip profit cache (written by eship.py)
_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".eship_profit_cache.json")
# Path to agent.db for eBay listing data — use local copy in service dir (avoids macOS sandbox)
AGENT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebay_agent.db")
if not os.path.exists(AGENT_DB):
    AGENT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ebay-agent", "agent.db")
if not os.path.exists(AGENT_DB):
    AGENT_DB = os.path.expanduser("~/Desktop/Claude Workspace/products/ebay-agent/agent.db")

# Platforms where price may be a low starting bid (auctions)
AUCTION_PLATFORMS = {"yahoo_auction"}

# Rejection reason labels (Japanese)
REJECT_REASONS = {
    "price_zero": "価格情報なし",
    "max_price": "仕入れ上限超過",
    "accessory": "アクセサリー/部品",
    "no_ebay_match": "eBayに該当商品なし",
    "no_model_token": "型番抽出不可",
    "no_model_match": "型番不一致",
    "in_stock": "eBay在庫あり",
    "no_eship_data": "eShipデータなし",
    "no_profit_data": "利益データ不完全",
    "price_ratio": "価格差異が大きい",
    "low_profit": "利益不足",
    "junk_description": "説明文にジャンク/不良記載",
    "user_rejected": "過去の見送りに該当",
}

# Words indicating parts/accessories — not the main product
ACCESSORY_KEYWORDS = {
    # Japanese
    "ゴム脚", "ゴムマット", "マット", "ケーブル", "アダプター", "アダプタ",
    "電源コード", "リモコン", "説明書", "取説", "マニュアル", "カバー",
    "ケース", "バッグ", "リュック", "ソフトケース", "ハードケース",
    "金具", "ラックイヤー", "ラックマウント", "パッドセンサー", "センサー",
    "ノブ", "フェーダー", "ツマミ", "ボタン", "キャップ", "フット",
    "取り外し", "から取り", "部品", "パーツ", "のみ", "だけ",
    "ジョグダイヤル", "キッチンマット", "ラグ", "カーペット",
    # English
    "rubber foot", "rubber feet", "rubber mat", "cable", "adapter",
    "power cord", "remote", "manual", "cover", "case", "bag",
    "rack ear", "rack mount", "pad sensor", "knob", "fader",
    "cap", "foot", "parts only", "decksaver",
}

# Words in description indicating junk/non-working items — should be excluded
JUNK_DESCRIPTION_KEYWORDS = {
    # Japanese
    "ジャンク", "通電のみ", "通電確認のみ", "動作未確認", "動作不良",
    "故障", "壊れ", "破損", "欠品あり", "不具合", "難あり",
    "部品取り", "現状渡し", "返品不可", "ノークレーム",
    "音が出ない", "音出ない", "電源入らない", "電源が入らない",
    "起動しない", "起動しません", "表示しない", "表示されない",
    "読み込まない", "読み込めない", "認識しない",
    "水没", "落下", "割れ", "ヒビ", "錆",
    # English
    "junk", "for parts", "not working", "as is", "no power",
    "does not turn on", "broken", "defective", "faulty",
    "no sound", "no display", "not tested",
}


async def check_description_junk(url: str) -> tuple:
    """Scrape listing page and check description for junk keywords.

    Returns (is_junk: bool, description: str)
    Only called for items that pass all other filters (to minimize scraping).
    """
    try:
        from scrapers.detail import scrape_detail
        detail = await scrape_detail(url)
        if not detail or not detail.description:
            return False, ""

        desc_lower = detail.description.lower()
        for kw in JUNK_DESCRIPTION_KEYWORDS:
            if kw.lower() in desc_lower:
                logger.info(f"Junk keyword '{kw}' found in description: {url}")
                return True, detail.description
        return False, detail.description
    except Exception as e:
        logger.warning(f"Description check failed for {url}: {e}")
        return False, ""


def _load_eship_cache() -> dict:
    """Load eShip profit cache."""
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r") as f:
                data = json.load(f)
            if time.time() - data.get("ts", 0) < 7200:  # 2hr validity for auto-sourcing
                return data.get("profits", {})
    except Exception:
        pass
    return {}


def _normalize_model(text: str) -> str:
    """Normalize model strings: collapse spaces, unify MK variations.
    Expects already-lowercased input.
    """
    t = text.strip()
    # "414 mkii" → "414mkii", "414 mk2" → "414mk2"
    t = re.sub(r'\s+(mk)', r'\1', t)
    # "porta 02" → "porta02", "porta 1" → "porta1"
    t = re.sub(r'(porta)\s+', r'\1', t)
    # "portastudio 424" → "portastudio424" (keep number attached)
    t = re.sub(r'(portastudio)\s+(\d)', r'\1\2', t)
    return t


# Number words → digit mapping for model names (Porta One, Porta Two, etc.)
_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "dos": "2", "tres": "3",  # Spanish
    "un": "1", "deux": "2",   # French
}


def _extract_model_tokens(text: str) -> set:
    """Extract model-number-like tokens from a title.

    Model tokens are alphanumeric strings that contain at least one digit,
    e.g. "MPC2000XL", "424", "GT-1B", "DP-900M2", "Porta02".
    Also handles:
    - Hyphenated models: "GT-1B" as a single token
    - Spaced models: "Porta 02" → "porta02", "414 MKII" → "414mkii"
    - Number words: "Porta One" → "porta1", "Porta Two" → "porta2"
    """
    t = text.lower().strip()

    # Replace number words with digits BEFORE normalization: "Porta One" → "Porta 1"
    for word, digit in _NUMBER_WORDS.items():
        t = re.sub(r'\b' + word + r'\b', digit, t)

    # Normalize: collapse spaces around model parts
    t = _normalize_model(t)

    # Find hyphenated tokens (e.g. "gt-1b", "dp-900m2")
    hyphenated = re.findall(r'[a-z0-9]+-[a-z0-9]+(?:-[a-z0-9]+)*', t)
    # Find standalone alphanumeric tokens
    words = re.findall(r'[a-z0-9]+', t)

    tokens = set()
    for w in hyphenated + words:
        # Must contain at least one digit to be a model number
        if re.search(r'\d', w) and len(w) >= 2:
            tokens.add(w)

    # Also generate concatenated pairs for "porta 05" → "porta05" patterns
    word_list = re.findall(r'[a-z]+|\d+', t)
    for i in range(len(word_list) - 1):
        a, b = word_list[i], word_list[i + 1]
        combined = a + b
        if re.search(r'[a-z]', combined) and re.search(r'\d', combined) and len(combined) >= 3:
            tokens.add(combined)

    # Standalone 3+ digit numbers are likely model numbers (424, 488, 464, etc.)
    for w in re.findall(r'\d{3,}', t):
        tokens.add(w)

    return tokens


def _get_ebay_matches(keyword: str) -> list:
    """Find ALL matching eBay listings for a keyword.

    Returns list of {title, listing_id, sku, price_usd, quantity} dicts.
    """
    import sqlite3
    if not os.path.exists(AGENT_DB):
        return []

    conn = sqlite3.connect(AGENT_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT sku, listing_id, title, price_usd, quantity FROM listings").fetchall()
    conn.close()

    kw_words = keyword.lower().split()
    matches = []
    for row in rows:
        title = (row["title"] or "").lower()
        if all(w in title for w in kw_words):
            matches.append(dict(row))
    return matches


def _find_best_ebay_match(listing_title: str, ebay_candidates: list) -> Optional[dict]:
    """Find the best eBay listing match for a specific deal-watcher listing title.

    Uses model-number token matching for precision.
    A candidate must share at least one model token with the listing title.
    Among matches, the one with the most shared model tokens wins.
    """
    listing_tokens = _extract_model_tokens(listing_title)

    if not listing_tokens:
        # No model numbers in listing title — can't match precisely
        return None

    best = None
    best_score = 0
    for ebay in ebay_candidates:
        ebay_tokens = _extract_model_tokens(ebay["title"] or "")
        shared = listing_tokens & ebay_tokens
        if shared:
            score = len(shared)
            if score > best_score:
                best_score = score
                best = ebay
    return best


# In-memory cache for reject patterns (refreshed each scan cycle)
_reject_patterns_cache = {"ts": 0, "patterns": []}


def _load_reject_patterns() -> list:
    """Load user-rejected patterns from DB. Cached for 5 minutes."""
    import sqlite3
    if time.time() - _reject_patterns_cache["ts"] < 300:
        return _reject_patterns_cache["patterns"]

    patterns = []
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        # Load from both eship_candidates and discovery_candidates
        for table in ("eship_candidates", "discovery_candidates"):
            try:
                rows = conn.execute(f"""
                    SELECT reject_keywords FROM {table}
                    WHERE status = 'rejected' AND reject_keywords IS NOT NULL AND reject_keywords != ''
                """).fetchall()
                for row in rows:
                    kws = [w.strip().lower() for w in row["reject_keywords"].split(",") if w.strip()]
                    if kws:
                        patterns.append(kws)
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    _reject_patterns_cache["ts"] = time.time()
    _reject_patterns_cache["patterns"] = patterns
    return patterns


def _matches_reject_pattern(title: str) -> bool:
    """Check if a listing title matches any user-rejected patterns."""
    patterns = _load_reject_patterns()
    if not patterns:
        return False
    title_lower = title.lower()
    for kws in patterns:
        if all(kw in title_lower for kw in kws):
            return True
    return False


async def evaluate_listing(keyword_name: str, listing: dict) -> Tuple[Optional[dict], str]:
    """Evaluate a single new listing for auto-sourcing.

    Returns:
        (candidate_dict, reason_code) — candidate is None if rejected.
    """
    price = listing.get("price") or 0
    if price <= 0:
        return None, "price_zero"

    platform = listing.get("platform", "")
    is_auction = platform in AUCTION_PLATFORMS
    listing_title = listing.get("title", "")

    # Check against user-rejected patterns (learned from feedback)
    if _matches_reject_pattern(listing_title):
        return None, "user_rejected"

    if not is_auction and price > config.AUTO_SOURCE_MAX_PRICE:
        return None, "max_price"

    title_lower = listing_title.lower()
    for kw in ACCESSORY_KEYWORDS:
        if kw.lower() in title_lower:
            return None, "accessory"

    ebay_candidates = _get_ebay_matches(keyword_name)
    if not ebay_candidates:
        return None, "no_ebay_match"

    listing_tokens = _extract_model_tokens(listing_title)
    if not listing_tokens:
        return None, "no_model_token"

    ebay = _find_best_ebay_match(listing_title, ebay_candidates)
    if not ebay:
        return None, "no_model_match"

    if (ebay.get("quantity") or 0) > 0:
        return None, "in_stock"

    eship_cache = _load_eship_cache()
    lid = str(ebay.get("listing_id", ""))
    sku = ebay.get("sku", "")
    eship = eship_cache.get(lid) or eship_cache.get(sku)
    if not eship:
        return None, "no_eship_data"

    base_profit = eship.get("profit", 0)
    eship_pp = eship.get("purchase_price", 0)

    if not base_profit or not eship_pp:
        return None, "no_profit_data"

    if not is_auction and eship_pp > 0:
        ratio = price / eship_pp
        if ratio < 0.3 or ratio > 2.0:
            return None, "price_ratio"

    adjusted_profit = base_profit + (eship_pp - price)

    if adjusted_profit < config.AUTO_SOURCE_MIN_PROFIT:
        return None, "low_profit"

    # Check description for junk keywords (scrape detail page)
    source_url = listing.get("url", "")
    if source_url:
        is_junk, _ = await check_description_junk(source_url)
        if is_junk:
            return None, "junk_description"

    return {
        "action": config.AUTO_SOURCE_MODE,
        "profit_jpy": round(adjusted_profit),
        "listing_price": price,
        "ebay_title": ebay["title"],
        "ebay_price_usd": ebay["price_usd"],
        "sku": sku,
        "listing_id": lid,
        "platform": platform,
        "url": listing.get("url", ""),
        "reason": f"利益¥{adjusted_profit:,.0f} (仕入¥{price:,})",
    }, "candidate"


async def process_candidate(candidate: dict, listing_db_id: int):
    """Process an auto-sourcing candidate: notify or auto-execute.

    Args:
        candidate: Result from evaluate_listing()
        listing_db_id: The deal-watcher listing ID
    """
    from notifier import PLATFORM_LABELS

    platform_label = PLATFORM_LABELS.get(candidate["platform"], candidate["platform"])
    profit = candidate["profit_jpy"]
    price = candidate["listing_price"]

    if candidate["action"] == "auto":
        # Auto-execute: send to eShip
        from eship import update_eship_item
        result = await update_eship_item(
            ebay_title=candidate["ebay_title"],
            supplier_url=candidate["url"],
            purchase_price=price,
            platform=candidate["platform"],
            set_quantity=1,
            sku=candidate["sku"],
        )

        if result.get("status") == "ok":
            # Update agent.db quantity
            _update_agent_qty(candidate["ebay_title"])

            # LINE notification: auto-sourced
            await _notify_auto_sourced(candidate, platform_label)
            logger.info(f"Auto-sourced: {candidate['ebay_title'][:40]} ¥{price:,} → 利益¥{profit:,}")
        else:
            # Failed - notify as candidate instead
            await _notify_candidate(candidate, platform_label)
            logger.warning(f"Auto-source failed: {result.get('message')}")

    elif candidate["action"] == "notify":
        # Notify only
        await _notify_candidate(candidate, platform_label)
        logger.info(f"Candidate notified: {candidate['ebay_title'][:40]} ¥{price:,} → 利益¥{profit:,}")


async def _save_candidate(candidate: dict) -> str:
    """Save candidate to DB and return its UUID."""
    import uuid
    import aiosqlite
    cid = str(uuid.uuid4())[:8]
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO eship_candidates
                (id, ebay_title, ebay_price_usd, sku, listing_id,
                 source_url, source_price, source_platform, profit_jpy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, candidate["ebay_title"], candidate.get("ebay_price_usd", 0),
                candidate.get("sku", ""), candidate.get("listing_id", ""),
                candidate.get("url", ""), candidate["listing_price"],
                candidate.get("platform", ""), candidate["profit_jpy"],
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save candidate: {e}")
    return cid


async def _notify_candidate(candidate: dict, platform_label: str):
    """Send LINE Flex Message with eShip registration button."""
    from notifier import notify_line_flex
    profit = candidate["profit_jpy"]
    price = candidate["listing_price"]
    ebay_usd = candidate.get("ebay_price_usd", 0)

    # Save to DB for one-tap registration
    cid = await _save_candidate(candidate)
    base_url = f"http://192.168.68.57:{config.PORT}"
    register_url = f"{base_url}/eship/register/{cid}"
    reject_url = f"{base_url}/candidate/reject/{cid}"

    await notify_line_flex(
        alt_text=f"仕入れ候補: {candidate['ebay_title'][:30]} 利益¥{profit:,}",
        contents={
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "仕入れ候補発見", "weight": "bold", "size": "md", "color": "#1DB446"},
                    {"type": "text", "text": candidate["ebay_title"][:50], "size": "sm", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
                        {"type": "text", "text": "仕入れ", "size": "sm", "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"¥{price:,} ({platform_label})", "size": "sm", "align": "end"},
                    ]},
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "eBay", "size": "sm", "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"${ebay_usd:,.0f}", "size": "sm", "align": "end"},
                    ]},
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "見込み利益", "size": "sm", "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"¥{profit:,}", "size": "sm", "weight": "bold",
                         "color": "#1DB446", "align": "end"},
                    ]},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446",
                         "action": {"type": "uri", "label": "eShip登録", "uri": register_url}},
                        {"type": "button", "style": "secondary",
                         "action": {"type": "uri", "label": "商品を見る", "uri": candidate["url"]}},
                    ]},
                    {"type": "button", "style": "link", "height": "sm", "color": "#e74c3c",
                     "action": {"type": "uri", "label": "見送り（理由を入力）", "uri": reject_url}},
                ],
            },
        },
    )


async def _notify_auto_sourced(candidate: dict, platform_label: str):
    """Send LINE notification for an auto-sourced item."""
    from notifier import notify_line_message
    profit = candidate["profit_jpy"]
    price = candidate["listing_price"]

    msg = (
        f"✅ 自動仕入れ完了！\n"
        f"【{platform_label}】¥{price:,}\n"
        f"📦 {candidate['ebay_title'][:50]}\n"
        f"💰 見込み利益: ¥{profit:,}\n"
        f"🔗 {candidate['url']}"
    )
    await notify_line_message(msg)


async def save_non_candidate(listing: dict, reason_code: str) -> str:
    """Save a non-candidate listing for feedback and return its UUID."""
    import uuid
    import aiosqlite
    fid = str(uuid.uuid4())[:8]
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO learning_data
                (id, listing_title, listing_price, platform, url, rejection_reason)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                fid,
                listing.get("title", ""),
                listing.get("price", 0),
                listing.get("platform", ""),
                listing.get("url", ""),
                reason_code,
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save non-candidate: {e}")
    return fid


async def notify_non_candidate(listing: dict, reason_code: str):
    """Send LINE Flex notification for a non-candidate with feedback button."""
    from notifier import notify_line_flex, PLATFORM_LABELS

    platform_label = PLATFORM_LABELS.get(listing.get("platform", ""), listing.get("platform", ""))
    price = listing.get("price", 0)
    title = listing.get("title", "")
    reason_label = REJECT_REASONS.get(reason_code, reason_code)

    fid = await save_non_candidate(listing, reason_code)
    feedback_url = f"http://192.168.68.57:{config.PORT}/feedback/{fid}"

    await notify_line_flex(
        alt_text=f"新着: {title[:30]} ({reason_label})",
        contents={
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "新着商品", "weight": "bold", "size": "md", "color": "#888888"},
                    {"type": "text", "text": title[:50], "size": "sm", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
                        {"type": "text", "text": "価格", "size": "sm", "color": "#555555", "flex": 0},
                        {"type": "text", "text": f"¥{price:,} ({platform_label})" if price else "価格不明",
                         "size": "sm", "align": "end"},
                    ]},
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "判定", "size": "sm", "color": "#555555", "flex": 0},
                        {"type": "text", "text": reason_label, "size": "sm", "color": "#e74c3c", "align": "end"},
                    ]},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "color": "#f39c12",
                     "action": {"type": "uri", "label": "仕入れたい", "uri": feedback_url}},
                    {"type": "button", "style": "secondary",
                     "action": {"type": "uri", "label": "商品を見る", "uri": listing.get("url", "")}},
                ],
            },
        },
    )


def _update_agent_qty(ebay_title: str):
    """Update agent.db quantity to 1 after auto-sourcing."""
    import sqlite3
    try:
        conn = sqlite3.connect(AGENT_DB)
        conn.execute("UPDATE listings SET quantity = 1 WHERE title = ?", (ebay_title,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to update agent DB: {e}")
