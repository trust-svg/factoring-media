"""eShip inventory scraper — returns reorder candidates without Playwright."""

import json
import logging
import os
import re
import time
from html.parser import HTMLParser

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CACHE_TTL = 1800  # 30 minutes
_CACHE_FILE = "/tmp/eship_reorder_cache.json"
BASE_URL = "https://eship-tool.com"


def _get_csrf_token(html: str) -> str:
    class _P(HTMLParser):
        token = ""

        def handle_starttag(self, tag, attrs):
            if tag == "input":
                d = dict(attrs)
                if d.get("name") == "authenticity_token":
                    self._P__class_token = d.get("value", "")

    # Simpler: just regex
    m = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login() -> requests.Session:
    from config import ESHIP_EMAIL, ESHIP_PASSWORD

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
    )
    r = session.get(f"{BASE_URL}/users/sign_in", timeout=20)
    token = _get_csrf_token(r.text)
    resp = session.post(
        f"{BASE_URL}/users/sign_in",
        data={
            "authenticity_token": token,
            "user[email]": ESHIP_EMAIL,
            "user[password]": ESHIP_PASSWORD,
            "commit": "ログイン",
        },
        allow_redirects=True,
        timeout=20,
    )
    if "/users/sign_in" in resp.url:
        raise RuntimeError("eShip login failed")
    return session


def _detect_platform(url: str) -> str:
    if "auctions.yahoo.co.jp" in url:
        return "ヤフオク"
    if "mercari.com" in url:
        return "メルカリ"
    if "paypayfleamarket" in url:
        return "Yahooフリマ"
    if "fril.jp" in url:
        return "ラクマ"
    if "amazon.co.jp" in url or "amazon.com" in url:
        return "Amazon"
    if "hardoff" in url:
        return "ハードオフ"
    if "suruga-ya" in url:
        return "駿河屋"
    return ""


def _scrape_all(session: requests.Session) -> tuple:
    sold_out: list = []
    unlisted: list = []
    page_num = 1

    while True:
        r = session.get(f"{BASE_URL}/inventories?page={page_num}", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            break
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else []
        if not rows:
            break

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            # Inventory ID (cell[0])
            id_inp = cells[0].find("input", {"name": "inventories[][id]"})
            if not id_inp:
                continue
            try:
                inv_id = int(id_inp.get("value", 0))
            except (ValueError, TypeError):
                continue

            # Image (cell[1] — thumbnail)
            img_tag = cells[1].find("img") if len(cells) > 1 else None
            image_url = img_tag.get("src", "") if img_tag else ""

            # Title (cell[2])
            title_raw = cells[2].get_text(strip=True)
            for suffix in ("出品中", "出品停止", "出品削除"):
                title_raw = title_raw.replace(suffix, "")
            title = title_raw.strip()

            # Sold count + quantity (cell[5])
            cell5_text = cells[5].get_text()
            sold_m = re.search(r"Sold(\d+)", cell5_text)
            sold = int(sold_m.group(1)) if sold_m else 0
            qty_inp = cells[5].find("input", {"name": "inventories[][quantity]"})
            qty = int(qty_inp.get("value", 0)) if qty_inp else 0

            # Purchase price (cell[7])
            pp_inp = cells[7].find("input", {"name": "inventories[][purchase_price]"})
            purchase_price = 0
            if pp_inp:
                try:
                    purchase_price = int(float(pp_inp.get("value", 0)))
                except (ValueError, TypeError):
                    pass

            # Supplier URL + platform (cell[6])
            url_inp = (
                cells[6].find("input", {"name": "inventories[][supplier_url]"})
                if len(cells) > 6
                else None
            )
            supplier_url = url_inp.get("value", "") if url_inp else ""
            platform = _detect_platform(supplier_url)

            # eBay selling price (cell[8])
            sp_inp = (
                cells[8].find("input", {"name": "inventories[][selling_price]"})
                if len(cells) > 8
                else None
            )
            selling_price_usd = 0.0
            if sp_inp:
                try:
                    selling_price_usd = float(sp_inp.get("value", 0))
                except (ValueError, TypeError):
                    pass

            item = {
                "id": inv_id,
                "eship_id": inv_id,
                "title": title,
                "purchase_price_jpy": purchase_price,
                "image_url": image_url,
                "platform": platform,
                "supplier_url": supplier_url,
                "sold_count": sold,
                "ebay_price_usd": selling_price_usd,
                "sold_at": None,
            }

            if qty >= 1:
                pass  # active listing — skip
            elif sold >= 1:
                item["category"] = "sold_out"
                sold_out.append(item)
            else:
                item["category"] = "unlisted"
                unlisted.append(item)

        next_link = soup.find("a", rel="next")
        if not next_link:
            break
        page_num += 1

    return sold_out, unlisted


def fetch_reorder_candidates(force: bool = False) -> dict:
    """Return dict with sold_out / unlisted lists and cached_at timestamp.

    Uses a 30-minute file cache to avoid hammering eShip on every page open.
    Pass force=True to bypass cache.
    """
    if not force:
        try:
            with open(_CACHE_FILE) as f:
                data = json.load(f)
            if time.time() - data.get("cached_at", 0) < CACHE_TTL:
                return data
        except Exception:
            pass

    try:
        session = _login()
        sold_out, unlisted = _scrape_all(session)
        result: dict = {
            "sold_out": sold_out,
            "unlisted": unlisted,
            "cached_at": time.time(),
        }
        with open(_CACHE_FILE, "w") as f:
            json.dump(result, f)
        logger.info(
            "eShip reorder candidates fetched: sold_out=%d unlisted=%d",
            len(sold_out),
            len(unlisted),
        )
        return result
    except Exception as exc:
        logger.error("eShip inventory fetch error: %s", exc)
        return {"sold_out": [], "unlisted": [], "cached_at": 0, "error": str(exc)}
