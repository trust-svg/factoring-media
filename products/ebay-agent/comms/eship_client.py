"""eShip browser automation — create / update inventory items via Playwright.

deal-watcher/eship.py から移植。ebay-agent 配下に複製されており独立して動く。
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


def _extract_search_keyword(title: str) -> str:
    """タイトルから検索用キーワードを抽出。モデル番号優先、なければ先頭2語。"""
    tokens = re.split(r"[\s/,()[\]]+", title)
    candidates = [
        t.strip("-.")
        for t in tokens
        if len(t) >= 3 and re.search(r"[A-Za-z]", t) and re.search(r"\d", t)
    ]
    if candidates:
        letter_first = [c for c in candidates if c[0].isalpha()]
        pool = letter_first if letter_first else candidates
        return max(pool, key=len)
    return " ".join(title.split()[:2])


def _detect_platform_from_url(url: str) -> str:
    if "auctions.yahoo.co.jp" in url:
        return "ヤフオク"
    if "mercari.com" in url:
        return "メルカリ"
    if "paypayfleamarket" in url:
        return "Yahoo!フリマ"
    if "fril.jp" in url:
        return "ラクマ"
    if "hardoff" in url:
        return "ハードオフ"
    if "suruga-ya" in url:
        return "駿河屋"
    return ""


async def update_eship_source(
    eship_id: int,
    item_title: str,
    source_url: str,
    platform: str = "",
) -> dict:
    """eShip在庫アイテムの仕入れ元URLとプラットフォームを更新し、在庫数を1に設定する。

    Args:
        eship_id: eShip内部ID（inventory id）
        item_title: eShip商品名（検索に使用）
        source_url: 仕入れ元URL（メルカリ・ヤフオク等）
        platform: プラットフォーム名。省略時はURLから自動判定

    Returns:
        {"status": "ok", "message": ..., "inventory_id": ...} or error dict
    """
    if not platform:
        platform = _detect_platform_from_url(source_url)
    supplier_id = SUPPLIER_MAP.get(platform, "")
    if not supplier_id:
        return {"status": "error", "message": f"不明なプラットフォーム: {platform}"}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--single-process"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ja-JP"
        )
        page = await ctx.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        try:
            if not await _login(page):
                return {"status": "error", "message": "eShip ログイン失敗"}

            await page.goto(
                f"{ESHIP_URL}/inventories", wait_until="networkidle", timeout=20000
            )
            await asyncio.sleep(random.uniform(0.8, 1.5))

            # モデル番号キーワードで検索（4語AND検索より確実）
            query = _extract_search_keyword(item_title)
            search_input = await page.query_selector(
                'input[name="q[ebay_item_id_or_supplier_url_or_name_or_sku_or_memo_cont]"]'
            )
            if search_input and query:
                await search_input.fill(query)
                btn = await page.query_selector(
                    'input[type="submit"][value="検索"], button:has-text("検索")'
                )
                if btn:
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(random.uniform(0.8, 1.5))

            # eship_id で対象行を特定（複数ページを最大3ページまで探索）
            target_idx = None
            for page_num in range(1, 4):
                id_inputs = await page.query_selector_all(
                    'input[name="inventories[][id]"]'
                )
                for i, hid in enumerate(id_inputs):
                    val = await hid.get_attribute("value")
                    if val and int(val) == eship_id:
                        target_idx = i
                        break
                if target_idx is not None:
                    break
                # 次ページへ
                next_btn = await page.query_selector(
                    'a[rel="next"], .next a, a:has-text("次へ")'
                )
                if not next_btn:
                    break
                await next_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(random.uniform(0.8, 1.5))

            if target_idx is None:
                return {
                    "status": "error",
                    "message": f"eShip ID {eship_id} が見つかりません（検索: {query!r}）",
                }

            inv_id_str = str(eship_id)

            # supplier_url 更新
            url_inputs = await page.query_selector_all(
                'input[name="inventories[][supplier_url]"]'
            )
            if target_idx < len(url_inputs):
                f = url_inputs[target_idx]
                await f.click()
                await asyncio.sleep(0.2)
                await f.press("Meta+a")
                await f.fill(source_url)
                await f.evaluate(
                    "el => el.dispatchEvent(new Event('change', {bubbles:true}))"
                )

            # supplier_id (platform) 更新
            sup_selects = await page.query_selector_all(
                'select[name="inventories[][supplier_id]"]'
            )
            if target_idx < len(sup_selects):
                await sup_selects[target_idx].select_option(value=supplier_id)
                await asyncio.sleep(random.uniform(0.3, 0.6))

            # すべて保存
            save_btn = await page.query_selector('input[value="すべて保存"]')
            if save_btn:
                await save_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(random.uniform(1.0, 1.8))
                logger.info("eShip: supplier info saved for ID %d", eship_id)

            # ページ再取得後、対象行を ID で再特定
            id_inputs2 = await page.query_selector_all(
                'input[name="inventories[][id]"]'
            )
            target_idx2 = None
            for i, hid in enumerate(id_inputs2):
                val = await hid.get_attribute("value")
                if val and int(val) == eship_id:
                    target_idx2 = i
                    break

            if target_idx2 is None:
                return {"status": "error", "message": "保存後に対象行が見つかりません"}

            # 在庫数を 1 に設定
            qty_inputs = await page.query_selector_all(
                'input[name="inventories[][quantity]"]'
            )
            if target_idx2 < len(qty_inputs):
                f = qty_inputs[target_idx2]
                await f.click(click_count=3)
                await asyncio.sleep(0.2)
                await f.type("1", delay=50)
                await asyncio.sleep(random.uniform(0.3, 0.6))

            # 在庫数「更新」ボタン（eBay数量同期）
            qty_btn = await page.query_selector(
                f'button.js-inventory-update-btn[data-id="{inv_id_str}"][data-update_type="quantity"]'
            )
            if qty_btn:
                await qty_btn.click()
                await asyncio.sleep(random.uniform(2.0, 3.0))
                logger.info("eShip: quantity updated to 1 for ID %d", eship_id)
            else:
                logger.warning(
                    "eShip: quantity 更新ボタンが見つかりません (ID %d)", eship_id
                )

            return {
                "status": "ok",
                "message": f"eShip更新完了: 仕入元={platform}, 在庫=1",
                "inventory_id": eship_id,
            }

        except Exception as e:
            logger.error("eShip update_source error: %s", e)
            return {"status": "error", "message": str(e)}
        finally:
            await ctx.close()
            await browser.close()
