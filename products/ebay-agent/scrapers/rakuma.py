"""ラクマ スクレイパー — Playwright

fril.jp を検索し、仕入れ候補を返す。
JS必須のためPlaywright使用。出品数は他サイトより少なめ。
"""
import asyncio
import logging
import re
import urllib.parse
from typing import Optional

from sourcing.schema import SourceCandidate
from scrapers import guess_condition, is_junk, parse_price

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 3.0


class RakumaScraper:
    platform_name = "ラクマ"

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 10,
    ) -> list[SourceCandidate]:
        from playwright.async_api import async_playwright

        await asyncio.sleep(RATE_LIMIT_SEC)

        encoded_keyword = urllib.parse.quote(keyword)
        url = f"https://fril.jp/search/{encoded_keyword}?sort=sell_price&order=asc"

        results = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(7000)

                # タイトルリンク（a.link_search_title）で取得
                items = await page.query_selector_all("a.link_search_title")
                # フォールバック: data属性
                if not items:
                    items = await page.query_selector_all("a[data-rat-item_name]")
                # フォールバック: URL パターン
                if not items:
                    items = await page.query_selector_all("a[href*='item.fril.jp']")

                logger.debug(f"[ラクマ] 商品リンク検出: {len(items)}件")

                seen_urls = set()
                for item in items:
                    if len(results) >= limit:
                        break
                    try:
                        candidate = await _parse_item(item)
                        if candidate and candidate.url not in seen_urls:
                            if candidate.price_jpy <= max_price_jpy:
                                if junk_ok or not candidate.is_junk:
                                    seen_urls.add(candidate.url)
                                    results.append(candidate)
                    except Exception as e:
                        logger.debug(f"[ラクマ] アイテムパースエラー: {e}")

                await browser.close()
        except Exception as e:
            logger.error(f"[ラクマ] 検索失敗: {e}")

        logger.info(f"[ラクマ] '{keyword}': {len(results)}件取得")
        return results


async def _parse_item(link_el) -> Optional[SourceCandidate]:
    href = await link_el.get_attribute("href") or ""
    if not href or "item.fril.jp" not in href:
        return None

    url = href if href.startswith("http") else f"https:{href}"

    # SOLD OUT 除外
    all_text = (await link_el.inner_text()).strip()
    if "SOLD" in all_text.upper():
        return None

    # タイトル: data-rat-item_name 属性（最も確実）
    title = await link_el.get_attribute("data-rat-item_name") or ""
    title = title.strip()

    # フォールバック: inner_text
    if not title:
        title = all_text.split("\n")[0].strip() if all_text else ""

    if not title:
        return None

    # 価格: data-rat-price 属性
    price_str = await link_el.get_attribute("data-rat-price") or ""
    price_jpy = int(price_str) if price_str.isdigit() else 0

    # フォールバック: 親要素から価格取得
    if price_jpy == 0:
        try:
            parent = await link_el.evaluate_handle(
                "el => el.closest('.item-box') || el.parentElement.parentElement"
            )
            if parent:
                price_el = await parent.query_selector(
                    "[data-content]:not([data-content='JPY'])"
                )
                if price_el:
                    price_text = await price_el.get_attribute("data-content") or ""
                    price_jpy = int(price_text) if price_text.isdigit() else 0
        except Exception:
            pass

    # さらにフォールバック: テキストから
    if price_jpy == 0:
        for line in all_text.split("\n"):
            line = line.strip()
            if "¥" in line or "円" in line:
                price_jpy = parse_price(line)
                if price_jpy > 0:
                    break

    # 画像: 同じ商品カード内のimg
    image_url = ""
    try:
        parent = await link_el.evaluate_handle(
            "el => el.closest('.item-box') || el.parentElement"
        )
        if parent:
            img_el = await parent.query_selector("img")
            if img_el:
                image_url = await img_el.get_attribute("src") or ""
    except Exception:
        pass

    condition = guess_condition(title)

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="ラクマ",
        url=url,
        image_url=image_url,
        condition=condition,
        is_junk=is_junk(title, condition),
    )
