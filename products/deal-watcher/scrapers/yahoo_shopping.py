from urllib.parse import quote
from .base import BaseScraper, Item, logger
import config


class YahooShoppingScraper(BaseScraper):
    platform = "yahoo_shopping"

    async def search(self, keyword: str) -> list[Item]:
        if not config.YAHOO_APP_ID:
            logger.debug("[yahoo_shopping] YAHOO_APP_ID not set, skipping")
            return []

        url = (
            f"https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
            f"?appid={config.YAHOO_APP_ID}"
            f"&query={quote(keyword)}"
            f"&results=20&sort=-score"
        )
        items = []
        try:
            async with self._client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            hits = data.get("hits", [])
            for hit in hits:
                item_id = hit.get("code", "")
                if not item_id:
                    continue

                price = hit.get("price")
                image = hit.get("image", {})
                image_url = image.get("medium") if isinstance(image, dict) else None

                items.append(Item(
                    platform=self.platform,
                    external_id=str(item_id),
                    title=hit.get("name", ""),
                    price=int(price) if price else None,
                    url=hit.get("url", ""),
                    image_url=image_url,
                ))
        except Exception as e:
            logger.error(f"[yahoo_shopping] search error: {e}")

        return items
