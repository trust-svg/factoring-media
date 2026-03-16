from __future__ import annotations
import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base import BaseScraper, Item, logger


class RakumaScraper(BaseScraper):
    platform = "rakuma"

    async def search(self, keyword: str) -> list:
        url = (
            f"https://fril.jp/s"
            f"?query={quote(keyword)}&sort=created_at&order=desc"
        )
        items = []
        try:
            async with self._client() as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            item_boxes = soup.select(".item-box")

            for box in item_boxes[:20]:
                link = box.select_one('a[href*="item.fril.jp"]')
                if not link:
                    continue

                href = link.get("href", "")
                # Extract ID from URL like https://item.fril.jp/abc123def
                match = re.search(r"item\.fril\.jp/([a-f0-9]+)", href)
                if not match:
                    continue
                item_id = match.group(1)

                img = box.select_one("img")
                title = img.get("alt", "") if img else ""
                if not title:
                    title = link.get_text(strip=True)[:100]

                price = None
                price_el = box.select_one(".item-box__item-price__value")
                if not price_el:
                    price_el = box.select_one('[class*="price"]')
                if price_el:
                    price_text = re.sub(r"[^\d]", "", price_el.get_text())
                    price = int(price_text) if price_text else None

                image_url = None
                if img:
                    src = img.get("data-original") or img.get("src", "")
                    if src and "dummy" not in src:
                        image_url = src

                items.append(Item(
                    platform=self.platform,
                    external_id=item_id,
                    title=title or f"rakuma:{item_id}",
                    price=price,
                    url=href,
                    image_url=image_url,
                ))
        except Exception as e:
            logger.error(f"[rakuma] search error: {e}")

        return items
