"""Individual listing page scraper — fetch detailed data from a single URL.

Supports: Yahoo Auction, Mercari, Yahoo Fleamarket, Rakuma, Hard Off
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

import config
from scrapers.base import DetailedItem

logger = logging.getLogger(__name__)

_UA = config.USER_AGENT
_TIMEOUT = 20


def detect_platform(url: str) -> str:
    """Detect marketplace platform from URL."""
    u = url.lower()
    if "auctions.yahoo.co.jp" in u:
        return "yahoo_auction"
    if "mercari.com" in u or "jp.mercari" in u:
        return "mercari"
    if "paypayfleamarket.yahoo.co.jp" in u:
        return "yahoo_fleamarket"
    if "fril.jp" in u or "rakuma" in u:
        return "rakuma"
    if "hardoff" in u or "netmall.hardoff" in u:
        return "hardoff"
    return ""


async def scrape_detail(url: str) -> Optional[DetailedItem]:
    """Scrape detailed listing data from a single URL.

    Auto-detects platform and dispatches to the appropriate scraper.
    Returns None if scraping fails or platform is unsupported.
    """
    platform = detect_platform(url)
    if not platform:
        logger.warning(f"Unsupported platform URL: {url}")
        return None

    try:
        scrapers = {
            "yahoo_auction": _scrape_yahoo_auction,
            "mercari": _scrape_mercari,
            "yahoo_fleamarket": _scrape_yahoo_fleamarket,
            "rakuma": _scrape_rakuma,
            "hardoff": _scrape_hardoff,
        }
        fn = scrapers.get(platform)
        if fn:
            return await fn(url)
    except Exception as e:
        logger.error(f"Scrape error [{platform}]: {e}")
    return None


# ── Yahoo Auction ────────────────────────────────────────

async def _scrape_yahoo_auction(url: str) -> Optional[DetailedItem]:
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Title
    title_el = soup.select_one("h1.ProductTitle__text") or soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else ""

    # Price
    price = 0
    price_el = soup.select_one(".Price__value") or soup.select_one('[data-testid="price"]')
    if price_el:
        price = int(re.sub(r"[^\d]", "", price_el.get_text()))

    # Images
    image_urls = []
    for img in soup.select(".ProductImage__image img, .ProductImage__inner img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and "thumb" not in src and src.startswith("http"):
            image_urls.append(src)
    # Also check og:image
    if not image_urls:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            image_urls.append(og["content"])

    # Description
    desc_el = soup.select_one(".ProductExplanation__commentBody") or soup.select_one("#ProductExplanation")
    description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""

    # Condition
    condition = ""
    cond_el = soup.select_one(".ProductDetail__item--condition")
    if cond_el:
        condition = cond_el.get_text(strip=True)

    # External ID
    ext_id = ""
    m = re.search(r'/auction/([a-zA-Z0-9]+)', url)
    if m:
        ext_id = m.group(1)

    return DetailedItem(
        platform="yahoo_auction",
        url=url,
        title=title,
        price=price,
        description=description,
        condition=condition,
        image_urls=image_urls,
        external_id=ext_id,
    )


# ── Mercari ──────────────────────────────────────────────

async def _scrape_mercari(url: str) -> Optional[DetailedItem]:
    """Mercari requires Playwright (CSR site)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed for Mercari scraping")
        return None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--single-process"],
        )
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            # Title
            title = ""
            title_el = await page.query_selector('h1, [data-testid="name"]')
            if title_el:
                title = (await title_el.inner_text()).strip()

            # Price
            price = 0
            price_el = await page.query_selector('[data-testid="price"], .item-price')
            if price_el:
                price_text = await price_el.inner_text()
                digits = re.sub(r"[^\d]", "", price_text)
                if digits:
                    price = int(digits)

            # Images
            image_urls = []
            img_els = await page.query_selector_all('img[src*="static.mercdn.net"]')
            for img in img_els:
                src = await img.get_attribute("src")
                if src and "thumb" not in src:
                    image_urls.append(src)
            # Deduplicate
            image_urls = list(dict.fromkeys(image_urls))

            # Description
            description = ""
            desc_el = await page.query_selector('[data-testid="description"], .item-description')
            if desc_el:
                description = (await desc_el.inner_text()).strip()

            # Condition
            condition = ""
            cond_el = await page.query_selector('[data-testid="condition"], .item-condition')
            if cond_el:
                condition = (await cond_el.inner_text()).strip()

            # External ID
            ext_id = ""
            m = re.search(r'/item/([a-zA-Z0-9]+)', url)
            if m:
                ext_id = m.group(1)

            return DetailedItem(
                platform="mercari",
                url=url,
                title=title,
                price=price,
                description=description,
                condition=condition,
                image_urls=image_urls,
                external_id=ext_id,
            )
        finally:
            await browser.close()


# ── Yahoo Fleamarket (PayPay) ────────────────────────────

async def _scrape_yahoo_fleamarket(url: str) -> Optional[DetailedItem]:
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try __NEXT_DATA__ JSON
    script = soup.select_one("script#__NEXT_DATA__")
    if script:
        import json
        try:
            data = json.loads(script.string)
            props = data.get("props", {}).get("pageProps", {})
            item = props.get("item", {})
            if item:
                image_urls = [img.get("url", "") for img in item.get("images", []) if img.get("url")]
                return DetailedItem(
                    platform="yahoo_fleamarket",
                    url=url,
                    title=item.get("name", ""),
                    price=int(item.get("price", 0)),
                    description=item.get("description", ""),
                    condition=item.get("condition", {}).get("name", ""),
                    image_urls=image_urls,
                    external_id=item.get("id", ""),
                )
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: HTML parsing
    title = ""
    title_el = soup.select_one("h1")
    if title_el:
        title = title_el.get_text(strip=True)

    price = 0
    og_price = soup.select_one('meta[property="product:price:amount"]')
    if og_price:
        price = int(og_price.get("content", "0"))

    image_urls = []
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img and og_img.get("content"):
        image_urls.append(og_img["content"])

    description = ""
    desc_el = soup.select_one('[class*="description"]')
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)

    return DetailedItem(
        platform="yahoo_fleamarket",
        url=url,
        title=title,
        price=price,
        description=description,
        condition="",
        image_urls=image_urls,
        external_id="",
    )


# ── Rakuma (fril.jp) ────────────────────────────────────

async def _scrape_rakuma(url: str) -> Optional[DetailedItem]:
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    title_el = soup.select_one("h1.item-name") or soup.select_one("h1")
    if title_el:
        title = title_el.get_text(strip=True)

    price = 0
    price_el = soup.select_one(".item-price__value") or soup.select_one('[itemprop="price"]')
    if price_el:
        content = price_el.get("content") or price_el.get_text()
        digits = re.sub(r"[^\d]", "", str(content))
        if digits:
            price = int(digits)

    image_urls = []
    for img in soup.select(".item-gallery img, .item-image img"):
        src = img.get("src") or img.get("data-original") or ""
        if src and src.startswith("http"):
            image_urls.append(src)
    if not image_urls:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            image_urls.append(og["content"])

    description = ""
    desc_el = soup.select_one(".item-description") or soup.select_one('[itemprop="description"]')
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)

    condition = ""
    cond_el = soup.select_one(".item-condition")
    if cond_el:
        condition = cond_el.get_text(strip=True)

    ext_id = ""
    m = re.search(r'/([a-f0-9]{32}|[0-9]+)', url)
    if m:
        ext_id = m.group(1)

    return DetailedItem(
        platform="rakuma",
        url=url,
        title=title,
        price=price,
        description=description,
        condition=condition,
        image_urls=image_urls,
        external_id=ext_id,
    )


# ── Hard Off ─────────────────────────────────────────────

async def _scrape_hardoff(url: str) -> Optional[DetailedItem]:
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    title_el = soup.select_one("h1.product-title") or soup.select_one("h1")
    if title_el:
        title = title_el.get_text(strip=True)

    price = 0
    price_el = soup.select_one(".product-price") or soup.select_one('[class*="price"]')
    if price_el:
        digits = re.sub(r"[^\d]", "", price_el.get_text())
        if digits:
            price = int(digits)

    image_urls = []
    for img in soup.select(".product-image img, .swiper-slide img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and src.startswith("http"):
            image_urls.append(src)
    if not image_urls:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            image_urls.append(og["content"])

    description = ""
    desc_el = soup.select_one(".product-description") or soup.select_one('[class*="comment"]')
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)

    condition = ""
    cond_el = soup.select_one('[class*="condition"], [class*="rank"]')
    if cond_el:
        condition = cond_el.get_text(strip=True)

    ext_id = ""
    m = re.search(r'/product/(\d+)', url)
    if m:
        ext_id = m.group(1)

    return DetailedItem(
        platform="hardoff",
        url=url,
        title=title,
        price=price,
        description=description,
        condition=condition,
        image_urls=image_urls,
        external_id=ext_id,
    )
