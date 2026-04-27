"""Yahoo!フリマ（旧PayPayフリマ）スクレイパー — Playwright

paypayfleamarket.yahoo.co.jp を検索し、仕入れ候補を返す。
JS必須のためPlaywright使用。
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


class PayPayFleaScraper:
    platform_name = "Yahoo!フリマ"

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
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{encoded_keyword}?price_max={max_price_jpy}"

        results = []
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
                        "Referer": "https://paypayfleamarket.yahoo.co.jp/",
                    },
                )
                page = await context.new_page()

                try:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(page)
                except ImportError:
                    pass

                # DNS一時障害対策: リトライ（最大3回）
                resp = None
                for attempt in range(3):
                    try:
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        break
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(f"[Yahoo!フリマ] 接続リトライ ({attempt + 1}/3): {e}")
                            await page.wait_for_timeout(2000 * (attempt + 1))
                        else:
                            raise

                status = resp.status if resp else 0
                if status >= 400:
                    logger.warning(f"[Yahoo!フリマ] '{keyword}': HTTP {status}")
                    await browser.close()
                    return results

                # JS描画＋lazy load
                await page.wait_for_timeout(5000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)

                # 複数のセレクタを試す（仕様変更に強くする）
                selectors = [
                    "a[href*='/item/z']",
                    "a[href*='/item/']",
                    "li a[data-cl-params]",
                ]
                items = []
                used_selector = ""
                for sel in selectors:
                    items = await page.query_selector_all(sel)
                    if items:
                        used_selector = sel
                        break
                logger.debug(
                    f"[Yahoo!フリマ] セレクタ='{used_selector}' 検出: {len(items)}件"
                )

                seen_urls = set()
                for item in items[: limit * 3]:
                    if len(results) >= limit:
                        break
                    try:
                        candidate = await _parse_item(item)
                        if candidate and candidate.url not in seen_urls:
                            if candidate.price_jpy <= max_price_jpy and candidate.price_jpy > 0:
                                if junk_ok or not candidate.is_junk:
                                    seen_urls.add(candidate.url)
                                    results.append(candidate)
                    except Exception as e:
                        logger.debug(f"[Yahoo!フリマ] アイテムパースエラー: {e}")

                await browser.close()
        except Exception as e:
            logger.error(f"[Yahoo!フリマ] 検索失敗: {e}")

        logger.info(f"[Yahoo!フリマ] '{keyword}': {len(results)}件取得")
        return results


async def _parse_item(item) -> Optional[SourceCandidate]:
    href = await item.get_attribute("href") or ""
    if not href or "/item/" not in href:
        return None

    url = href if href.startswith("http") else f"https://paypayfleamarket.yahoo.co.jp{href}"

    # タイトル: img alt 属性から取得
    title = ""
    img_el = await item.query_selector("img[alt]")
    if img_el:
        title = (await img_el.get_attribute("alt") or "").strip()

    # フォールバック: inner_text
    if not title:
        all_text = (await item.inner_text()).strip()
        noise = {"いいね！", "SOLD", "送料無料", ""}
        for line in all_text.split("\n"):
            line = line.strip()
            if line not in noise and "円" not in line and not re.match(r"^[\d,]+$", line):
                title = line
                break

    if not title:
        return None

    # 価格: data-cl-params 属性 ( price:6500 形式 )
    price_jpy = 0
    cl_params = await item.get_attribute("data-cl-params") or ""
    price_match = re.search(r"price:(\d+)", cl_params)
    if price_match:
        price_jpy = int(price_match.group(1))

    # フォールバック: inner_text から
    if price_jpy == 0:
        all_text = (await item.inner_text()).strip()
        for line in all_text.split("\n"):
            line = line.strip()
            if "円" in line:
                price_jpy = parse_price(line)
                if price_jpy > 0:
                    break
            elif re.match(r"^[\d,]+$", line):
                val = int(line.replace(",", ""))
                if val > 0:
                    price_jpy = val
                    break

    # 画像
    image_url = ""
    if img_el:
        image_url = await img_el.get_attribute("src") or ""

    condition = guess_condition(title)

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="Yahoo!フリマ",
        url=url,
        image_url=image_url,
        condition=condition,
        is_junk=is_junk(title, condition),
    )
