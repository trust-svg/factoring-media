"""駿河屋スクレイパー — requests + BeautifulSoup

www.suruga-ya.jp を検索し、仕入れ候補を返す。
ホビー・ゲーム・AV機器に強い。requestsベースで安定動作。
"""
import asyncio
import logging
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from scrapers import HEADERS, guess_condition, is_junk
from sourcing.schema import SourceCandidate

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 2.0


class SurugayaScraper:
    platform_name = "駿河屋"

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
            logger.info(f"[駿河屋] '{keyword}' → 0件のため '{first_word}' でリトライ")
            await asyncio.sleep(RATE_LIMIT_SEC)
            items = self._fetch_and_parse(first_word)

        results = []
        for item in items[:limit]:
            try:
                title = item["title"]
                price = item["price"]
                condition = guess_condition(title, item.get("condition_text", ""))

                if price > max_price_jpy:
                    continue
                if not junk_ok and is_junk(title, condition):
                    continue

                results.append(SourceCandidate(
                    title=title,
                    price_jpy=price,
                    platform="駿河屋",
                    url=item["url"],
                    image_url=item.get("image_url", ""),
                    condition=condition,
                    is_junk=is_junk(title, condition),
                ))
            except Exception as e:
                logger.warning(f"[駿河屋] パースエラー: {e}")

        logger.info(f"[駿河屋] '{keyword}': {len(results)}件取得")
        return results

    def _fetch_and_parse(self, keyword: str) -> list[dict]:
        encoded_kw = urllib.parse.quote(keyword)
        url = f"https://www.suruga-ya.jp/search?category=&search_word={encoded_kw}&rankBy=price%3Aascending"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"[駿河屋] HTTP {resp.status_code}")
                return []
        except requests.RequestException as e:
            logger.warning(f"[駿河屋] リクエストエラー: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        product_cards = soup.select(".item")
        if not product_cards:
            product_cards = soup.select(".product_box, .item_box, [class*='product']")

        for card in product_cards:
            try:
                # タイトル
                title_el = card.select_one(".title a, .item_title a, h3 a, a[title]")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.suruga-ya.jp" + href

                # 価格
                price_el = card.select_one(".price, .item_price, [class*='price']")
                if not price_el:
                    continue
                price_text = price_el.get_text(strip=True)
                price_num = re.sub(r"[^\d]", "", price_text)
                if not price_num:
                    continue

                # 画像
                img_el = card.select_one("img")
                image_url = img_el.get("src", "") if img_el else ""

                # コンディション
                condition_el = card.select_one(
                    ".condition, .item_condition, [class*='condition']"
                )
                condition_text = condition_el.get_text(strip=True) if condition_el else ""

                items.append({
                    "title": title,
                    "price": int(price_num),
                    "url": href,
                    "image_url": image_url,
                    "condition_text": condition_text,
                })
            except Exception:
                continue

        return items
