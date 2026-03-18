"""ラクマ購入履歴スクレイパー

Playwrightで fril.jp の購入履歴を巡回し、
購入した商品情報を抽出して仕入れ台帳に登録する。

楽天ログインが必要（初回はブラウザで手動ログイン、
2回目以降はCookieで自動ログイン）。
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

COOKIE_DIR = Path(__file__).parent.parent / ".playwright"
COOKIE_FILE = COOKIE_DIR / "rakuma_cookies.json"

PURCHASES_URL = "https://fril.jp/mypage/purchases"

# スクリーンショット保存先
SS_BASE = Path("/Users/Mac_air/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/総務関連/TrustLink/確定申告資料/輸出業/仕入れ履歴スクリーンショット")


async def _save_cookies(context):
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = await context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
    logger.info(f"ラクマ cookies saved ({len(cookies)} entries)")


async def _load_cookies(context):
    if COOKIE_FILE.exists():
        cookies = json.loads(COOKIE_FILE.read_text())
        await context.add_cookies(cookies)
        logger.info(f"ラクマ cookies loaded ({len(cookies)} entries)")
        return True
    return False


async def scrape_rakuma_purchases(
    on_progress=None,
    headless: bool = False,
) -> list[dict]:
    """ラクマ購入履歴を巡回して商品情報を取得"""
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
            on_progress("ラクマ購入履歴にアクセス中...", 0, 0)

        await page.goto(PURCHASES_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # ログインチェック
        if "login" in page.url or "grp" in page.url or "auth" in page.url:
            if headless and not has_cookies:
                await browser.close()
                raise RuntimeError("LOGIN_REQUIRED")

            if on_progress:
                on_progress("楽天ログインが必要です。ブラウザでログインしてください...", 0, 0)

            try:
                await page.wait_for_url(
                    lambda url: "mypage" in url or "purchases" in url or "fril.jp" in url,
                    timeout=300000,
                )
                await asyncio.sleep(3)
            except Exception:
                await browser.close()
                raise RuntimeError("LOGIN_TIMEOUT")

            await _save_cookies(context)
            await page.goto(PURCHASES_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

        # ── 「もっと見る」ボタン + スクロールで全件読み込み ──
        logger.info(f"購入履歴ページ: {page.url}")
        await asyncio.sleep(5)

        # ラクマの購入履歴リンクパターン
        initial_count = await page.evaluate(
            """document.querySelectorAll('a[href*="item.fril.jp"], a[href*="/transaction/"]').length"""
        )
        logger.info(f"初期リンク数: {initial_count}")

        if on_progress:
            on_progress(f"購入履歴を読み込み中... {initial_count}件", initial_count, 0)

        prev_count = initial_count
        no_change_streak = 0
        click_count = 0

        for loop_i in range(500):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            # 「もっと見る」ボタンを探してクリック
            clicked = False
            try:
                load_more = await page.evaluate("""() => {
                    const buttons = [...document.querySelectorAll('button, a, div[role="button"]')];
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').trim();
                        if (text === 'もっと見る' || text === 'もっとみる' || text === 'さらに表示'
                            || text === 'Load more' || text === '次のページ') {
                            btn.scrollIntoView();
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if load_more:
                    clicked = True
                    click_count += 1
                    await asyncio.sleep(3)
            except Exception:
                pass

            current_count = await page.evaluate(
                """document.querySelectorAll('a[href*="item.fril.jp"], a[href*="/transaction/"]').length"""
            )

            if current_count > prev_count:
                no_change_streak = 0
                prev_count = current_count
                if on_progress:
                    on_progress(f"読み込み中... {current_count}件", current_count, 0)
            else:
                no_change_streak += 1
                if not clicked and no_change_streak >= 3:
                    break
                await asyncio.sleep(2)

        logger.info(f"読み込み完了: {prev_count}件（{loop_i + 1}ループ, ボタン{click_count}回クリック）")

        # ── 一覧からアイテム情報を抽出 ──
        items_data = await page.evaluate("""() => {
            const results = [];
            const cards = document.querySelectorAll('a[href*="item.fril.jp"], a[href*="/transaction/"]');

            for (const card of cards) {
                const href = card.getAttribute('href') || '';
                // item ID を抽出
                const idMatch = href.match(/item\\.fril\\.jp\\/([a-f0-9]+)/) || href.match(/\\/transaction\\/([a-f0-9]+)/);
                if (!idMatch) continue;

                const itemId = idMatch[1];
                const container = card.closest('li') || card.closest('[class*="item"]') || card.parentElement;
                if (!container) continue;

                const text = container.innerText || '';

                // タイトル
                let title = '';
                const img = container.querySelector('img[alt]');
                if (img && img.alt && img.alt.length > 2) {
                    title = img.alt;
                }
                if (!title) {
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 2);
                    for (const line of lines) {
                        if (!line.match(/^[¥\\d,]+$/) && !line.includes('取引') && !line.includes('評価')
                            && !line.includes('SOLD') && !line.includes('購入')) {
                            title = line;
                            break;
                        }
                    }
                }

                // 価格
                let price = 0;
                const priceMatch = text.match(/[¥￥]\\s*([\\d,]+)/);
                if (priceMatch) {
                    price = parseInt(priceMatch[1].replace(/,/g, ''), 10) || 0;
                }

                // 日付
                let date = '';
                const dateMatch = text.match(/(\\d{4})[/\\-](\\d{1,2})[/\\-](\\d{1,2})/);
                if (dateMatch) {
                    date = dateMatch[1] + '-' + dateMatch[2].padStart(2, '0') + '-' + dateMatch[3].padStart(2, '0');
                }

                // 画像URL
                let imageUrl = '';
                if (img) imageUrl = img.src || '';

                // キャンセル判定
                const cancelled = text.includes('キャンセル');

                const itemUrl = href.startsWith('http') ? href : 'https://item.fril.jp/' + itemId;

                if (title && title.length > 2) {
                    results.push({
                        item_id: itemId,
                        title: title.substring(0, 256),
                        price: price,
                        date: date,
                        item_url: itemUrl,
                        image_url: imageUrl,
                        cancelled: cancelled,
                    });
                }
            }
            return results;
        }""")

        logger.info(f"一覧から {len(items_data)} 件検出")

        # 重複除去
        seen_ids = set()
        unique_items = []
        for item in items_data:
            if item["item_id"] not in seen_ids:
                seen_ids.add(item["item_id"])
                unique_items.append(item)

        total = len(unique_items)
        if on_progress:
            on_progress(f"{total} 件検出。詳細ページから情報を取得中...", 0, total)

        # ── 各商品ページから詳細取得 + スクリーンショット ──
        for idx, item in enumerate(unique_items):
            if item.get("cancelled"):
                continue

            item_id = item["item_id"]
            item_url = item["item_url"]
            try:
                await page.goto(item_url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_selector('img[src*="fril"], [class*="price"]', timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(1)

                # 価格が0の場合
                if not item.get("price"):
                    price_info = await page.evaluate("""() => {
                        const body = document.body.innerText || '';
                        const priceMatch = body.match(/[¥￥]\\s*([\\d,]+)/);
                        return priceMatch ? parseInt(priceMatch[1].replace(/,/g, ''), 10) : 0;
                    }""")
                    item["price"] = price_info

                # 画像URLが未取得の場合
                if not item.get("image_url"):
                    try:
                        img_url = await page.evaluate("""() => {
                            const ogImg = document.querySelector('meta[property="og:image"]');
                            if (ogImg && ogImg.content) return ogImg.content;
                            const img = document.querySelector('img[src*="fril"]');
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
                ss_dir = SS_BASE / year / "ラクマ"
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
                            logger.info(f"SS撮影: {item_id}")
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
