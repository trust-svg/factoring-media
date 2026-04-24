"""メルカリ 検索スクレイパー — Playwright + Stealth

jp.mercari.com を検索し、仕入れ候補を返す。
JS必須のためPlaywright使用。
※ mercari.py（購入履歴スクレイパー）とは別ファイル。
"""
import asyncio
import logging
import re
import urllib.parse
from typing import Optional

from sourcing.schema import SourceCandidate
from scrapers import guess_condition, is_junk

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 3.0


class MercariScraper:
    platform_name = "メルカリ"

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 15,
    ) -> list[SourceCandidate]:
        from playwright.async_api import async_playwright

        await asyncio.sleep(RATE_LIMIT_SEC)

        params = {
            "keyword": keyword,
            "status": "on_sale",
            "price_max": max_price_jpy,
        }
        url = "https://jp.mercari.com/search?" + urllib.parse.urlencode(params)

        results = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    locale="ja-JP",
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/130.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()

                # stealth 適用
                try:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(page)
                except ImportError:
                    pass

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Reactレンダリング完了を待つ
                await page.wait_for_timeout(8000)
                # lazy loading対策
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

                # 商品リンクは /item/m{id} 形式
                items = await page.query_selector_all("a[href*='/item/m']")
                logger.debug(f"[メルカリ] 商品リンク検出: {len(items)}件")

                seen_urls = set()
                for item in items[:limit * 2]:
                    if len(results) >= limit:
                        break
                    try:
                        candidate = await _parse_from_link(item)
                        if candidate and candidate.url not in seen_urls:
                            if candidate.price_jpy <= max_price_jpy:
                                if junk_ok or not candidate.is_junk:
                                    seen_urls.add(candidate.url)
                                    results.append(candidate)
                    except Exception as e:
                        logger.debug(f"[メルカリ] リンクパースエラー: {e}")

                await browser.close()
        except Exception as e:
            logger.error(f"[メルカリ] 検索失敗: {e}")

        logger.info(f"[メルカリ] '{keyword}': {len(results)}件取得")
        return results


async def _parse_from_link(link_el) -> Optional[SourceCandidate]:
    href = await link_el.get_attribute("href") or ""
    if not href or "/item/" not in href:
        return None

    url = f"https://jp.mercari.com{href}" if href.startswith("/") else href

    # タイトル: data-testid="thumbnail-item-name"
    title = ""
    title_el = await link_el.query_selector("[data-testid='thumbnail-item-name']")
    if title_el:
        title = (await title_el.inner_text()).strip()

    # フォールバック: img alt（"...のサムネイル" を除去）
    if not title:
        img_el = await link_el.query_selector("img[alt]")
        if img_el:
            alt = (await img_el.get_attribute("alt")) or ""
            title = re.sub(r"のサムネイル$", "", alt).strip()

    if not title:
        return None

    # 価格: span[class*="number"]
    price_jpy = 0
    price_el = await link_el.query_selector("span[class*='number']")
    if price_el:
        price_text = await price_el.inner_text()
        price_jpy = int(re.sub(r"[^\d]", "", price_text) or "0")

    # フォールバック
    if price_jpy == 0:
        all_text = (await link_el.inner_text()).strip()
        for line in all_text.split("\n"):
            line = line.strip()
            if re.match(r"^[\d,]+$", line) and int(line.replace(",", "")) > 0:
                price_jpy = int(line.replace(",", ""))
                break

    # 画像
    img_el = await link_el.query_selector("img")
    image_url = await img_el.get_attribute("src") if img_el else ""

    condition = guess_condition(title)

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="メルカリ",
        url=url,
        image_url=image_url or "",
        condition=condition,
        is_junk=is_junk(title, condition),
    )
