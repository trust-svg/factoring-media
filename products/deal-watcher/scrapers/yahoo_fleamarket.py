from __future__ import annotations
import json
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base import BaseScraper, Item, logger


class YahooFleamarketScraper(BaseScraper):
    platform = "yahoo_fleamarket"

    async def search(self, keyword: str) -> list:
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}"
        items = []
        try:
            async with self._client() as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            script = soup.select_one("script#__NEXT_DATA__")
            if not script or not script.string:
                return items

            data = json.loads(script.string)
            search_items = (
                data.get("props", {})
                .get("initialState", {})
                .get("searchState", {})
                .get("search", {})
                .get("result", {})
                .get("items", [])
            )

            for si in search_items[:20]:
                item_id = str(si.get("id", ""))
                if not item_id:
                    continue
                items.append(Item(
                    platform=self.platform,
                    external_id=item_id,
                    title=si.get("title", ""),
                    price=si.get("price"),
                    url=f"https://paypayfleamarket.yahoo.co.jp/item/{item_id}",
                    image_url=si.get("thumbnailImageUrl"),
                ))
        except Exception as e:
            logger.error(f"[yahoo_fleamarket] search error: {e}")

        return items
