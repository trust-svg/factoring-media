import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base import BaseScraper, Item, logger


class YahooAuctionScraper(BaseScraper):
    platform = "yahoo_auction"

    async def search(self, keyword: str) -> list[Item]:
        url = (
            f"https://auctions.yahoo.co.jp/search/search"
            f"?p={quote(keyword)}&n=20&s1=new&o1=d"
        )
        items = []
        try:
            async with self._client() as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            products = soup.select(".Product")

            for prod in products[:20]:
                link_el = prod.select_one(".Product__titleLink")
                if not link_el:
                    continue
                title = link_el.get_text(strip=True)
                href = link_el.get("href", "")

                # Extract auction ID from URL
                aid_match = re.search(r"/([a-zA-Z]\d+)$", href)
                if not aid_match:
                    aid_match = re.search(r"/([a-zA-Z]\d+)\?", href)
                ext_id = aid_match.group(1) if aid_match else href

                price_el = prod.select_one(".Product__priceValue")
                price = None
                if price_el:
                    price_text = re.sub(r"[^\d]", "", price_el.get_text())
                    price = int(price_text) if price_text else None

                img_el = prod.select_one(".Product__imageData")
                image_url = img_el.get("src") if img_el else None

                items.append(Item(
                    platform=self.platform,
                    external_id=str(ext_id),
                    title=title,
                    price=price,
                    url=href,
                    image_url=image_url,
                ))
        except Exception as e:
            logger.error(f"[yahoo_auction] search error: {e}")

        return items
