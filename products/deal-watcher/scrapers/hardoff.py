import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base import BaseScraper, Item, logger


class HardoffScraper(BaseScraper):
    platform = "hardoff"

    async def search(self, keyword: str) -> list[Item]:
        url = (
            f"https://netmall.hardoff.co.jp/search"
            f"?q={quote(keyword)}&sort=arrival_date_desc"
        )
        items = []
        try:
            async with self._client() as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Hard Off netmall product cards
            products = soup.select('.itemList__item, .p-product-list__item, [class*="product"]')
            if not products:
                # Try link-based approach
                products = soup.select('a[href*="/product/"]')

            seen = set()
            for prod in products[:20]:
                link = prod if prod.name == "a" else prod.select_one("a[href]")
                if not link:
                    continue

                href = link.get("href", "")
                match = re.search(r"/product/(\d+)", href)
                if not match:
                    continue
                item_id = match.group(1)
                if item_id in seen:
                    continue
                seen.add(item_id)

                if href.startswith("/"):
                    full_url = f"https://netmall.hardoff.co.jp{href}"
                else:
                    full_url = href

                title_el = prod.select_one('[class*="name"], [class*="title"]')
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    img = prod.select_one("img")
                    title = img.get("alt", "") if img else ""
                if not title:
                    title = link.get_text(strip=True)[:100]

                price = None
                price_el = prod.select_one('[class*="price"]')
                if price_el:
                    price_text = re.sub(r"[^\d]", "", price_el.get_text())
                    price = int(price_text) if price_text else None

                img_el = prod.select_one("img")
                image_url = img_el.get("src") if img_el else None

                items.append(Item(
                    platform=self.platform,
                    external_id=item_id,
                    title=title or f"hardoff:{item_id}",
                    price=price,
                    url=full_url,
                    image_url=image_url,
                ))
        except Exception as e:
            logger.error(f"[hardoff] search error: {e}")

        return items
