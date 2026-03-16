from urllib.parse import quote
from .base import BaseScraper, Item, logger
import config


class RakutenScraper(BaseScraper):
    platform = "rakuten"

    async def search(self, keyword: str) -> list[Item]:
        if not config.RAKUTEN_APP_ID:
            logger.debug("[rakuten] RAKUTEN_APP_ID not set, skipping")
            return []

        url = (
            f"https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
            f"?applicationId={config.RAKUTEN_APP_ID}"
            f"&keyword={quote(keyword)}"
            f"&hits=20&sort=-updateTimestamp"
        )
        items = []
        try:
            async with self._client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            for item_data in data.get("Items", []):
                item = item_data.get("Item", item_data)
                item_code = item.get("itemCode", "")
                if not item_code:
                    continue

                price = item.get("itemPrice")
                images = item.get("mediumImageUrls", [])
                image_url = None
                if images:
                    first = images[0]
                    image_url = first.get("imageUrl") if isinstance(first, dict) else first

                items.append(Item(
                    platform=self.platform,
                    external_id=str(item_code),
                    title=item.get("itemName", ""),
                    price=int(price) if price else None,
                    url=item.get("itemUrl", ""),
                    image_url=image_url,
                ))
        except Exception as e:
            logger.error(f"[rakuten] search error: {e}")

        return items
