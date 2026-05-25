"""単品URL スクレイパー — 日本マーケットプレイス対応

指定URLの商品ページを取得し、構造化された商品情報を返す。

対応プラットフォーム:
    - ヤフオク  (requests + BeautifulSoup)
    - メルカリ  (Playwright)
    - Yahooフリマ (requests + BeautifulSoup)
    - ハードオフ (requests + BeautifulSoup)
    - 駿河屋   (requests + BeautifulSoup)
    - ラクマ   (Playwright)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers import HEADERS, parse_price

logger = logging.getLogger(__name__)

# ── コンディションマッピング ──────────────────────────────────────────────────

CONDITION_MAP: dict[str, str] = {
    "新品": "新品",
    "未使用": "新品",
    "新品未使用": "新品",
    "未使用に近い": "美品",
    "美品": "美品",
    "目立った傷や汚れなし": "良品",
    "良品": "良品",
    "やや傷や汚れあり": "中古",
    "中古": "中古",
    "傷や汚れあり": "中古",
    "全体的に状態が悪い": "ジャンク",
    "ジャンク": "ジャンク",
}


def _normalize_condition(raw: str) -> str:
    """生コンディションテキストを標準値にマッピング。一致なしは空文字。"""
    raw = raw.strip()
    if raw in CONDITION_MAP:
        return CONDITION_MAP[raw]
    # 部分一致フォールバック（長い順に試す）
    for key in sorted(CONDITION_MAP, key=len, reverse=True):
        if key in raw:
            return CONDITION_MAP[key]
    return ""


# ── プラットフォーム検出 ───────────────────────────────────────────────────────


def _detect_platform(url: str) -> str:
    """URLからプラットフォーム名を返す。"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if "auctions.yahoo.co.jp" in host:
        return "ヤフオク"
    if "jp.mercari.com" in host and "/item/" in path:
        return "メルカリ"
    if "paypayfleamarket.yahoo.co.jp" in host:
        return "Yahooフリマ"
    if "hardoff.co.jp" in host:
        return "ハードオフ"
    if "suruga-ya.jp" in host:
        return "駿河屋"
    if "fril.jp" in host or "rakuma.co.jp" in host:
        return "ラクマ"
    return "不明"


def _empty_result(url: str, platform: str, error: Optional[str] = None) -> dict:
    """エラー時のデフォルト構造を返す。"""
    return {
        "platform": platform,
        "title": "",
        "price_jpy": 0,
        "image_url": "",
        "image_urls": [],
        "product_url": url,
        "condition": "",
        "seller_id": "",
        "description": "",
        "error": error,
    }


def _finalize_images(result: dict) -> None:
    """image_urls が空なら image_url の単一画像でフォールバック。"""
    if not result.get("image_urls") and result.get("image_url"):
        result["image_urls"] = [result["image_url"]]
    if result.get("image_urls") and not result.get("image_url"):
        result["image_url"] = result["image_urls"][0]


# ── ヤフオク ──────────────────────────────────────────────────────────────────


def _normalize_yahooauction_url(url: str) -> str:
    """オークションIDを抽出して正規化URLを構築する。"""
    m = re.search(r"/auction/([A-Za-z0-9]+)", url)
    if m:
        return f"https://page.auctions.yahoo.co.jp/jp/auction/{m.group(1)}"
    return url


async def _fetch_yahooauction(url: str) -> dict:
    """ヤフオク単品スクレイパー (requests + BeautifulSoup)。"""
    platform = "ヤフオク"
    norm_url = _normalize_yahooauction_url(url)
    result = _empty_result(norm_url, platform)

    try:
        resp = await asyncio.to_thread(
            requests.get, norm_url, headers=HEADERS, timeout=15
        )
        resp.raise_for_status()
    except Exception as e:
        result["error"] = f"リクエスト失敗: {e}"
        return result

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # タイトル
        h1 = soup.find("h1", class_="ProductTitle__text")
        if h1:
            result["title"] = h1.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                result["title"] = og_title.get("content", "").strip()

        # 画像
        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["image_url"] = og_image.get("content", "").strip()

        # 価格 — 現在価格 / 即決価格
        price_raw = ""
        # パターン1: data-auction-price 属性
        price_tag = soup.find(attrs={"data-auction-price": True})
        if price_tag:
            price_raw = price_tag["data-auction-price"]
        if not price_raw:
            # パターン2: 商品詳細テーブルから "現在価格" / "即決価格"
            for dt in soup.find_all("dt"):
                label = dt.get_text(strip=True)
                if label in ("現在価格", "即決価格"):
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        price_raw = dd.get_text(strip=True)
                        break
        if not price_raw:
            # パターン3: class に Price が含む要素
            price_el = soup.find(class_=re.compile(r"Price", re.I))
            if price_el:
                price_raw = price_el.get_text(strip=True)

        if price_raw:
            result["price_jpy"] = parse_price(price_raw)

        # コンディション
        for dt in soup.find_all("dt"):
            if "状態" in dt.get_text():
                dd = dt.find_next_sibling("dd")
                if dd:
                    result["condition"] = _normalize_condition(dd.get_text(strip=True))
                    break

        # セラーID
        seller_tag = soup.find(attrs={"data-auction-seller": True})
        if seller_tag:
            result["seller_id"] = seller_tag["data-auction-seller"]
        else:
            seller_link = soup.find("a", href=re.compile(r"/seller/"))
            if seller_link:
                m = re.search(r"/seller/([^/?#]+)", seller_link["href"])
                if m:
                    result["seller_id"] = m.group(1)

        # 説明文
        desc_div = soup.find("div", class_=re.compile(r"ProductDescription", re.I))
        if desc_div:
            result["description"] = desc_div.get_text(separator="\n", strip=True)[:2000]

    except Exception as e:
        result["error"] = f"パース失敗: {e}"

    _finalize_images(result)
    return result


# ── メルカリ ──────────────────────────────────────────────────────────────────

_MERCARI_COOKIE_FILE = (
    Path(__file__).parent.parent / ".playwright" / "mercari_cookies.json"
)
_MERCARI_TOKEN_CACHE = (
    Path(__file__).parent.parent / ".playwright" / "mercari_token_cache.json"
)
_TOKEN_TTL = 3000  # Mercari tokens expire ~3600s; cache for 50 min to be safe


async def _capture_mercari_token_playwright() -> Optional[str]:
    """Intercept access_token from auth.mercari.com/jp/v1/token via route handler.

    Uses ctx.route() instead of on_response so the body is read while the
    request is still in-flight — avoids the race where resp.json() fails
    because browser.close() runs before the async callback completes.
    asyncio.Event ensures we wait for the token before closing.
    """
    import asyncio
    from playwright.async_api import async_playwright

    token: Optional[str] = None
    token_ready = asyncio.Event()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # op_sess (auth.mercari.com) is required for prompt=none silent PKCE auth
        if _MERCARI_COOKIE_FILE.exists():
            try:
                cookies = json.loads(_MERCARI_COOKIE_FILE.read_text())
                await ctx.add_cookies(cookies)
            except Exception as e:
                logger.warning(f"[mercari] cookie load failed: {e}")

        async def intercept_token(route, request):
            nonlocal token
            # Fetch the response ourselves so the body is available before browser closes
            response = await route.fetch()
            if not token:
                try:
                    body = json.loads(await response.body())
                    if "access_token" in body:
                        token = body["access_token"]
                        logger.info("[mercari] access_token captured")
                        token_ready.set()
                except Exception:
                    pass
            await route.fulfill(response=response)

        # Intercept only the token endpoint to avoid slowing down other requests
        await ctx.route(
            lambda url: "mercari" in url and "/jp/v1/token" in url,
            intercept_token,
        )

        page = await ctx.new_page()

        try:
            await page.goto(
                "https://jp.mercari.com/",
                wait_until="networkidle",
                timeout=40000,
            )
            # Wait up to 8s for token capture after networkidle
            try:
                await asyncio.wait_for(token_ready.wait(), timeout=8.0)
            except asyncio.TimeoutError:
                pass
        except Exception as e:
            logger.warning(f"[mercari] Playwright navigation failed: {e}")
        finally:
            await browser.close()

    return token


async def _get_mercari_token() -> Optional[str]:
    """Return a valid Mercari access_token, calling Playwright only when cache is stale."""
    if _MERCARI_TOKEN_CACHE.exists():
        try:
            cache = json.loads(_MERCARI_TOKEN_CACHE.read_text())
            if time.time() < cache.get("expires_at", 0):
                logger.debug("[mercari] using cached token")
                return cache["access_token"]
        except Exception:
            pass

    token = await _capture_mercari_token_playwright()
    if token:
        try:
            _MERCARI_TOKEN_CACHE.write_text(
                json.dumps(
                    {
                        "access_token": token,
                        "expires_at": time.time() + _TOKEN_TTL,
                    }
                )
            )
        except Exception:
            pass
    return token


async def _fetch_mercari(url: str) -> dict:
    """メルカリ: access_tokenをネットワーク傍受→直接APIで商品情報を取得。"""
    import urllib.request
    import urllib.error

    platform = "メルカリ"
    result = _empty_result(url, platform)

    m = re.search(r"/item/(m\d+)", url)
    if not m:
        result["error"] = "URLからアイテムIDを取得できません"
        return result
    item_id = m.group(1)

    try:
        token = await _get_mercari_token()
    except Exception as e:
        result["error"] = f"トークン取得失敗: {e}"
        return result

    if not token:
        result["error"] = "アクセストークンを取得できませんでした"
        return result

    req = urllib.request.Request(
        f"https://api.mercari.jp/items/get?id={item_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Platform": "web",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token expired; invalidate cache so next call refreshes it
            try:
                _MERCARI_TOKEN_CACHE.unlink(missing_ok=True)
            except Exception:
                pass
            result["error"] = (
                "認証エラー(401): トークンを無効化しました。再度URLを入力してください"
            )
        else:
            result["error"] = f"API HTTPエラー: {e.code}"
        return result
    except Exception as e:
        result["error"] = f"APIリクエスト失敗: {e}"
        return result

    item = data.get("data", {})

    result["title"] = item.get("name", "")

    price = item.get("price")
    if price is not None:
        try:
            result["price_jpy"] = int(price)
        except (ValueError, TypeError):
            pass

    cond = item.get("item_condition")
    if isinstance(cond, dict):
        raw_cond = cond.get("name", "")
    elif isinstance(cond, str):
        raw_cond = cond
    else:
        raw_cond = ""
    result["condition"] = _normalize_condition(raw_cond) if raw_cond else ""

    seller = item.get("seller")
    if isinstance(seller, dict):
        result["seller_id"] = seller.get("name", "")
    elif isinstance(seller, str):
        result["seller_id"] = seller

    thumbnails = item.get("thumbnails", [])
    if thumbnails:
        # Mercari API の thumbnails は 240px サムネ。
        # `static.mercdn.net/thumb/...` → `static.mercdn.net/...` でフル解像度版になる。
        def _full_res(url: str) -> str:
            if not url:
                return url
            return url.replace("static.mercdn.net/thumb/", "static.mercdn.net/")

        full = [_full_res(t) for t in thumbnails if t]
        result["image_url"] = full[0] if full else ""
        result["image_urls"] = full

    result["description"] = (item.get("description", "") or "")[:2000]

    _finalize_images(result)
    return result


# ── Yahooフリマ ───────────────────────────────────────────────────────────────


async def _fetch_yahoo_flea(url: str) -> dict:
    """Yahooフリマ単品スクレイパー (requests + BeautifulSoup)。"""
    platform = "Yahooフリマ"
    result = _empty_result(url, platform)

    try:
        resp = await asyncio.to_thread(requests.get, url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        result["error"] = f"リクエスト失敗: {e}"
        return result

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # タイトル
        og_title = soup.find("meta", property="og:title")
        if og_title:
            result["title"] = og_title.get("content", "").strip()
        else:
            h1 = soup.find("h1")
            if h1:
                result["title"] = h1.get_text(strip=True)

        # 画像
        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["image_url"] = og_image.get("content", "").strip()

        # 価格
        price_el = soup.find(class_=re.compile(r"price|Price"))
        if price_el:
            result["price_jpy"] = parse_price(price_el.get_text(strip=True))
        else:
            # JSON-LD フォールバック
            ld = soup.find("script", type="application/ld+json")
            if ld and ld.string:
                import json

                try:
                    data = json.loads(ld.string)
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        price_str = str(offers.get("price", "0"))
                        result["price_jpy"] = (
                            int(price_str) if price_str.isdigit() else 0
                        )
                except Exception:
                    pass

        # コンディション
        for dt in soup.find_all("dt"):
            if "状態" in dt.get_text():
                dd = dt.find_next_sibling("dd")
                if dd:
                    result["condition"] = _normalize_condition(dd.get_text(strip=True))
                    break

        # セラーID — Yahooフリマはセラー名リンクから
        seller_link = soup.find("a", href=re.compile(r"/seller/|/user/"))
        if seller_link:
            m = re.search(r"/(?:seller|user)/([^/?#]+)", seller_link.get("href", ""))
            if m:
                result["seller_id"] = m.group(1)

        # 説明文
        desc_el = soup.find(
            class_=re.compile(r"description|Description|comment|Comment")
        )
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)[:2000]

    except Exception as e:
        result["error"] = f"パース失敗: {e}"

    _finalize_images(result)
    return result


# ── ハードオフ ────────────────────────────────────────────────────────────────


async def _fetch_hardoff(url: str) -> dict:
    """ハードオフ単品スクレイパー (requests + BeautifulSoup)。"""
    platform = "ハードオフ"
    result = _empty_result(url, platform)

    try:
        resp = await asyncio.to_thread(requests.get, url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        result["error"] = f"リクエスト失敗: {e}"
        return result

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # タイトル
        h1 = soup.find("h1")
        if h1:
            result["title"] = h1.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                result["title"] = og_title.get("content", "").strip()

        # 画像
        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["image_url"] = og_image.get("content", "").strip()

        # 価格 — ハードオフは "¥XX,XXX（税込）" 形式が多い
        price_el = (
            soup.find(class_=re.compile(r"price|Price"))
            or soup.find("strong", string=re.compile(r"¥|円"))
            or soup.find("span", string=re.compile(r"¥|円"))
        )
        if price_el:
            result["price_jpy"] = parse_price(price_el.get_text(strip=True))

        # コンディション — ハードオフは Aランク/Bランク/ジャンク 形式
        grade_map = {
            "Sランク": "新品",
            "Aランク": "美品",
            "Bランク": "良品",
            "Cランク": "中古",
            "ジャンク": "ジャンク",
        }
        for dt in soup.find_all("dt"):
            label = dt.get_text(strip=True)
            if "ランク" in label or "状態" in label or "コンディション" in label:
                dd = dt.find_next_sibling("dd")
                if dd:
                    raw_cond = dd.get_text(strip=True)
                    result["condition"] = grade_map.get(
                        raw_cond, _normalize_condition(raw_cond)
                    )
                    break
        # グレードが本文に直接書かれているケースへのフォールバック
        if not result["condition"]:
            page_text = soup.get_text()
            for grade, mapped in grade_map.items():
                if grade in page_text:
                    result["condition"] = mapped
                    break

        # セラーID — 店舗名を seller_id 代替として使用
        store_el = soup.find(class_=re.compile(r"store|shop|Shop|Store"))
        if store_el:
            result["seller_id"] = store_el.get_text(strip=True)[:100]

        # 説明文
        desc_el = soup.find(class_=re.compile(r"description|Description|detail|Detail"))
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)[:2000]

    except Exception as e:
        result["error"] = f"パース失敗: {e}"

    _finalize_images(result)
    return result


# ── 駿河屋 ────────────────────────────────────────────────────────────────────


async def _fetch_surugaya(url: str) -> dict:
    """駿河屋単品スクレイパー (requests + BeautifulSoup)。"""
    platform = "駿河屋"
    result = _empty_result(url, platform)

    try:
        resp = await asyncio.to_thread(requests.get, url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        result["error"] = f"リクエスト失敗: {e}"
        return result

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # タイトル
        og_title = soup.find("meta", property="og:title")
        if og_title:
            result["title"] = og_title.get("content", "").strip()
        else:
            h1 = soup.find("h1")
            if h1:
                result["title"] = h1.get_text(strip=True)

        # 画像
        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["image_url"] = og_image.get("content", "").strip()

        # 価格
        price_el = soup.find(class_=re.compile(r"price|Price")) or soup.find(
            id=re.compile(r"price|Price")
        )
        if price_el:
            result["price_jpy"] = parse_price(price_el.get_text(strip=True))

        # コンディション — 駿河屋は商品状態テーブルに記載
        for label_el in soup.find_all(
            string=re.compile(r"商品状態|コンディション|状態")
        ):
            parent = label_el.parent
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    result["condition"] = _normalize_condition(
                        sibling.get_text(strip=True)
                    )
                    break

        # セラーID — 駿河屋は単一店舗のため固定
        result["seller_id"] = "suruga-ya"

        # 説明文
        desc_el = soup.find(
            class_=re.compile(r"description|Description|detail|comment")
        ) or soup.find(id=re.compile(r"description|detail"))
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)[:2000]

    except Exception as e:
        result["error"] = f"パース失敗: {e}"

    _finalize_images(result)
    return result


# ── ラクマ ────────────────────────────────────────────────────────────────────


def _normalize_rakuma_url(url: str) -> str:
    """fril.jp の商品URLを正規化する (app/items → items)。"""
    return re.sub(r"/app/items/", "/items/", url)


async def _fetch_rakuma(url: str) -> dict:
    """ラクマ単品スクレイパー (Playwright)。"""
    from playwright.async_api import async_playwright

    platform = "ラクマ"
    norm_url = _normalize_rakuma_url(url)
    result = _empty_result(norm_url, platform)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
            )
            page = await ctx.new_page()
            try:
                await page.goto(norm_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                data = await page.evaluate("""() => {
                    const og = (prop) => {
                        const el = document.querySelector(`meta[property="${prop}"]`);
                        return el ? el.content : '';
                    };

                    // タイトル
                    const h1 = document.querySelector('h1');
                    const title = h1 ? h1.innerText.trim() : og('og:title');

                    // 画像
                    const imageUrl = og('og:image');

                    // 価格
                    const body = document.body.innerText || '';
                    const priceMatch = body.match(/¥([\\d,]+)/);
                    const priceRaw = priceMatch ? priceMatch[1].replace(/,/g, '') : '0';

                    // コンディション — ラクマは「商品の状態」ラベルの隣または下
                    let condition = '';
                    const elements = [...document.querySelectorAll('*')];
                    for (const el of elements) {
                        if (el.children.length > 0) continue;
                        const txt = (el.innerText || '').trim();
                        if (txt === '商品の状態' || txt === '状態') {
                            const parent = el.closest('tr, li, div');
                            if (parent) {
                                const next = parent.nextElementSibling;
                                if (next) { condition = next.innerText.trim(); break; }
                                // td の隣
                                const tds = parent.querySelectorAll('td');
                                if (tds.length >= 2) { condition = tds[1].innerText.trim(); break; }
                            }
                        }
                    }

                    // セラーID — ラクマはセラーリンクから
                    let sellerId = '';
                    const sellerLink = document.querySelector('a[href*="/users/"], a[href*="/user/"]');
                    if (sellerLink) {
                        const m = sellerLink.href.match(/\\/users?\\/([^/?#]+)/);
                        if (m) sellerId = m[1];
                    }

                    // 説明文
                    let description = '';
                    const descEl = document.querySelector(
                        '[class*="description"], [class*="Description"], [class*="comment"]'
                    );
                    if (descEl) description = descEl.innerText.trim().substring(0, 2000);

                    return { title, image_url: imageUrl, price_raw: priceRaw,
                             condition, seller_id: sellerId, description };
                }""")

                result["title"] = data.get("title", "")
                result["image_url"] = data.get("image_url", "")
                result["seller_id"] = data.get("seller_id", "")
                result["description"] = data.get("description", "")

                price_raw = data.get("price_raw", "0")
                result["price_jpy"] = int(price_raw) if price_raw.isdigit() else 0

                raw_cond = data.get("condition", "")
                result["condition"] = _normalize_condition(raw_cond) if raw_cond else ""

            finally:
                await browser.close()

    except Exception as e:
        result["error"] = f"Playwright失敗: {e}"

    _finalize_images(result)
    return result


# ── メイン関数 ────────────────────────────────────────────────────────────────

_PLATFORM_HANDLERS = {
    "ヤフオク": _fetch_yahooauction,
    "メルカリ": _fetch_mercari,
    "Yahooフリマ": _fetch_yahoo_flea,
    "ハードオフ": _fetch_hardoff,
    "駿河屋": _fetch_surugaya,
    "ラクマ": _fetch_rakuma,
}


async def fetch_product_url(url: str) -> dict:
    """URLから商品情報を取得して構造化dictを返す。

    Args:
        url: 対応マーケットプレイスの商品URL

    Returns:
        {
            "platform": str,     # "ヤフオク"|"メルカリ"|"Yahooフリマ"|"ハードオフ"|"駿河屋"|"ラクマ"|"不明"
            "title": str,
            "price_jpy": int,
            "image_url": str,
            "product_url": str,
            "condition": str,    # "新品"|"美品"|"良品"|"中古"|"ジャンク"|""
            "seller_id": str,
            "description": str,
            "error": str | None  # 成功時は None、失敗時はエラーメッセージ
        }
    """
    platform = _detect_platform(url)
    handler = _PLATFORM_HANDLERS.get(platform)

    if handler is None:
        logger.warning(f"[product_detail] 未対応プラットフォーム: {url}")
        return _empty_result(
            url, platform, error=f"未対応のプラットフォームです: {url}"
        )

    logger.info(f"[product_detail] {platform} — {url}")
    try:
        result = await handler(url)
    except Exception as e:
        logger.exception(f"[product_detail] {platform} 予期しないエラー: {e}")
        result = _empty_result(url, platform, error=f"予期しないエラー: {e}")

    return result
