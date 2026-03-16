"""メルカリ購入履歴スクレイパー

Playwrightで jp.mercari.com/mypage/purchases を巡回し、
購入した商品情報を抽出して仕入れ台帳に登録する。

初回はブラウザが開いてメルカリログインが必要。
2回目以降はCookieで自動ログイン。
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COOKIE_DIR = Path(__file__).parent.parent / ".playwright"
COOKIE_FILE = COOKIE_DIR / "mercari_cookies.json"

PURCHASES_URL = "https://jp.mercari.com/mypage/purchases"
LOGIN_URL_PREFIX = "https://login.jp.mercari.com"

# スクリーンショット保存先
SS_BASE = Path("/Users/Mac_air/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/総務関連/TrustLink/確定申告資料/輸出業/仕入れ履歴スクリーンショット")


async def _save_cookies(context):
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = await context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
    logger.info(f"Mercari cookies saved ({len(cookies)} entries)")


async def _load_cookies(context):
    if COOKIE_FILE.exists():
        cookies = json.loads(COOKIE_FILE.read_text())
        await context.add_cookies(cookies)
        logger.info(f"Mercari cookies loaded ({len(cookies)} entries)")
        return True
    return False


async def scrape_mercari_purchases(
    on_progress=None,
    headless: bool = False,
) -> list[dict]:
    """メルカリ購入履歴を巡回して商品情報を取得"""
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
            on_progress("メルカリ購入履歴にアクセス中...", 0, 0)

        await page.goto(PURCHASES_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # ログインチェック
        if "login" in page.url:
            if headless and not has_cookies:
                await browser.close()
                raise RuntimeError("LOGIN_REQUIRED")

            if on_progress:
                on_progress("メルカリログインが必要です。ブラウザでログインしてください...", 0, 0)

            try:
                await page.wait_for_url(
                    lambda url: "mypage" in url or "purchases" in url,
                    timeout=300000,
                )
                await asyncio.sleep(3)
            except Exception:
                await browser.close()
                raise RuntimeError("LOGIN_TIMEOUT")

            await _save_cookies(context)
            await page.goto(PURCHASES_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

        # ── スクロールして全件読み込み ──
        logger.info(f"購入履歴ページ: {page.url}")

        # ページが完全にレンダリングされるまで待機
        await asyncio.sleep(5)

        # 初期リンク数を確認
        initial_count = await page.evaluate(
            """document.querySelectorAll('a[href*="/transaction/"]').length"""
        )
        logger.info(f"初期リンク数: {initial_count}")

        if initial_count == 0:
            # ページがまだ読み込まれていない場合、再読み込み
            logger.info("リンクが0件 — リロードして再試行")
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            initial_count = await page.evaluate(
                """document.querySelectorAll('a[href*="/transaction/"]').length"""
            )
            logger.info(f"リロード後リンク数: {initial_count}")

        if on_progress:
            on_progress(f"購入履歴をスクロール読み込み中... {initial_count}件", initial_count, 0)

        prev_count = initial_count
        for scroll_i in range(50):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            current_count = await page.evaluate(
                """document.querySelectorAll('a[href*="/transaction/"]').length"""
            )
            if current_count == prev_count:
                break
            prev_count = current_count
            if on_progress:
                on_progress(f"スクロール読み込み中... {current_count}件", current_count, 0)

        logger.info(f"スクロール完了: {prev_count}件")

        # ── 一覧からアイテム情報を抽出 ──
        items_data = await page.evaluate("""() => {
            const results = [];
            const links = document.querySelectorAll('a[href*="/transaction/"]');

            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const idMatch = href.match(/\\/transaction\\/(m\\d+)/);
                if (!idMatch) continue;

                const itemId = idMatch[1];
                const container = link.closest('li') || link.parentElement;
                if (!container) continue;

                const text = container.innerText || '';
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                // 商品名: 最初の意味のある行
                let title = '';
                let brand = '';
                let date = '';

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    // 日付パターン
                    const dm = line.match(/(\\d{4})\\/(\\d{2})\\/(\\d{2})\\s+\\d{2}:\\d{2}/);
                    if (dm) {
                        date = dm[1] + '-' + dm[2] + '-' + dm[3];
                        // 日付の前の行がブランド、その前が商品名
                        if (i >= 2) {
                            brand = lines[i-1];
                            title = lines[i-2];
                        } else if (i >= 1) {
                            title = lines[i-1];
                        }
                        break;
                    }
                }

                // ステータス行を除外
                const skipTexts = ['取引中の商品', '購入した商品', '発送完了', '受取完了',
                                   '取引完了', '評価完了', 'キャンセル'];
                if (skipTexts.includes(title)) {
                    // タイトルがステータスだった場合、次の行を使う
                    for (const line of lines) {
                        if (!skipTexts.includes(line) && !line.match(/\\d{4}\\//) && line.length > 3) {
                            title = line;
                            break;
                        }
                    }
                }

                // キャンセル判定
                const cancelled = text.includes('キャンセル');

                // 画像URL
                let imageUrl = '';
                const img = container.querySelector('img[src*="static.mercdn"]');
                if (img) imageUrl = img.src;

                if (title && title.length > 2) {
                    results.push({
                        item_id: itemId,
                        title: title.substring(0, 256),
                        brand: brand,
                        date: date,
                        transaction_url: 'https://jp.mercari.com' + href,
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
            on_progress(f"{total} 件検出。取引ページから価格を取得中...", 0, total)

        # ── 各商品ページから価格・送料を取得 + スクリーンショット ──
        cancelled_count = 0
        for idx, item in enumerate(unique_items):
            if item.get("cancelled"):
                cancelled_count += 1
                continue

            item_id = item["item_id"]
            item_url = f"https://jp.mercari.com/item/{item_id}"
            try:
                await page.goto(item_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                # 価格・送料を取得
                price_info = await page.evaluate("""() => {
                    const body = document.body.innerText || '';
                    const lines = body.split('\\n').map(l => l.trim());

                    let price = 0;
                    let shipping = 0;

                    // 最初の "¥XX,XXX" が商品価格
                    const priceMatch = body.match(/¥([\\d,]+)/);
                    if (priceMatch) {
                        price = parseInt(priceMatch[1].replace(/,/g, ''), 10) || 0;
                    }

                    // "送料込み" → 購入者の送料負担なし
                    // "着払い" or "送料 ¥XXX" → 購入者負担
                    if (body.includes('着払い') || body.includes('購入者負担')) {
                        const shipMatch = body.match(/送料\\s*¥([\\d,]+)/);
                        if (shipMatch) {
                            shipping = parseInt(shipMatch[1].replace(/,/g, ''), 10) || 0;
                        }
                    }

                    return { price, shipping };
                }""")

                item["price"] = price_info.get("price", 0)
                item["shipping"] = price_info.get("shipping", 0)

                # 商品ページURLを保存（リンク用）
                item["item_url"] = item_url

                # ── スクリーンショット ──
                item_date = item.get("date", "")
                year = item_date[:4] if item_date and len(item_date) >= 4 else str(datetime.now().year)
                ss_dir = SS_BASE / year / "メルカリ"
                ss_dir.mkdir(parents=True, exist_ok=True)
                ss_path = ss_dir / f"{item_id}.png"

                if not ss_path.exists():
                    try:
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

        # キャンセル除外
        results = [item for item in unique_items if not item.get("cancelled")]

        await _save_cookies(context)
        await browser.close()

    if on_progress:
        msg = f"完了: {len(results)} 件取得"
        if cancelled_count > 0:
            msg += f"（キャンセル {cancelled_count} 件除外）"
        on_progress(msg, len(results), len(results))

    return results
