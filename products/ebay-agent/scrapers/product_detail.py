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
import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers import HEADERS, parse_price

logger = logging.getLogger(__name__)

# Mac 経由で fetch するプロキシ URL（VPS から Yahoo Auction が EEA ブロックされる対策）
# 設定時: POST {YAHOO_FETCH_PROXY_URL} {"url": ...} → {"status", "html", "final_url"}
# 未設定時: 従来通り直接 requests.get で取得
YAHOO_FETCH_PROXY_URL = os.environ.get("YAHOO_FETCH_PROXY_URL", "").strip()

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


def _extract_images_multi(
    soup: BeautifulSoup,
    html_text: str = "",
    url_pattern: Optional[str] = None,
) -> list[str]:
    """商品ギャラリー画像URLを複数抽出する（重複排除・順序保持）。

    多くの仕入先スクレイパーは og:image の1枚しか取得しておらず、eBay 出品が
    1枚画像になっていた。本関数は以下を順に収集して複数画像を返す:
      1. JSON-LD (schema.org Product) の image（str / list / {url}）
      2. og:image / og:image:url / og:image:secure_url meta（複数可）
      3. twitter:image meta
      4. url_pattern（プラットフォーム固有の画像URL正規表現）を raw HTML に適用

    1枚も取れなければ空リスト。呼び出し側は _finalize_images で og:image 単枚に
    フォールバックするため、本関数は「画像を増やすだけで減らさない」安全な追加層。
    """
    images: list[str] = []
    seen: set[str] = set()

    def _add(u: str) -> None:
        u = (u or "").strip()
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http") and u not in seen:
            seen.add(u)
            images.append(u)

    # 1) JSON-LD Product.image
    for ld in soup.find_all("script", type="application/ld+json"):
        if not ld.string:
            continue
        try:
            data = json.loads(ld.string)
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            img = node.get("image")
            if isinstance(img, str):
                _add(img)
            elif isinstance(img, list):
                for it in img:
                    if isinstance(it, str):
                        _add(it)
                    elif isinstance(it, dict):
                        _add(it.get("url", ""))
            elif isinstance(img, dict):
                _add(img.get("url", ""))

    # 2) og:image 系 meta（サイトによっては複数枚を列挙する）
    for prop in ("og:image", "og:image:url", "og:image:secure_url"):
        for m in soup.find_all("meta", property=prop):
            _add(m.get("content", ""))

    # 3) twitter:image
    for m in soup.find_all("meta", attrs={"name": "twitter:image"}):
        _add(m.get("content", ""))

    # 4) プラットフォーム固有の画像URLパターン（ギャラリーが JS 埋め込みの場合）
    if url_pattern and html_text:
        for u in re.findall(url_pattern, html_text):
            _add(u)

    return images


# ヤフオクの商品画像CDN（gallery は JSON 埋め込みで og:image だけでは1枚しか取れない）
_YAHOO_AUCTION_IMG_PATTERN = (
    r"https://auctions\.c\.yimg\.jp/images\.auctions\.yahoo\.co\.jp/image/"
    r"[^\"'\\\s)]+?\.(?:jpg|jpeg|png)"
)


# ── ヤフオク ──────────────────────────────────────────────────────────────────


def _normalize_yahooauction_url(url: str) -> str:
    """オークションIDを抽出して正規化URLを構築する。"""
    m = re.search(r"/auction/([A-Za-z0-9]+)", url)
    if m:
        return f"https://page.auctions.yahoo.co.jp/jp/auction/{m.group(1)}"
    return url


async def _fetch_yahoo_html_via_proxy(
    norm_url: str,
) -> tuple[Optional[str], Optional[str]]:
    """Mac 経由で Yahoo Auction の HTML を取得。(html, error) を返す。

    VPS の Contabo Asia IP は Yahoo に EEA 扱いで 403/欧州規制ページを返されるため、
    Mac で動く local/server.py の /fetch_yahoo_html に proxy する。
    """
    try:
        resp = await asyncio.to_thread(
            requests.post,
            YAHOO_FETCH_PROXY_URL,
            json={"url": norm_url, "timeout": 15},
            timeout=25,
        )
    except Exception as e:
        return None, f"proxy リクエスト失敗: {e}"

    if resp.status_code != 200:
        return None, f"proxy エラー: HTTP {resp.status_code} {resp.text[:200]}"

    try:
        data = resp.json()
    except Exception as e:
        return None, f"proxy レスポンスパース失敗: {e}"

    upstream_status = data.get("status")
    html = data.get("html") or ""
    if upstream_status and int(upstream_status) >= 400:
        return None, f"Yahoo HTTP {upstream_status}"
    if not html:
        return None, "proxy returned empty HTML"
    return html, None


def _extract_yahooauction_next_data(soup: BeautifulSoup) -> Optional[dict]:
    """Yahoo!オークションの __NEXT_DATA__ (Next.js) から正規データを抽出する。

    2026-05 に Yahoo がページを Next.js 化し、現在価格 / 状態 / 説明文の旧DOM
    (dt/dd の「現在価格」「即決価格」, data-auction-price, div.ProductDescription)
    が消滅した。価格などはすべて埋め込みJSON
    props.pageProps.initialState.item.detail.item に移行している。
    取得できない（旧ページ・構造変更）場合は None を返し、呼び出し側のDOM
    フォールバックに委ねる。
    """
    node = soup.find("script", id="__NEXT_DATA__")
    if not node or not node.string:
        return None
    try:
        nd = json.loads(node.string)
    except (ValueError, TypeError):
        return None

    item = None
    for path in (
        ("props", "pageProps", "initialState", "item", "detail", "item"),
        ("props", "initialState", "item", "detail", "item"),
    ):
        cur = nd
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break
        if isinstance(cur, dict):
            item = cur
            break
    if not item:
        return None

    out: dict = {}

    title = item.get("title")
    if isinstance(title, str) and title.strip():
        out["title"] = title.strip()

    # 価格: 即決(bidOrBuyPrice) > 現在価格(price) > 開始価格(initPrice)。
    # 無在庫ドロップシップは「即決で買える価格」が仕入コスト。即決が無い純
    # オークションは現在価格をフロアとして採用する。
    for key in ("bidOrBuyPrice", "price", "initPrice"):
        v = item.get(key)
        if v in (None, "", 0, "0"):
            continue
        try:
            pv = int(float(v))
        except (ValueError, TypeError):
            continue
        if pv > 0:
            out["price_jpy"] = pv
            break

    cond = item.get("conditionName")
    if isinstance(cond, str) and cond.strip():
        out["condition"] = _normalize_condition(cond.strip())

    desc = item.get("description")
    if isinstance(desc, list) and desc:
        text = "\n".join(str(d) for d in desc if d).strip()
        if text:
            out["description"] = text[:2000]
    elif isinstance(desc, str) and desc.strip():
        out["description"] = desc.strip()[:2000]

    img = item.get("img")
    if isinstance(img, list):
        urls: list[str] = []
        for e in img:
            u = (
                e.get("image")
                if isinstance(e, dict)
                else (e if isinstance(e, str) else None)
            )
            if u and u not in urls:
                urls.append(u)
        if urls:
            out["image_urls"] = urls

    seller = item.get("seller")
    if isinstance(seller, dict):
        sid = seller.get("displayName") or seller.get("aucUserId")
        if sid:
            out["seller_id"] = str(sid)

    return out


async def _fetch_yahooauction(url: str) -> dict:
    """ヤフオク単品スクレイパー (requests + BeautifulSoup)。"""
    platform = "ヤフオク"
    norm_url = _normalize_yahooauction_url(url)
    result = _empty_result(norm_url, platform)

    html_text: Optional[str] = None
    if YAHOO_FETCH_PROXY_URL:
        logger.info(f"[ヤフオク] proxy 経由で取得: {YAHOO_FETCH_PROXY_URL}")
        html_text, err = await _fetch_yahoo_html_via_proxy(norm_url)
        if err:
            logger.warning(f"[ヤフオク] proxy 失敗、直接 fetch にフォールバック: {err}")

    if html_text is None:
        try:
            resp = await asyncio.to_thread(
                requests.get, norm_url, headers=HEADERS, timeout=15
            )
            resp.raise_for_status()
            html_text = resp.text
        except Exception as e:
            result["error"] = f"リクエスト失敗: {e}"
            return result

    try:
        soup = BeautifulSoup(html_text, "html.parser")

        # タイトル
        h1 = soup.find("h1", class_="ProductTitle__text")
        if h1:
            result["title"] = h1.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                result["title"] = og_title.get("content", "").strip()

        # 画像（ギャラリー複数枚）
        imgs = _extract_images_multi(
            soup, html_text=html_text, url_pattern=_YAHOO_AUCTION_IMG_PATTERN
        )
        if imgs:
            result["image_url"] = imgs[0]
            result["image_urls"] = imgs

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

        # __NEXT_DATA__ (Next.js) が取れれば正規データで上書きする。
        # 2026-05 の Next.js 化で上の旧DOM抽出は価格/状態/説明が取れない。
        nd_data = _extract_yahooauction_next_data(soup)
        if nd_data:
            for k in ("title", "price_jpy", "condition", "description", "seller_id"):
                if nd_data.get(k):
                    result[k] = nd_data[k]
            if nd_data.get("image_urls"):
                result["image_urls"] = nd_data["image_urls"]
                result["image_url"] = nd_data["image_urls"][0]

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

    # Mercari API のフル解像度画像は `photos` フィールドに全枚数入っている
    # (`https://static.mercdn.net/item/detail/orig/photos/m{ID}_{N}.jpg`)。
    # `thumbnails` は 240px サムネが 1 枚しか返らないので photos を優先する。
    photos = item.get("photos", []) or []
    photos = [p for p in photos if p]
    if photos:
        result["image_url"] = photos[0]
        result["image_urls"] = photos
    else:
        thumbnails = item.get("thumbnails", []) or []
        thumbnails = [t for t in thumbnails if t]
        if thumbnails:
            result["image_url"] = thumbnails[0]
            result["image_urls"] = thumbnails

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

        # 画像（ギャラリー複数枚）
        imgs = _extract_images_multi(soup, html_text=resp.text)
        if imgs:
            result["image_url"] = imgs[0]
            result["image_urls"] = imgs

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

        # 画像（ギャラリー複数枚）
        imgs = _extract_images_multi(soup, html_text=resp.text)
        if imgs:
            result["image_url"] = imgs[0]
            result["image_urls"] = imgs

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

        # 画像（ギャラリー複数枚）
        imgs = _extract_images_multi(soup, html_text=resp.text)
        if imgs:
            result["image_url"] = imgs[0]
            result["image_urls"] = imgs

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

                # 画像（ギャラリー複数枚）— レンダリング済み HTML から抽出
                try:
                    rendered_html = await page.content()
                    imgs = _extract_images_multi(
                        BeautifulSoup(rendered_html, "html.parser")
                    )
                    if imgs:
                        result["image_url"] = imgs[0]
                        result["image_urls"] = imgs
                except Exception as e:
                    logger.warning(f"[ラクマ] ギャラリー画像抽出失敗: {e}")

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
