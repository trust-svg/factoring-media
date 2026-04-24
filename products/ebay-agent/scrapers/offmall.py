"""ブックオフ公式オンラインストア (Offmall) スクレイパー — requests + BeautifulSoup

shopping.bookoff.co.jp を検索し、仕入れ候補を返す。
requestsベースで安定動作。Playwright不要。
"""
import asyncio
import logging
import urllib.parse
from typing import Optional

import requests
from bs4 import BeautifulSoup

from scrapers import HEADERS, guess_condition, is_junk, parse_price
from sourcing.schema import SourceCandidate

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 2.0


class OffmallScraper:
    platform_name = "ブックオフ"

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 15,
    ) -> list[SourceCandidate]:
        await asyncio.sleep(RATE_LIMIT_SEC)

        items = self._fetch_and_parse(keyword)

        # 複合キーワードで0件の場合、最初の語だけでリトライ
        if not items and " " in keyword:
            first_word = keyword.split()[0]
            logger.info(f"[ブックオフ] '{keyword}' → 0件のため '{first_word}' でリトライ")
            await asyncio.sleep(RATE_LIMIT_SEC)
            items = self._fetch_and_parse(first_word)

        results = []
        for item in items[:limit]:
            try:
                candidate = _parse_item(item)
                if candidate and candidate.price_jpy <= max_price_jpy:
                    if junk_ok or not candidate.is_junk:
                        results.append(candidate)
            except Exception as e:
                logger.debug(f"[ブックオフ] アイテムパースエラー: {e}")

        logger.info(f"[ブックオフ] '{keyword}': {len(results)}件取得")
        return results

    def _fetch_and_parse(self, keyword: str) -> list:
        encoded_keyword = urllib.parse.quote(keyword)
        url = f"https://shopping.bookoff.co.jp/search/keyword/{encoded_keyword}?sort=price-asc"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except Exception as e:
            logger.error(f"[ブックオフ] 検索失敗: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".productItem")
        if not items:
            items = soup.select("[class*='productItem']")
        return items


def _parse_item(item) -> Optional[SourceCandidate]:
    link_el = item.select_one("a.productItem__link, a.productItem__image, a[href]")
    if not link_el:
        return None

    href = link_el.get("href", "")
    url = href if href.startswith("http") else "https://shopping.bookoff.co.jp" + href

    # タイトル — .productItem__title (2026年3月時点の構造)
    title_el = (
        item.select_one(".productItem__title")
        or item.select_one("p.productItem__title")
        or item.select_one("img[alt]")  # alt属性にタイトルが入っている
    )
    if title_el and title_el.name == "img":
        title = title_el.get("alt", "").strip()
    else:
        title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    # 価格 — .productItem__price の直接テキスト（<small>の「定価より...」を除外）
    price_el = item.select_one(".productItem__price")
    price_jpy = 0
    if price_el:
        # <small>を除去してからパース
        small = price_el.find("small")
        if small:
            small.decompose()
        # moneyUnit span も除去
        unit = price_el.find("span", class_="productItem__moneyUnit")
        if unit:
            unit.decompose()
        price_text = price_el.get_text(strip=True)
        price_jpy = parse_price(price_text)

    # コンディション — タグリスト内の「中古」「新品」等
    condition = "中古品"  # ブックオフはほぼ中古
    tag_els = item.select(".tag")
    for tag in tag_els:
        tag_text = tag.get_text(strip=True)
        if tag_text in ("新品", "未使用"):
            condition = tag_text
            break

    # 画像
    img_el = item.select_one("img")
    image_url = ""
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src") or ""

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="ブックオフ",
        url=url,
        image_url=image_url,
        condition=condition,
        is_junk=is_junk(title, condition),
    )
