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
        # 2026-04: VPS IP は PC 版で 403 連発 → モバイルUA を優先 → ダメなら PC 版にフォールバック
        attempts = [
            {
                "label": "mobile",
                "ua": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.4 Mobile/15E148 Safari/604.1"
                ),
                "viewport": {"width": 390, "height": 844},
            },
            {
                "label": "desktop",
                "ua": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0.0.0 Safari/537.36"
                ),
                "viewport": {"width": 1280, "height": 900},
            },
        ]
        url = (
            f"https://auctions.yahoo.co.jp/search/search/{encoded_kw}/0/"
            f"?fixed=1&max={max_price_jpy}&n=50"
        )

        results: list[SourceCandidate] = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)

                items_found: list = []
                last_status = 0

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
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception as e:
                        logger.warning(f"[ヤフオク/{att['label']}] goto失敗: {e}")
                        await context.close()
                        continue

                    last_status = resp.status if resp else 0
                    if last_status == 404:
                        logger.warning(f"[ヤフオク/{att['label']}] '{keyword}': 404（該当なし）")
                        await context.close()
                        continue
                    if last_status >= 400:
                        logger.warning(f"[ヤフオク/{att['label']}] '{keyword}': HTTP {last_status}")
                        await context.close()
                        continue

                    await page.wait_for_timeout(2500)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)

                    selectors = [
                        "li.Product",
                        "li[class*='Product']",
                        "a[href*='/jp/auction/']",
                    ]
                    for sel in selectors:
                        items_found = await page.query_selector_all(sel)
                        if items_found:
                            logger.debug(
                                f"[ヤフオク/{att['label']}] sel='{sel}' 検出: {len(items_found)}件"
                            )
                            break

                    await context.close()
                    if items_found:
                        break

                if not items_found:
                    logger.error(
                        f"[ヤフオク] '{keyword}': 全アプローチ失敗 (last_status={last_status})"
                    )
                    await browser.close()
                    return results

                seen_urls: set[str] = set()
                for item in items_found[: limit * 3]:
                    if len(results) >= limit:
                        break
                    try:
                        candidate = await _parse_item_pw(item)
                        if candidate and candidate.url not in seen_urls:
                            if 0 < candidate.price_jpy <= max_price_jpy:
                                if junk_ok or not candidate.is_junk:
                                    seen_urls.add(candidate.url)
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
    # PC版（li.Product）→ モバイル版（aタグ直） どちらでも動くようにフォールバック
    title_el = (
        await item.query_selector(".Product__titleLink")
        or await item.query_selector(".Product__title a")
        or await item.query_selector("a[href*='/jp/auction/']")
    )

    # itemそのものがアンカーなら自分自身を使う
    self_tag = (await item.evaluate("el => el.tagName")) or ""
    if not title_el and self_tag.lower() == "a":
        title_el = item

    if not title_el:
        return None

    raw_text = (await title_el.inner_text()).strip()
    url = (await title_el.get_attribute("href")) or ""
    if url and not url.startswith("http"):
        url = "https://auctions.yahoo.co.jp" + url

    # タイトル: PC版は title 単体、モバイル版は title+価格+詳細が改行で混在
    title = raw_text.split("\n")[0].strip() if raw_text else ""

    price_el = (
        await item.query_selector(".Product__priceValue")
        or await item.query_selector(".Product__price")
        or await item.query_selector("[class*='Price']")
    )
    price_text = (await price_el.inner_text()).strip() if price_el else ""

    price_jpy = 0
    if price_text:
        price_jpy = int(re.sub(r"[^\d]", "", price_text) or "0")
    if price_jpy == 0 and raw_text:
        # モバイル版: inner_text 全体から「￥XXX」「XXX円」を拾う
        m = re.search(r"[¥￥]\s*([\d,]+)", raw_text)
        if not m:
            m = re.search(r"([\d,]+)\s*円", raw_text)
        if m:
            price_jpy = int(m.group(1).replace(",", ""))

    condition = guess_condition(title)

    img_el = (
        await item.query_selector(".Product__imageData img")
        or await item.query_selector("img")
    )
    image_url = ""
    if img_el:
        image_url = (await img_el.get_attribute("src")) or \
                    (await img_el.get_attribute("data-src")) or ""

    if not title or not url:
        return None

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="ヤフオク",
        url=url,
        image_url=image_url,
        condition=condition,
        is_junk=is_junk(title, condition),
    )
