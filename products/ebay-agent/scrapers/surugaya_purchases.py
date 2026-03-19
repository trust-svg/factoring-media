"""駿河屋 購入履歴スクレイパー

Playwrightで suruga-ya.jp の注文履歴を巡回し、
購入した商品情報を抽出して仕入れ台帳に登録する。

初回はブラウザで手動ログイン、2回目以降はCookieで自動ログイン。
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

COOKIE_DIR = Path(__file__).parent.parent / ".playwright"
COOKIE_FILE = COOKIE_DIR / "surugaya_cookies.json"

ORDERS_URL = "https://www.suruga-ya.jp/my/order_history"

SS_BASE = Path("/Users/Mac_air/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/総務関連/TrustLink/確定申告資料/輸出業/仕入れ履歴スクリーンショット")


async def _save_cookies(context):
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = await context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
    logger.info(f"駿河屋 cookies saved ({len(cookies)} entries)")


async def _load_cookies(context):
    if COOKIE_FILE.exists():
        cookies = json.loads(COOKIE_FILE.read_text())
        await context.add_cookies(cookies)
        logger.info(f"駿河屋 cookies loaded ({len(cookies)} entries)")
        return True
    return False


async def scrape_surugaya_purchases(
    on_progress=None,
    headless: bool = False,
) -> list[dict]:
    """駿河屋注文履歴を巡回して商品情報を取得"""
    from playwright.async_api import async_playwright

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
        )

        has_cookies = await _load_cookies(context)
        page = await context.new_page()

        if on_progress:
            on_progress("駿河屋注文履歴にアクセス中...", 0, 0)

        await page.goto(ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # ログインチェック
        if "login" in page.url or "signin" in page.url or "auth" in page.url:
            if headless and not has_cookies:
                await browser.close()
                raise RuntimeError("LOGIN_REQUIRED")

            if on_progress:
                on_progress("駿河屋にログインしてください（5分以内）...", 0, 0)

            try:
                for _ in range(150):
                    await asyncio.sleep(2)
                    current_url = page.url
                    if "login" not in current_url and "signin" not in current_url and "auth" not in current_url:
                        break
                else:
                    await browser.close()
                    raise RuntimeError("LOGIN_TIMEOUT")
                await asyncio.sleep(3)
            except RuntimeError:
                raise
            except Exception:
                await browser.close()
                raise RuntimeError("LOGIN_TIMEOUT")

            await _save_cookies(context)
            await page.goto(ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

        logger.info(f"注文履歴ページ: {page.url}")
        await asyncio.sleep(3)

        # ── ページネーションで全注文を読み込み ──
        all_orders = []
        page_num = 1

        while True:
            if on_progress:
                on_progress(f"注文履歴を読み込み中... ページ{page_num}", len(all_orders), 0)

            page_orders = await page.evaluate("""() => {
                const results = [];
                const seen = new Set();

                // 商品リンクを検索
                const links = document.querySelectorAll(
                    'a[href*="/product/detail/"], a[href*="/product/other/"], a[href*="/product/"]'
                );

                for (const link of links) {
                    const href = link.getAttribute('href') || '';
                    const idMatch = href.match(/\\/product\\/(?:detail\\/|other\\/)?([\\w-]+)/);
                    if (!idMatch) continue;

                    const itemId = idMatch[1];
                    if (seen.has(itemId)) continue;
                    seen.add(itemId);

                    const container = link.closest('tr') || link.closest('[class*="order"]')
                        || link.closest('[class*="item"]') || link.closest('li')
                        || link.parentElement;
                    const text = container ? (container.innerText || '') : '';

                    // タイトル
                    let title = (link.textContent || '').trim();
                    if (!title || title.length < 3) {
                        const img = (container || link).querySelector('img[alt]');
                        if (img && img.alt) title = img.alt;
                    }
                    if (!title || title.length < 3) continue;

                    // 価格
                    let price = 0;
                    const priceMatch = text.match(/[¥￥]\\s*([\\d,]+)/);
                    if (priceMatch) {
                        price = parseInt(priceMatch[1].replace(/,/g, ''), 10) || 0;
                    }

                    // 日付
                    let date = '';
                    const dateMatch = text.match(/(\\d{4})[/\\-\\.](\\d{1,2})[/\\-\\.](\\d{1,2})/);
                    if (dateMatch) {
                        date = dateMatch[1] + '-' + dateMatch[2].padStart(2, '0') + '-' + dateMatch[3].padStart(2, '0');
                    }

                    // 画像URL
                    let imageUrl = '';
                    const img = (container || link).querySelector('img');
                    if (img) imageUrl = img.src || '';

                    const itemUrl = href.startsWith('http') ? href : 'https://www.suruga-ya.jp' + href;

                    results.push({
                        item_id: itemId,
                        title: title.substring(0, 256),
                        price: price,
                        date: date,
                        item_url: itemUrl,
                        image_url: imageUrl,
                        cancelled: text.includes('キャンセル'),
                    });
                }
                return results;
            }""")

            all_orders.extend(page_orders)
            logger.info(f"ページ{page_num}: {len(page_orders)}件検出")

            # 次のページ
            has_next = await page.evaluate("""() => {
                const links = document.querySelectorAll('a');
                for (const a of links) {
                    const text = (a.textContent || '').trim();
                    if (text === '次へ' || text === '次のページ' || text === 'Next'
                        || text === '>' || text === '›' || text === '»') {
                        a.click();
                        return true;
                    }
                }
                const currentPage = document.querySelector('.current, .active, [aria-current="page"]');
                if (currentPage) {
                    const next = currentPage.nextElementSibling;
                    if (next && next.tagName === 'A') {
                        next.click();
                        return true;
                    }
                }
                return false;
            }""")

            if has_next:
                page_num += 1
                await asyncio.sleep(3)
            else:
                break

            if page_num > 50:
                break

        logger.info(f"全ページ読み込み完了: {len(all_orders)}件")

        # 重複除去
        seen_ids = set()
        unique_items = []
        for item in all_orders:
            if item["item_id"] not in seen_ids:
                seen_ids.add(item["item_id"])
                unique_items.append(item)

        total = len(unique_items)
        if on_progress:
            on_progress(f"{total} 件検出。商品ページから情報取得中...", 0, total)

        # ── 各商品ページでスクリーンショット撮影 ──
        for idx, item in enumerate(unique_items):
            if item.get("cancelled"):
                continue

            item_url = item["item_url"]
            item_id = item["item_id"]
            try:
                await page.goto(item_url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_selector('img[src*="suruga"], [class*="price"]', timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(1)

                # 画像URL補完
                if not item.get("image_url"):
                    try:
                        img_url = await page.evaluate("""() => {
                            const ogImg = document.querySelector('meta[property="og:image"]');
                            if (ogImg && ogImg.content) return ogImg.content;
                            const img = document.querySelector('img[src*="suruga"]');
                            if (img) return img.src;
                            return '';
                        }""")
                        if img_url:
                            item["image_url"] = img_url
                    except Exception:
                        pass

                # スクリーンショット
                item_date = item.get("date", "")
                year = item_date[:4] if item_date and len(item_date) >= 4 else str(datetime.now().year)
                ss_dir = SS_BASE / year / "駿河屋"
                ss_dir.mkdir(parents=True, exist_ok=True)
                ss_path = ss_dir / f"{item_id}.png"

                if not ss_path.exists():
                    try:
                        has_content = await page.evaluate("""() => {
                            const body = document.body.innerText || '';
                            return body.includes('¥') || body.length > 500;
                        }""")
                        if has_content:
                            await page.screenshot(path=str(ss_path), full_page=True)
                    except Exception as e:
                        logger.warning(f"Screenshot error ({item_id}): {e}")

                if ss_path.exists():
                    item["screenshot_path"] = str(ss_path)

            except Exception as e:
                logger.warning(f"Item page error ({item_id}): {e}")

            if on_progress and (idx + 1) % 5 == 0:
                on_progress(f"商品情報取得中: {idx+1}/{total}", idx + 1, total)
            await asyncio.sleep(0.5)

        results = [item for item in unique_items if not item.get("cancelled")]
        await _save_cookies(context)
        await browser.close()

    if on_progress:
        on_progress(f"完了: {len(results)} 件取得", len(results), len(results))

    return results
