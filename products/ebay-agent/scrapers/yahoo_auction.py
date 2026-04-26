"""ヤフオク 検索スクレイパー — Playwright + Stealth

auctions.yahoo.co.jp を検索し、仕入れ候補を返す。
2026-04: VPS IP からの 403 Forbidden 多発のため requests → Playwright 化。
※ yahoo_auctions.py（落札履歴スクレイパー）とは別ファイル。
"""
import asyncio
import logging
import re
import urllib.parse
from typing import Optional

from sourcing.schema import SourceCandidate
from scrapers import guess_condition, is_junk

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 2.0


class YahooAuctionScraper:
    platform_name = "ヤフオク"

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 20,
    ) -> list[SourceCandidate]:
        from playwright.async_api import async_playwright

        await asyncio.sleep(RATE_LIMIT_SEC)

        encoded_kw = urllib.parse.quote(keyword, safe="")
        url = (
            f"https://auctions.yahoo.co.jp/search/search/{encoded_kw}/0/"
            f"?fixed=1&max={max_price_jpy}&n=50"
        )

        results: list[SourceCandidate] = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    locale="ja-JP",
                    timezone_id="Asia/Tokyo",
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/130.0.0.0 Safari/537.36"
                    ),
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

                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                status = resp.status if resp else 0

                if status == 404:
                    short_kw = _simplify_keyword(keyword)
                    if short_kw and short_kw != keyword:
                        logger.info(f"[ヤフオク] '{keyword}' → 404 → '{short_kw}' でリトライ")
                        encoded_kw = urllib.parse.quote(short_kw, safe="")
                        url = (
                            f"https://auctions.yahoo.co.jp/search/search/{encoded_kw}/0/"
                            f"?fixed=1&max={max_price_jpy}&n=50"
                        )
                        await asyncio.sleep(1)
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        status = resp.status if resp else 0

                if status == 404:
                    logger.warning(f"[ヤフオク] '{keyword}': 404（該当なし）")
                    await browser.close()
                    return results

                if status >= 400:
                    logger.error(f"[ヤフオク] '{keyword}': HTTP {status}")
                    await browser.close()
                    return results

                # JS描画＋lazy load
                await page.wait_for_timeout(2000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

                items = await page.query_selector_all("li.Product")
                logger.debug(f"[ヤフオク] li.Product 検出: {len(items)}件")

                for item in items[:limit * 2]:
                    if len(results) >= limit:
                        break
                    try:
                        candidate = await _parse_item_pw(item)
                        if candidate:
                            if candidate.price_jpy <= max_price_jpy:
                                if junk_ok or not candidate.is_junk:
                                    results.append(candidate)
                    except Exception as e:
                        logger.debug(f"[ヤフオク] アイテムパースエラー: {e}")

                await browser.close()
        except Exception as e:
            logger.error(f"[ヤフオク] 検索失敗: {e}")
            return results

        logger.info(f"[ヤフオク] '{keyword}': {len(results)}件取得")
        return results


def _simplify_keyword(keyword: str) -> str:
    words = keyword.split()
    if len(words) >= 2:
        return words[0]
    return ""


async def _parse_item_pw(item) -> Optional[SourceCandidate]:
    title_el = await item.query_selector(".Product__titleLink") or \
               await item.query_selector(".Product__title a")
    if not title_el:
        return None
    title = (await title_el.inner_text()).strip()
    url = (await title_el.get_attribute("href")) or ""
    if url and not url.startswith("http"):
        url = "https://auctions.yahoo.co.jp" + url

    price_el = await item.query_selector(".Product__priceValue") or \
               await item.query_selector(".Product__price")
    price_text = (await price_el.inner_text()).strip() if price_el else "0"
    price_jpy = int(re.sub(r"[^\d]", "", price_text) or "0")

    condition = guess_condition(title)

    img_el = await item.query_selector(".Product__imageData img") or \
             await item.query_selector("img")
    image_url = ""
    if img_el:
        image_url = (await img_el.get_attribute("src")) or \
                    (await img_el.get_attribute("data-src")) or ""

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="ヤフオク",
        url=url,
        image_url=image_url,
        condition=condition,
        is_junk=is_junk(title, condition),
    )
