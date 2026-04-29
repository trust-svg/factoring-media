"""ヤフオク 検索スクレイパー — requests 主軸 + Playwright フォールバック

auctions.yahoo.co.jp を検索し、仕入れ候補を返す。

DOM 仕様 (2026-04 確認):
  各 <li class="Product"> 内に <a class="Product__imageLink"> または
  <a class="Product__titleLink"> があり、以下の data-* 属性で構造化データを持つ。
    - data-auction-id     : オークションID (例: t1227735194)
    - data-auction-title  : 商品タイトル
    - data-auction-price  : 即決/現在価格 (円)
    - data-auction-img    : 画像URL

このため inner_text に頼らず data-* 属性で安定パースする。

Mac (住宅IP) では requests で十分動作。VPS は site_registry の env switch で
file_source へ差し替わるため、ここのコードは VPS では呼ばれない想定。
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from typing import Optional

import requests

from sourcing.schema import SourceCandidate
from scrapers import HEADERS, guess_condition, is_junk

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 2.0

_DATA_ATTR_RE = re.compile(
    r'<a[^>]*class="(?P<cls>[^"]*Product__(?:image|title)Link[^"]*)"[^>]*?'
    r'data-auction-id="(?P<id>[^"]+)"[^>]*?'
    r'data-auction-title="(?P<title>[^"]+)"[^>]*?'
    r'data-auction-img="(?P<img>[^"]*)"[^>]*?'
    r'data-auction-price="(?P<price>[^"]*)"',
    re.DOTALL,
)

# data-auction-img と data-auction-price の順序がブロックによって入れ替わるケース対応
_DATA_ATTR_ALT_RE = re.compile(
    r'<a[^>]*class="(?P<cls>[^"]*Product__(?:image|title)Link[^"]*)"[^>]*?'
    r'data-auction-id="(?P<id>[^"]+)"[^>]*?'
    r'data-auction-title="(?P<title>[^"]+)"[^>]*?'
    r'data-auction-price="(?P<price>[^"]*)"[^>]*?'
    r'data-auction-img="(?P<img>[^"]*)"',
    re.DOTALL,
)


def _build_url(keyword: str, max_price_jpy: int) -> str:
    encoded_kw = urllib.parse.quote(keyword, safe="")
    return (
        f"https://auctions.yahoo.co.jp/search/search/{encoded_kw}/0/"
        f"?fixed=1&max={max_price_jpy}&n=50"
    )


def _decode_html_entities(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )


def _parse_html(html: str) -> list[dict]:
    """data-auction-* 属性を正規表現で抽出。重複は data-auction-id で除外。"""
    seen: set[str] = set()
    items: list[dict] = []

    for pat in (_DATA_ATTR_RE, _DATA_ATTR_ALT_RE):
        for m in pat.finditer(html):
            aid = m.group("id")
            if aid in seen:
                continue
            seen.add(aid)
            items.append(
                {
                    "id": aid,
                    "title": _decode_html_entities(m.group("title")),
                    "img": m.group("img"),
                    "price": int(m.group("price")) if m.group("price").isdigit() else 0,
                }
            )

    return items


def _to_candidate(
    d: dict, max_price_jpy: int, junk_ok: bool
) -> Optional[SourceCandidate]:
    title = d["title"].strip()
    if not title:
        return None
    price = d["price"]
    if price <= 0 or price > max_price_jpy:
        return None
    url = f"https://auctions.yahoo.co.jp/jp/auction/{d['id']}"
    condition = guess_condition(title)
    junk = is_junk(title, condition)
    if junk and not junk_ok:
        return None
    return SourceCandidate(
        title=title,
        price_jpy=price,
        platform="ヤフオク",
        url=url,
        image_url=d["img"] or "",
        condition=condition,
        is_junk=junk,
    )


async def _search_via_requests(
    keyword: str,
    max_price_jpy: int,
    junk_ok: bool,
    limit: int,
) -> tuple[list[SourceCandidate], int]:
    """requests + 正規表現で取得。戻り値: (results, http_status)。失敗時は status=0 か 4xx/5xx。"""
    url = _build_url(keyword, max_price_jpy)
    try:
        resp = await asyncio.to_thread(requests.get, url, headers=HEADERS, timeout=15)
    except Exception as e:
        logger.warning(f"[ヤフオク/requests] '{keyword}': {e}")
        return [], 0

    if resp.status_code >= 400:
        return [], resp.status_code

    items = _parse_html(resp.text)
    results: list[SourceCandidate] = []
    for d in items:
        if len(results) >= limit:
            break
        cand = _to_candidate(d, max_price_jpy, junk_ok)
        if cand:
            results.append(cand)

    return results, resp.status_code


async def _search_via_playwright(
    keyword: str,
    max_price_jpy: int,
    junk_ok: bool,
    limit: int,
) -> list[SourceCandidate]:
    """requests がブロックされた場合のフォールバック。同じ data-* 属性パースを HTML 上で実行。"""
    from playwright.async_api import async_playwright

    url = _build_url(keyword, max_price_jpy)
    attempts = [
        {
            "label": "desktop",
            "ua": HEADERS["User-Agent"],
            "viewport": {"width": 1280, "height": 900},
        },
        {
            "label": "mobile",
            "ua": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Mobile/15E148 Safari/604.1"
            ),
            "viewport": {"width": 390, "height": 844},
        },
    ]

    results: list[SourceCandidate] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            for att in attempts:
                context = await browser.new_context(
                    locale="ja-JP",
                    timezone_id="Asia/Tokyo",
                    user_agent=att["ua"],
                    viewport=att["viewport"],
                    extra_http_headers={
                        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                        "Referer": "https://auctions.yahoo.co.jp/",
                    },
                )
                page = await context.new_page()
                try:
                    from playwright_stealth import Stealth

                    await Stealth().apply_stealth_async(page)
                except ImportError:
                    pass

                try:
                    resp = await page.goto(
                        url, wait_until="domcontentloaded", timeout=30000
                    )
                except Exception as e:
                    logger.warning(f"[ヤフオク/{att['label']}] goto失敗: {e}")
                    await context.close()
                    continue

                status = resp.status if resp else 0
                if status >= 400:
                    logger.warning(
                        f"[ヤフオク/{att['label']}] '{keyword}': HTTP {status}"
                    )
                    await context.close()
                    continue

                await page.wait_for_timeout(2000)
                html = await page.content()
                await context.close()

                items = _parse_html(html)
                for d in items:
                    if len(results) >= limit:
                        break
                    cand = _to_candidate(d, max_price_jpy, junk_ok)
                    if cand:
                        results.append(cand)

                if results:
                    break

            await browser.close()
    except Exception as e:
        logger.error(f"[ヤフオク/playwright] '{keyword}': {e}")

    return results


class YahooAuctionScraper:
    platform_name = "ヤフオク"

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 20,
    ) -> list[SourceCandidate]:
        await asyncio.sleep(RATE_LIMIT_SEC)

        # 1. requests で試す（Mac 住宅IPなら 200 で返る）
        results, status = await _search_via_requests(
            keyword, max_price_jpy, junk_ok, limit
        )
        if results:
            logger.info(f"[ヤフオク/requests] '{keyword}': {len(results)}件取得")
            return results
        if status == 200:
            # 200 で取れたが該当なし
            logger.info(f"[ヤフオク/requests] '{keyword}': 0件（該当商品なし）")
            return results
        if status == 404:
            logger.info(f"[ヤフオク/requests] '{keyword}': 404（該当なし）")
            return results

        # 2. requests が 403/タイムアウト等 → Playwright フォールバック
        logger.warning(
            f"[ヤフオク/requests] '{keyword}': status={status} → Playwrightへフォールバック"
        )
        results = await _search_via_playwright(keyword, max_price_jpy, junk_ok, limit)
        logger.info(f"[ヤフオク/playwright] '{keyword}': {len(results)}件取得")
        return results
