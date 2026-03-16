"""ヤフオク落札一覧スクレイパー

Playwrightで auctions.yahoo.co.jp/my/won を巡回し、
一覧ページから直接商品情報を抽出して仕入れ台帳に登録する。

初回はブラウザが開いてYahooログインが必要。
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
COOKIE_FILE = COOKIE_DIR / "yahoo_cookies.json"

WON_LIST_URL = "https://auctions.yahoo.co.jp/my/won"
LOGIN_URL_PREFIX = "https://login.yahoo.co.jp"

CANCEL_KEYWORDS = ["キャンセル", "取引中止", "落札者都合により削除",
                   "出品者都合により削除", "取り消し", "返金済み", "削除済み"]

# 商品名ではないUI文言
JUNK_TEXTS = {"取引ナビ", "取引連絡", "取引メッセージがあります", "評価",
              "LYPプレミアム利用ガイド", "ヘルプ", "ガイド", "Yahoo! JAPAN",
              "ヤフオク!", "マイ・オークション", "商品が発送されました",
              "発送連絡待ちです", "支払い手続きをしてください", "受け取り連絡待ちです",
              "円", "送料無料", "ストア", ""}


async def _save_cookies(context):
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookies = await context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
    logger.info(f"Cookies saved ({len(cookies)} entries)")


async def _load_cookies(context):
    if COOKIE_FILE.exists():
        cookies = json.loads(COOKIE_FILE.read_text())
        await context.add_cookies(cookies)
        logger.info(f"Cookies loaded ({len(cookies)} entries)")
        return True
    return False


def _is_cancelled(text: str) -> bool:
    return any(kw in text for kw in CANCEL_KEYWORDS)


async def scrape_yahoo_won(
    on_progress=None,
    max_pages: int = 50,
    headless: bool = False,
) -> list[dict]:
    """ヤフオク落札一覧ページから直接商品情報を抽出"""
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
            on_progress("落札一覧ページにアクセス中...", 0, 0)

        await page.goto(WON_LIST_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # ログインチェック
        if LOGIN_URL_PREFIX in page.url:
            if headless and not has_cookies:
                await browser.close()
                raise RuntimeError("LOGIN_REQUIRED")

            if on_progress:
                on_progress("Yahooログインが必要です。ブラウザでログインしてください...", 0, 0)

            try:
                await page.wait_for_url(
                    lambda url: "auctions.yahoo.co.jp" in url and "login" not in url,
                    timeout=300000,
                )
                await asyncio.sleep(2)
            except Exception:
                await browser.close()
                raise RuntimeError("LOGIN_TIMEOUT")

            await _save_cookies(context)
            await page.goto(WON_LIST_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

        # ── 一覧ページを巡回 ──
        page_num = 1
        seen_aids: set[str] = set()
        cancelled_count = 0

        while page_num <= max_pages:
            if on_progress:
                on_progress(f"一覧ページ {page_num} を読み込み中...", len(results), 0)

            page_url = page.url
            logger.info(f"一覧ページ {page_num}: {page_url}")

            # デバッグHTML保存（1ページ目のみ）
            if page_num == 1:
                try:
                    html = await page.content()
                    debug_file = COOKIE_DIR / "debug_won_page.html"
                    debug_file.write_text(html, encoding="utf-8")
                    logger.info(f"デバッグHTML保存: {debug_file}")
                except Exception as e:
                    logger.warning(f"デバッグHTML保存失敗: {e}")

            # ページ内の商品を抽出
            items_on_page = await _extract_items_from_list(page)
            logger.info(f"ページ {page_num}: {len(items_on_page)} 件検出")

            new_on_page = 0
            for item in items_on_page:
                aid = item.get("auction_id", "")
                if aid and aid in seen_aids:
                    continue
                if aid:
                    seen_aids.add(aid)

                if item.get("cancelled"):
                    cancelled_count += 1
                    logger.info(f"キャンセル除外: {item.get('title', '?')[:40]}")
                    continue

                if item.get("title"):
                    results.append(item)
                    new_on_page += 1

            logger.info(f"ページ {page_num}: {new_on_page} 件追加（累計 {len(results)}）")

            if len(items_on_page) == 0:
                logger.info("アイテムなし、巡回終了")
                break

            # 次のページ
            next_el = await _find_next_page(page)
            if not next_el:
                logger.info(f"ページネーション終了: {page_num}ページ目")
                break

            await next_el.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(1.5)
            page_num += 1

        # ── スクリーンショット撮影（ページ全体） ──
        if on_progress:
            on_progress(f"スクリーンショット撮影中...", 0, len(results))

        # Google Drive の確定申告資料フォルダに保存（年/プラットフォーム別）
        ss_base = Path("/Users/Mac_air/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/総務関連/TrustLink/確定申告資料/輸出業/仕入れ履歴スクリーンショット")

        for idx, item in enumerate(results):
            aid = item.get("auction_id", "")
            if not aid:
                continue
            # 仕入日から年を取得（なければ今年）
            item_date = item.get("date", "")
            year = item_date[:4] if item_date and len(item_date) >= 4 else str(datetime.now().year)
            screenshot_dir = ss_base / year / "ヤフオク"
            screenshot_dir.mkdir(parents=True, exist_ok=True)

            ss_path = screenshot_dir / f"{aid}.png"
            if ss_path.exists():
                item["screenshot_path"] = str(ss_path)
                continue

            auction_url = f"https://auctions.yahoo.co.jp/jp/auction/{aid}"
            try:
                # ── 取引ナビから送料を取得 ──
                tx_url = item.get("transaction_url", "")
                if tx_url and item.get("shipping", 0) == 0:
                    try:
                        await page.goto(tx_url, wait_until="domcontentloaded", timeout=20000)
                        await asyncio.sleep(2)

                        # ストア取引ページの場合「お届け情報・お支払い情報などを確認する」を展開
                        expand_btn = await page.query_selector('text=お届け情報・お支払い情報などを確認する')
                        if expand_btn:
                            await expand_btn.click()
                            await asyncio.sleep(2)

                        ship_cost = await page.evaluate("""() => {
                            const body = document.body.innerText || '';
                            const lines = body.split('\\n').map(l => l.trim());

                            // パターン1: "（送料：1,400円）" — 通常出品の取引ナビ
                            const m1 = body.match(/送料[：:]\\s*([\\d,]+)\\s*円/);
                            if (m1) {
                                const v = parseInt(m1[1].replace(/,/g, ''), 10) || 0;
                                if (v > 0) return v;
                            }

                            // パターン2: "送料" の次行に "1,740円" — ストア取引ページ
                            for (let i = 0; i < lines.length; i++) {
                                if (lines[i] === '送料' && lines[i+1]) {
                                    const m2 = lines[i+1].match(/^([\\d,]+)\\s*円$/);
                                    if (m2) return parseInt(m2[1].replace(/,/g, ''), 10) || 0;
                                }
                            }

                            if (body.includes('送料無料') || body.includes('送料：0円')) return 0;
                            return 0;
                        }""")
                        if ship_cost > 0:
                            item["shipping"] = ship_cost
                            logger.info(f"送料取得(取引ナビ): {aid} → ¥{ship_cost}")
                    except Exception as e:
                        logger.warning(f"取引ナビ送料取得失敗 ({aid}): {e}")

                # ── 商品ページでスクリーンショット撮影 ──
                await page.goto(auction_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                await page.screenshot(path=str(ss_path), full_page=True)
                item["screenshot_path"] = str(ss_path)
                logger.info(f"SS撮影: {aid}")
            except Exception as e:
                logger.warning(f"Screenshot error ({aid}): {e}")

            if on_progress and (idx + 1) % 5 == 0:
                on_progress(f"スクリーンショット: {idx+1}/{len(results)}", idx+1, len(results))

            await asyncio.sleep(0.5)

        await _save_cookies(context)
        await browser.close()

    if on_progress:
        msg = f"完了: {len(results)} 件取得"
        if cancelled_count > 0:
            msg += f"（キャンセル {cancelled_count} 件除外）"
        on_progress(msg, len(results), len(results))

    return results


async def _extract_items_from_list(page) -> list[dict]:
    """落札一覧ページのli要素から商品情報を抽出

    ヤフオク落札一覧のHTML構造（2026年3月時点）:
    - 各商品は <li class="sc-e4f5438-0 ..."> で区切られる
    - 商品名: 最も長いテキスト行 or <img alt="商品名" src="*auctions.c.yimg.jp*">
    - 価格: "XX,XXX" + "円" の行
    - 日付: "M/D HH:MM" 形式
    - 商品ID: "商品ID：XXXXX"
    """

    junk_set = list(JUNK_TEXTS)
    cancel_kws = list(CANCEL_KEYWORDS)

    items = await page.evaluate("""(config) => {
        const { junkTexts, cancelKeywords } = config;
        const results = [];

        // li要素をすべて取得（アイテムコンテナ）
        const allLis = document.querySelectorAll('li');

        for (const li of allLis) {
            // 商品IDがあるかチェック（「商品ID：xxx」テキスト）
            const fullText = li.textContent || '';
            const idMatch = fullText.match(/商品ID[：:]\\s*([a-zA-Z0-9]+)/);
            if (!idMatch) continue;  // 商品liではない

            const auctionId = idMatch[1];

            // テキスト行を抽出
            const textContent = li.innerText || '';
            const lines = textContent.split('\\n')
                .map(l => l.trim())
                .filter(l => l.length > 0);

            // キャンセル判定
            const cancelled = cancelKeywords.some(kw => fullText.includes(kw));

            // 商品名を特定 — 以下の優先度:
            // 1. <img alt="..." src="*auctions.c.yimg.jp*"> のalt属性
            // 2. テキスト行の中で最も長い有効なテキスト
            let title = '';

            // 方法1: 商品画像のalt
            const imgs = li.querySelectorAll('img[alt]');
            for (const img of imgs) {
                const src = img.src || '';
                const alt = (img.alt || '').trim();
                if (src.includes('auctions.c.yimg.jp') && alt.length > 5) {
                    title = alt;
                    break;
                }
            }

            // 方法2: オークションページリンクのテキスト
            if (!title) {
                const auctionLinks = li.querySelectorAll('a[href*="auctions.yahoo.co.jp/jp/auction/"]');
                for (const a of auctionLinks) {
                    const t = a.textContent.trim();
                    if (t.length > 5 && !junkTexts.includes(t)) {
                        title = t;
                        break;
                    }
                }
            }

            // 方法3: 最も長い非ゴミテキスト行
            if (!title) {
                let longest = '';
                for (const line of lines) {
                    if (line.length > longest.length
                        && !junkTexts.includes(line)
                        && !line.match(/^[\\d,]+$/)     // 数字だけの行は除外
                        && !line.match(/^\\d+\\/\\d+/)     // 日付行は除外
                        && !line.startsWith('商品ID')
                        && !line.includes('プレミアム')
                        && !line.includes('利用ガイド')
                        && line.length > 5) {
                        longest = line;
                    }
                }
                title = longest;
            }

            // 価格: "XX,XXX" の行 + 次の行が "円"、 または "XX,XXX円"
            let price = 0;
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                const nextLine = lines[i+1] || '';

                // パターン1: "XX,XXX" + "円"
                if (/^[\\d,]+$/.test(line) && nextLine === '円') {
                    price = parseInt(line.replace(/,/g, ''), 10) || 0;
                    break;
                }
                // パターン2: "XX,XXX円" 一体型
                const pm = line.match(/^([\\d,]+)\\s*円$/);
                if (pm) {
                    price = parseInt(pm[1].replace(/,/g, ''), 10) || 0;
                    break;
                }
            }

            // 日付: "M/D HH:MM" 形式
            let date = '';
            for (const line of lines) {
                // "3/14 20:42" 形式
                const dm = line.match(/^(\\d{1,2})\\/(\\d{1,2})\\s+\\d{1,2}:\\d{2}$/);
                if (dm) {
                    const month = parseInt(dm[1], 10);
                    const day = parseInt(dm[2], 10);
                    const now = new Date();
                    let year = now.getFullYear();
                    // 現在月より大きい月なら前年（例: 現在3月で12月のデータ→前年）
                    if (month > now.getMonth() + 1) {
                        year -= 1;
                    }
                    date = year + '-' + dm[1].padStart(2, '0') + '-' + dm[2].padStart(2, '0');
                    break;
                }
                // "2026/3/14 20:42" 形式
                const dm2 = line.match(/(\\d{4})\\/(\\d{1,2})\\/(\\d{1,2})/);
                if (dm2) {
                    date = dm2[1] + '-' + dm2[2].padStart(2, '0') + '-' + dm2[3].padStart(2, '0');
                    break;
                }
            }

            // URL
            let url = '';
            const aLink = li.querySelector('a[href*="auctions.yahoo.co.jp/jp/auction/' + auctionId + '"]');
            if (aLink) {
                url = aLink.href;
            }

            // 送料
            let shipping = 0;
            const hasFreeship = fullText.includes('送料無料');
            if (!hasFreeship) {
                // "送料 1,200円" or "送料：1,200円" パターン
                const shipMatch = fullText.match(/送料[：:]?\\s*([\\d,]+)\\s*円/);
                if (shipMatch) {
                    shipping = parseInt(shipMatch[1].replace(/,/g, ''), 10) || 0;
                }
                // テキスト行に "送料" + 数字行パターン
                if (shipping === 0) {
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].includes('送料') && !lines[i].includes('無料')) {
                            // 同じ行から
                            const sm = lines[i].match(/([\\d,]+)\\s*円/);
                            if (sm) {
                                shipping = parseInt(sm[1].replace(/,/g, ''), 10) || 0;
                                break;
                            }
                            // 次の行から
                            if (lines[i+1]) {
                                const sm2 = lines[i+1].match(/^([\\d,]+)(\\s*円)?$/);
                                if (sm2) {
                                    shipping = parseInt(sm2[1].replace(/,/g, ''), 10) || 0;
                                    break;
                                }
                            }
                        }
                    }
                }
            }

            // ストア判定
            const isStore = lines.includes('ストア') || fullText.includes('ストア出品');

            // 消費税 — 明示的に「消費税 X円」と表示されている場合のみ
            // ストア出品の落札価格は税込なので、別途加算しない
            let tax = 0;
            const taxMatch = fullText.match(/消費税[：:]?\\s*([\\d,]+)\\s*円/);
            if (taxMatch) {
                tax = parseInt(taxMatch[1].replace(/,/g, ''), 10) || 0;
            }

            // 出品者
            let seller = '';
            const sellerLink = li.querySelector('a[href*="auctions.yahoo.co.jp/seller/"]');
            if (sellerLink) {
                seller = sellerLink.textContent.trim();
            }

            // 商品画像URL
            let imageUrl = '';
            for (const img of imgs) {
                const src = img.src || '';
                if (src.includes('auctions.c.yimg.jp')) {
                    imageUrl = src;
                    break;
                }
            }

            // 取引ナビURL（送料取得用）— 通常出品とストア出品でURLが異なる
            let transactionUrl = '';
            const txLink = li.querySelector(
                'a[href*="contact.auctions.yahoo.co.jp/buyer/top"], ' +
                'a[href*="buy.auctions.yahoo.co.jp/order/status"]'
            );
            if (txLink) {
                transactionUrl = txLink.href;
            }

            results.push({
                auction_id: auctionId,
                title: (title || '').substring(0, 256),
                price: price,
                date: date,
                seller: seller,
                shipping: shipping,
                tax: tax,
                is_store: isStore,
                url: url,
                image_url: imageUrl,
                transaction_url: transactionUrl,
                cancelled: cancelled
            });
        }

        return results;
    }""", {"junkTexts": junk_set, "cancelKeywords": cancel_kws})

    return items or []


async def _find_next_page(page):
    """次のページへのリンクを探す"""
    # ヤフオクの「次へ」ボタンを探す
    for selector in [
        'a:has-text("次へ")',
        'a:has-text("次のページ")',
        'a[aria-label="次のページ"]',
        'button:has-text("次へ")',
        # ページネーション内の「>」や「次」
        'nav a:has-text(">")',
        '.Pager__next a',
        'li.next a',
        'a.next',
    ]:
        try:
            el = await page.query_selector(selector)
            if el:
                # クリック可能か確認
                is_visible = await el.is_visible()
                if is_visible:
                    return el
        except Exception:
            continue
    return None


# ── 同期版ラッパー ──
def scrape_yahoo_won_sync(**kwargs) -> list[dict]:
    return asyncio.run(scrape_yahoo_won(**kwargs))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def progress(msg, cur, total):
        print(f"[{cur}/{total}] {msg}")

    results = scrape_yahoo_won_sync(on_progress=progress, headless=False)
    print(f"\n=== {len(results)} items found ===")
    for r in results[:5]:
        print(f"  {r['title'][:50]}  ¥{r['price']:,}  {r['date']}  [{r['seller']}]")
