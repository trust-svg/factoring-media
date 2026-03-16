from __future__ import annotations
import re
from urllib.parse import quote
from .base import BaseScraper, Item, logger


class MercariScraper(BaseScraper):
    platform = "mercari"

    async def search(self, keyword: str) -> list:
        """Search Mercari using headless browser (CSR site).
        Browser launches per-search and closes immediately to minimize memory.
        """
        url = (
            f"https://jp.mercari.com/search"
            f"?keyword={quote(keyword)}&status=on_sale"
            f"&order=desc&sort=created_time"
        )
        items = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("[mercari] playwright not installed, skipping")
            return items

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu", "--single-process"],
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    java_script_enabled=True,
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)

                # Extract item links
                item_elements = await page.query_selector_all('a[href*="/item/m"]')
                seen = set()

                for el in item_elements[:20]:
                    href = await el.get_attribute("href") or ""
                    match = re.search(r"/item/(m\d+)", href)
                    if not match:
                        continue
                    item_id = match.group(1)
                    if item_id in seen:
                        continue
                    seen.add(item_id)

                    # Text format: "¥\n47,000\nProduct Title"
                    full_text = (await el.inner_text()).strip()
                    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

                    price = None
                    title = ""
                    for line in lines:
                        if line == "¥":
                            continue
                        digits = re.sub(r"[^\d]", "", line)
                        if digits and re.match(r"^[\d,]+$", line) and price is None:
                            price = int(digits)
                        elif len(line) > 2 and not re.match(r"^[\d,¥]+$", line):
                            if not title:
                                title = line[:100]

                    if not title:
                        img = await el.query_selector("img")
                        if img:
                            title = await img.get_attribute("alt") or ""

                    image_url = None
                    img = await el.query_selector("img")
                    if img:
                        image_url = await img.get_attribute("src")

                    items.append(Item(
                        platform=self.platform,
                        external_id=item_id,
                        title=title or f"mercari:{item_id}",
                        price=price,
                        url=f"https://jp.mercari.com/item/{item_id}",
                        image_url=image_url,
                    ))

                await context.close()
                await browser.close()

        except Exception as e:
            logger.error(f"[mercari] search error: {e}")

        return items
