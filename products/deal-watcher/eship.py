"""eShip browser automation — set supplier info and activate listings."""
import asyncio
import json
import logging
import os
import random
import time
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Profit cache stored as JSON file for persistence across module reloads
PROFIT_CACHE_TTL = 3600  # 1 hour
_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".eship_profit_cache.json")


def _load_cache() -> tuple[dict, float]:
    """Load profit cache from file."""
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r") as f:
                data = json.load(f)
            return data.get("profits", {}), data.get("ts", 0)
    except Exception:
        pass
    return {}, 0


def _save_cache(profits: dict):
    """Save profit cache to file."""
    with open(_CACHE_FILE, "w") as f:
        json.dump({"profits": profits, "ts": time.time()}, f)

ESHIP_URL = "https://eship-tool.com"
ESHIP_EMAIL = os.getenv("ESHIP_EMAIL", "")
ESHIP_PASSWORD = os.getenv("ESHIP_PASSWORD", "")

# deal-watcher platform -> eShip supplier_id
SUPPLIER_MAP = {
    "yahoo_auction": "20086",
    "mercari": "20083",
    "yahoo_fleamarket": "20090",
    "rakuma": "20085",
    "hardoff": "20089",
    "yahoo_shopping": "20087",
    "rakuten": "20088",
}


async def _login(page):
    """Login to eShip and return True on success."""
    await page.goto(f"{ESHIP_URL}/users/sign_in", wait_until="networkidle", timeout=30000)
    await page.fill('input[name="user[email]"]', ESHIP_EMAIL)
    await page.fill('input[name="user[password]"]', ESHIP_PASSWORD)
    await page.click('input[type="submit"]')
    await page.wait_for_load_state("networkidle", timeout=15000)
    return "/users/sign_in" not in page.url


async def _find_item_on_page(page, ebay_title: str):
    """Find matching eShip inventory item by eBay title.
    Returns the inventory ID if found, None otherwise.
    """
    title_lower = ebay_title.lower()
    title_words = title_lower.split()[:5]  # First 5 words for matching

    item_links = await page.query_selector_all('td a[href*="/inventories/"][href*="/edit"]')
    for link in item_links:
        text = (await link.inner_text()).strip().lower()
        # Match if most title words appear
        matches = sum(1 for w in title_words if w in text)
        if matches >= min(3, len(title_words)):
            href = await link.get_attribute("href") or ""
            # Extract ID from /inventories/12345/edit
            parts = href.split("/")
            for j, part in enumerate(parts):
                if part == "inventories" and j + 1 < len(parts):
                    return parts[j + 1]
    return None


async def _get_all_inventory_ids(page):
    """Get all inventory IDs and their names from current page."""
    items = []
    id_inputs = await page.query_selector_all('input[name="inventories[][id]"]')
    name_links = await page.query_selector_all('td a[href*="/inventories/"][href*="/edit"]')

    for i, hid in enumerate(id_inputs):
        item_id = await hid.get_attribute("value")
        name = ""
        if i < len(name_links):
            name = (await name_links[i].inner_text()).strip()
        items.append({"id": item_id, "name": name})
    return items


async def _search_item(page, query: str):
    """Use eShip's search to find an item."""
    search_input = await page.query_selector('input[name="q[ebay_item_id_or_supplier_url_or_name_or_sku_or_memo_cont]"]')
    if search_input:
        await search_input.fill(query)
        # Find and click the search button
        search_btn = await page.query_selector('input[type="submit"][value="検索"], button:has-text("検索")')
        if search_btn:
            await search_btn.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(random.uniform(1, 2))
            return True
    return False


async def fetch_eship_profits() -> dict:
    """Fetch profit data for all eShip inventory items.

    Returns dict keyed by SKU: {profit, profit_rate, tax_refunded_profit, tax_refunded_profit_rate}
    Uses a 1-hour cache to avoid hammering eShip.
    """
    cached, ts = _load_cache()
    if cached and (time.time() - ts) < PROFIT_CACHE_TTL:
        return cached

    if not ESHIP_EMAIL or not ESHIP_PASSWORD:
        return {}

    result = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-gpu", "--single-process"],
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
        page = await ctx.new_page()

        try:
            if not await _login(page):
                return {}

            page.set_default_timeout(60000)
            page_num = 1
            while True:
                url = f"{ESHIP_URL}/inventories?page={page_num}"
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(random.uniform(1.5, 2.5))

                rows = await page.query_selector_all("table tbody tr")
                if not rows:
                    break

                for row in rows:
                    # Get Item ID and SKU from cell[3]
                    cells = await row.query_selector_all("td")
                    item_id = ""
                    sku = ""
                    if len(cells) > 3:
                        text = (await cells[3].inner_text()).strip()
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        # Line 0 = Item ID (numeric), Line 2 = SKU
                        if lines:
                            item_id = lines[0]
                        for line in lines:
                            if not line.isdigit() and line not in ("出品削除",) and "Left" not in line:
                                sku = line
                                break

                    # Get profit + purchase_price values
                    profit_inputs = await row.query_selector_all('input[name="inventories[][profit]"]')
                    rate_inputs = await row.query_selector_all('input[name="inventories[][profit_rate]"]')
                    pp_inputs = await row.query_selector_all('input[name="inventories[][purchase_price]"]')

                    profit = float(await profit_inputs[0].get_attribute("value") or 0) if profit_inputs else 0
                    prate = float(await rate_inputs[0].get_attribute("value") or 0) if rate_inputs else 0
                    pp = float(await pp_inputs[0].get_attribute("value") or 0) if pp_inputs else 0

                    data = {
                        "profit": round(profit),
                        "profit_rate": prate,
                        "purchase_price": round(pp),
                    }
                    # Key by both Item ID and SKU for flexible matching
                    if item_id:
                        result[item_id] = data
                    if sku:
                        result[sku] = data

                # Check for next page (stop if < 2 rows = past real listings)
                if len(rows) < 2:
                    break
                next_link = await page.query_selector('a[rel="next"]')
                if not next_link:
                    break
                page_num += 1

            logger.info(f"Fetched eShip profit data for {len(result)} items")
        except Exception as e:
            logger.error(f"eShip profit fetch error: {e}")
        finally:
            await ctx.close()
            await browser.close()

    _save_cache(result)
    return result


async def create_eship_item(
    title: str,
    supplier_url: str,
    purchase_price: int,
    platform: str,
    selling_price_usd: float = 0,
    sku: str = "",
    ebay_item_id: str = "",
    condition: str = "Used",
    condition_description: str = "",
    image_url: str = "",
    category_id: str = "",
    category_path: str = "",
    height_cm: int = 0,
    length_cm: int = 0,
    width_cm: int = 0,
    memo: str = "",
) -> dict:
    """Create a NEW eShip inventory item via the /inventories/new form.

    All items are created as drafts (quantity=0).
    FedEx/北米 fixed. Promoted rate 2%.
    Volume weight is calculated from dimensions and used as weight.

    Returns: {"status": "ok", "inventory_id": ...} or error
    """
    supplier_id = SUPPLIER_MAP.get(platform, "")
    if not ESHIP_EMAIL or not ESHIP_PASSWORD:
        return {"status": "error", "message": "ESHIP credentials not set"}

    # Condition mapping
    condition_id = "2"  # Used
    if "new" in condition.lower() or "新品" in condition:
        condition_id = "1"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--single-process"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        page = await ctx.new_page()

        try:
            if not await _login(page):
                return {"status": "error", "message": "Login failed"}

            # Navigate to new inventory form
            new_url = f"{ESHIP_URL}/inventories/new?utf8=%E2%9C%93&store_account_id=1410&commit=%E9%80%B2%E3%82%80"
            await page.goto(new_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(random.uniform(1, 2))

            # Fill form fields
            async def _fill(name, value):
                if not value:
                    return
                el = await page.query_selector(f'input[name="{name}"]')
                if el:
                    await el.fill(str(value))

            async def _select(name, value):
                if not value:
                    return
                el = await page.query_selector(f'select[name="{name}"]')
                if el:
                    await el.select_option(value=str(value))

            # Required fields
            await _fill("inventory[name]", title[:100])
            await _fill("inventory[supplier_url]", supplier_url)
            await _fill("inventory[purchase_price]", purchase_price)
            await _fill("inventory[sku]", sku)
            await _fill("inventory[title]", title[:80])
            await _fill("inventory[quantity]", "1")
            await _fill("inventory[condition_description]", condition_description)
            await _fill("inventory[image_url]", image_url)
            await _fill("inventory[memo]", memo[:200])
            await _fill("inventory[promoted_rate]", "2")  # Fixed 2%

            # eBay fields
            if ebay_item_id:
                await _fill("inventory[ebay_item_id]", ebay_item_id)
            if selling_price_usd > 0:
                await _fill("inventory[selling_price]", int(selling_price_usd))
            if category_id:
                await _fill("inventory[ebay_category_id]", category_id)
            if category_path:
                await _fill("inventory[ebay_category_path]", category_path)

            # SELECT fields
            if supplier_id:
                await _select("inventory[supplier_id]", supplier_id)
            await _select("inventory[item_condition_id]", condition_id)
            await _select("inventory[stock_condition_id]", condition_id)

            # Shipping: FedEx + 北米
            await _select("inventory[shipping_method_id]", "4")  # FedEx
            await asyncio.sleep(1)  # Wait for area options to load
            await _select("inventory[shipping_area_id]", "2")  # 北米

            # Dimensions → volume weight
            if height_cm > 0 and length_cm > 0 and width_cm > 0:
                await _fill("inventory[height]", height_cm)
                await _fill("inventory[length]", length_cm)
                await _fill("inventory[width]", width_cm)
                # Volume weight = L x W x H / 5000 (FedEx formula, in grams)
                volume_weight = int(length_cm * width_cm * height_cm / 5000 * 1000)
                await _fill("inventory[weight]", volume_weight)
                await _fill("inventory[volume_weight]", volume_weight)

            await asyncio.sleep(random.uniform(0.5, 1))

            # Submit form
            submit_btn = await page.query_selector('input[type="submit"], button[type="submit"]')
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("networkidle", timeout=30000)
                await asyncio.sleep(random.uniform(1, 2))

            # Check success: URL should change to /inventories or /inventories/{id}/edit
            if "/inventories" in page.url and "/new" not in page.url:
                # Try to extract inventory ID from URL
                import re
                m = re.search(r'/inventories/(\d+)', page.url)
                inv_id = m.group(1) if m else ""
                logger.info(f"eShip item created: {title[:40]} (ID: {inv_id})")
                return {
                    "status": "ok",
                    "message": f"Created: {title[:50]}",
                    "inventory_id": inv_id,
                }
            else:
                # Check for error messages on page
                error_el = await page.query_selector('.alert-danger, .error, #error_explanation')
                error_msg = ""
                if error_el:
                    error_msg = await error_el.inner_text()
                return {
                    "status": "error",
                    "message": f"Form submission may have failed. URL: {page.url}. {error_msg}",
                }

        except Exception as e:
            logger.error(f"eShip create error: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            await ctx.close()
            await browser.close()


async def update_eship_item(
    ebay_title: str,
    supplier_url: str,
    purchase_price: int,
    platform: str,
    set_quantity: int = 1,
    sku: str = "",
) -> dict:
    """Find an eShip item by eBay title/SKU and update its supplier info.

    Args:
        ebay_title: eBay listing title to search for in eShip
        supplier_url: Source URL from deal-watcher
        purchase_price: Purchase price in JPY
        platform: deal-watcher platform key (yahoo_auction, mercari, etc.)
        set_quantity: Quantity to set (default 1)
        sku: eBay SKU for more reliable search (optional)

    Returns:
        dict with status, message, and inventory_id
    """
    supplier_id = SUPPLIER_MAP.get(platform)
    if not supplier_id:
        return {"status": "error", "message": f"Unknown platform: {platform}"}

    if not ESHIP_EMAIL or not ESHIP_PASSWORD:
        return {"status": "error", "message": "ESHIP_EMAIL/ESHIP_PASSWORD not set in .env"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--single-process"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        page = await ctx.new_page()

        try:
            # Auto-accept all confirm/alert dialogs (eShip uses confirm for eBay updates)
            page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

            # Login
            if not await _login(page):
                return {"status": "error", "message": "Login failed"}

            await asyncio.sleep(random.uniform(1, 2))

            # Go to inventory list
            await page.goto(f"{ESHIP_URL}/inventories", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Search strategy: SKU first (most reliable), then title keywords
            search_queries = []
            if sku:
                search_queries.append(sku)
            # Title-based fallback: try first 4 words > 2 chars, then first 2
            words = [w for w in ebay_title.split() if len(w) > 2][:4]
            if words:
                search_queries.append(" ".join(words))
                if len(words) > 2:
                    search_queries.append(" ".join(words[:2]))

            id_inputs = []
            used_query = ""
            for query in search_queries:
                logger.info(f"Searching eShip for: {query}")
                if not await _search_item(page, query):
                    continue
                id_inputs = await page.query_selector_all('input[name="inventories[][id]"]')
                if id_inputs:
                    used_query = query
                    break

            if not id_inputs:
                return {"status": "error", "message": f"No items found for: {search_queries}"}

            # Find the right item row
            target_idx = None
            name_links = await page.query_selector_all('td a[href*="/inventories/"][href*="/edit"]')

            if len(id_inputs) == 1:
                target_idx = 0
            else:
                # Match by title
                title_lower = ebay_title.lower()
                title_words = [w.lower() for w in ebay_title.split() if len(w) > 2]
                best_score = 0
                for i, link in enumerate(name_links):
                    text = (await link.inner_text()).strip().lower()
                    score = sum(1 for w in title_words if w in text)
                    if score > best_score:
                        best_score = score
                        target_idx = i

            if target_idx is None:
                return {"status": "error", "message": "Could not match item"}

            inventory_id = await id_inputs[target_idx].get_attribute("value")
            item_name = (await name_links[target_idx].inner_text()).strip()[:60] if target_idx < len(name_links) else "?"
            logger.info(f"Found eShip item: ID={inventory_id} name={item_name}")

            # Get all form field arrays
            qty_inputs = await page.query_selector_all('input[name="inventories[][quantity]"]')
            supplier_selects = await page.query_selector_all('select[name="inventories[][supplier_id]"]')
            url_inputs = await page.query_selector_all('input[name="inventories[][supplier_url]"]')
            price_inputs = await page.query_selector_all('input[name="inventories[][purchase_price]"]')

            # Update the target item's fields
            if target_idx < len(supplier_selects):
                await supplier_selects[target_idx].select_option(value=supplier_id)
                await asyncio.sleep(random.uniform(0.3, 0.7))

            if target_idx < len(url_inputs):
                url_field = url_inputs[target_idx]
                await url_field.click()
                await asyncio.sleep(0.2)
                await url_field.press("Meta+a")
                await url_field.fill(supplier_url)
                await url_field.evaluate("""el => {
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""")
                await asyncio.sleep(random.uniform(0.3, 0.7))

            if target_idx < len(price_inputs):
                price_field = price_inputs[target_idx]
                await price_field.click()
                await asyncio.sleep(0.2)
                await price_field.press("Meta+a")
                await price_field.type(str(purchase_price), delay=30)
                await price_field.evaluate("""el => {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""")
                await asyncio.sleep(random.uniform(0.3, 0.7))

            # STEP 1: Click "すべて保存" for supplier/url/price fields FIRST
            save_btn = await page.query_selector('input[value="すべて保存"]')
            if save_btn:
                await save_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(random.uniform(1, 2))
                logger.info("Saved supplier/url/price via すべて保存")

            # STEP 2: Re-query fields after page reload from すべて保存
            qty_inputs = await page.query_selector_all('input[name="inventories[][quantity]"]')
            id_inputs = await page.query_selector_all('input[name="inventories[][id]"]')

            # Re-find target_idx after reload
            target_idx = None
            for i, hid in enumerate(id_inputs):
                if await hid.get_attribute("value") == inventory_id:
                    target_idx = i
                    break

            # STEP 3: Update quantity LAST — this triggers eBay sync
            if target_idx is not None and target_idx < len(qty_inputs):
                qty_field = qty_inputs[target_idx]
                await qty_field.click(click_count=3)
                await asyncio.sleep(0.2)
                await qty_field.type(str(set_quantity), delay=50)
                await asyncio.sleep(random.uniform(0.3, 0.7))

                # Click the quantity-specific 更新 button (triggers confirm dialog + eBay API)
                qty_update_btn = await page.query_selector(
                    f'button.js-inventory-update-btn[data-id="{inventory_id}"][data-update_type="quantity"]'
                )
                if qty_update_btn:
                    await qty_update_btn.click()
                    await asyncio.sleep(random.uniform(2.0, 3.0))
                    logger.info(f"Clicked quantity 更新 button for ID {inventory_id}")
                else:
                    logger.warning(f"Quantity 更新 button not found for ID {inventory_id}")
            else:
                logger.warning(f"Could not re-find item {inventory_id} after save")

            # Verify after save
            saved_qty = None
            qty_after = await page.query_selector_all('input[name="inventories[][quantity]"]')
            if target_idx < len(qty_after):
                saved_qty = await qty_after[target_idx].input_value()
                logger.info(f"Quantity after save: {saved_qty}")

            return {
                "status": "ok",
                "message": f"Updated: {item_name}",
                "inventory_id": inventory_id,
                "supplier": platform,
                "price": purchase_price,
                "quantity": set_quantity,
                "verified_qty": saved_qty,
            }

        except Exception as e:
            logger.error(f"eShip automation error: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            await ctx.close()
            await browser.close()


# CLI usage
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 5:
        print("Usage: python eship.py <ebay_title> <supplier_url> <price> <platform>")
        print("Example: python eship.py 'TASCAM 424' 'https://auctions.yahoo.co.jp/...' 15000 yahoo_auction")
        sys.exit(1)

    result = asyncio.run(update_eship_item(
        ebay_title=sys.argv[1],
        supplier_url=sys.argv[2],
        purchase_price=int(sys.argv[3]),
        platform=sys.argv[4],
    ))
    print(result)
