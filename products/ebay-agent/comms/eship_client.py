"""eShip browser automation — create new inventory items via Playwright.

deal-watcher/eship.py から移植。create_eship_item のみ提供。
本ファイルは ebay-agent 配下に複製されており、deal-watcher と独立して動く。
"""

from __future__ import annotations

import asyncio
import logging
import random
import re

from playwright.async_api import async_playwright

from config import ESHIP_EMAIL, ESHIP_PASSWORD

logger = logging.getLogger(__name__)


ESHIP_URL = "https://eship-tool.com"

# ebay-agent の jp_platform 表記 → eShip supplier_id
SUPPLIER_MAP = {
    "ヤフオク": "20086",
    "yahoo_auction": "20086",
    "yahoo_auctions": "20086",
    "メルカリ": "20083",
    "mercari": "20083",
    "Yahoo!フリマ": "20090",
    "Yahooフリマ": "20090",
    "yahoo_fleamarket": "20090",
    "paypay_flea": "20090",
    "ラクマ": "20085",
    "rakuma": "20085",
    "ハードオフ": "20089",
    "hardoff": "20089",
    "オフモール": "20089",
    "offmall": "20089",
    "駿河屋": "20088",
    "surugaya": "20088",
}


async def _login(page) -> bool:
    await page.goto(
        f"{ESHIP_URL}/users/sign_in", wait_until="networkidle", timeout=30000
    )
    await page.fill('input[name="user[email]"]', ESHIP_EMAIL)
    await page.fill('input[name="user[password]"]', ESHIP_PASSWORD)
    await page.click('input[type="submit"]')
    await page.wait_for_load_state("networkidle", timeout=15000)
    return "/users/sign_in" not in page.url


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

    All items are created as drafts (quantity=1). FedEx/北米 fixed. Promoted rate 2%.
    Returns: {"status": "ok", "inventory_id": ..., "message": ...} or
             {"status": "error", "message": ...}
    """
    if not ESHIP_EMAIL or not ESHIP_PASSWORD:
        return {"status": "error", "message": "ESHIP credentials not set"}

    supplier_id = SUPPLIER_MAP.get(platform, "")

    # Condition mapping (eShip ID: 1=新品 / 2=Used)
    condition_id = "1" if ("new" in condition.lower() or "新品" in condition) else "2"

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

            new_url = (
                f"{ESHIP_URL}/inventories/new"
                "?utf8=%E2%9C%93&store_account_id=1410&commit=%E9%80%B2%E3%82%80"
            )
            await page.goto(new_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(random.uniform(1, 2))

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

            await _fill("inventory[name]", title[:100])
            await _fill("inventory[supplier_url]", supplier_url)
            await _fill("inventory[purchase_price]", purchase_price)
            await _fill("inventory[sku]", sku)
            await _fill("inventory[title]", title[:80])
            await _fill("inventory[quantity]", "1")
            await _fill("inventory[condition_description]", condition_description)
            await _fill("inventory[image_url]", image_url)
            await _fill("inventory[memo]", memo[:200])
            await _fill("inventory[promoted_rate]", "2")

            if ebay_item_id:
                await _fill("inventory[ebay_item_id]", ebay_item_id)
            if selling_price_usd > 0:
                await _fill("inventory[selling_price]", int(selling_price_usd))
            if category_id:
                await _fill("inventory[ebay_category_id]", category_id)
            if category_path:
                await _fill("inventory[ebay_category_path]", category_path)

            if supplier_id:
                await _select("inventory[supplier_id]", supplier_id)
            await _select("inventory[item_condition_id]", condition_id)
            await _select("inventory[stock_condition_id]", condition_id)

            await _select("inventory[shipping_method_id]", "4")  # FedEx
            await asyncio.sleep(1)
            await _select("inventory[shipping_area_id]", "2")  # 北米

            if height_cm > 0 and length_cm > 0 and width_cm > 0:
                await _fill("inventory[height]", height_cm)
                await _fill("inventory[length]", length_cm)
                await _fill("inventory[width]", width_cm)
                # Volume weight = L x W x H / 5000 (FedEx, in grams)
                volume_weight = int(length_cm * width_cm * height_cm / 5000 * 1000)
                await _fill("inventory[weight]", volume_weight)
                await _fill("inventory[volume_weight]", volume_weight)

            await asyncio.sleep(random.uniform(0.5, 1))

            submit_btn = await page.query_selector(
                'input[type="submit"], button[type="submit"]'
            )
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("networkidle", timeout=30000)
                await asyncio.sleep(random.uniform(1, 2))

            if "/inventories" in page.url and "/new" not in page.url:
                m = re.search(r"/inventories/(\d+)", page.url)
                inv_id = m.group(1) if m else ""
                logger.info("eShip item created: %s (ID: %s)", title[:40], inv_id)
                return {
                    "status": "ok",
                    "message": f"Created: {title[:50]}",
                    "inventory_id": inv_id,
                }

            error_el = await page.query_selector(
                ".alert-danger, .error, #error_explanation"
            )
            error_msg = await error_el.inner_text() if error_el else ""
            return {
                "status": "error",
                "message": (
                    f"Form submission may have failed. URL: {page.url}. {error_msg}"
                ),
            }
        except Exception as e:
            logger.error("eShip create error: %s", e)
            return {"status": "error", "message": str(e)}
        finally:
            await ctx.close()
            await browser.close()
