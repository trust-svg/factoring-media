"""ebay-agent ローカル検索サーバ — port 5759

VPS の listing-assistant 再仕入れ候補 / 単品URL取り込みから呼ばれる。
ebay-inventory-tool/scrapers を流用してメルカリ・ヤフオク・Yahoo!フリマを並列検索。

VPS の IP は各フリマからブロックされているため、ローカルMacで実行する必要がある。
特にヤフオクは Contabo Asia の IP を EEA とご認識して 403/欧州規制ページを返す。

deal-watcher の autossh tunnel (port 5759) 経由で VPS から呼び出される。

提供エンドポイント:
    POST /search              — キーワード検索（複数プラットフォーム横断）
    POST /fetch_yahoo_html    — ヤフオク単品URLの生HTML取得（VPS側で BS4 パース）
    GET  /health              — ヘルスチェック

起動:
    /Users/Mac_air/Claude-Workspace/products/ebay-inventory-tool/.venv/bin/python \\
        /Users/Mac_air/Claude-Workspace/products/ebay-agent/local/server.py

launchd plist: com.trustlink.ebay-agent-local.plist
"""

import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from aiohttp import web

EIT_DIR = Path("/Users/Mac_air/Claude-Workspace/products/ebay-inventory-tool")
sys.path.insert(0, str(EIT_DIR))
os.chdir(EIT_DIR)

from scrapers import MercariScraper, PayPayFleaScraper, YahooAuctionScraper  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ebay-agent-local")

SCRAPERS = [
    YahooAuctionScraper(),
    MercariScraper(),
    PayPayFleaScraper(),
]


SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "35"))


async def _run_one(
    scraper, keyword: str, max_price_jpy: int, limit: int, junk_ok: bool
):
    try:
        results = await asyncio.wait_for(
            scraper.search(
                keyword=keyword,
                max_price_jpy=max_price_jpy,
                junk_ok=junk_ok,
                limit=limit,
            ),
            timeout=SCRAPER_TIMEOUT,
        )
        return scraper.platform_name, [
            {
                "platform": r.platform,
                "title": r.title,
                "price_jpy": r.price_jpy,
                "shipping_jpy": r.shipping_jpy,
                "total_price_jpy": r.total_price_jpy,
                "condition": r.condition,
                "url": r.url,
                "image_url": r.image_url,
                "is_junk": r.is_junk,
            }
            for r in results
        ]
    except asyncio.TimeoutError:
        logger.warning(
            f"{scraper.platform_name} timed out after {SCRAPER_TIMEOUT}s — skipping"
        )
        return scraper.platform_name, {"error": f"timeout after {SCRAPER_TIMEOUT}s"}
    except Exception as e:
        logger.exception(f"{scraper.platform_name} search failed: {e}")
        return scraper.platform_name, {"error": str(e)}


async def search_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    keyword = (body.get("keyword") or "").strip()
    if not keyword:
        return web.json_response({"error": "keyword is required"}, status=400)

    try:
        max_price_jpy = int(body.get("max_price_jpy", 30000))
    except (ValueError, TypeError):
        max_price_jpy = 30000
    try:
        limit = int(body.get("limit", 5))
    except (ValueError, TypeError):
        limit = 5
    junk_ok = bool(body.get("junk_ok", False))

    logger.info(
        f"search: keyword='{keyword}' max_price=¥{max_price_jpy:,} limit={limit} junk_ok={junk_ok}"
    )

    # Playwright scrapers (メルカリ・Yahoo!フリマ) を並列起動するとlaunchd環境で
    # Chromiumリソース競合 → 30s内部タイムアウト発火。逐次実行で安定化。
    results = []
    for s in SCRAPERS:
        results.append(await _run_one(s, keyword, max_price_jpy, limit, junk_ok))

    # 型番トークン（数字またはハイフンを含む）のみタイトル一致を必須とする。
    # ブランド名は日本語表記（パイオニア等）が多いため除外。
    # "Pioneer CDJ-900" → filter_tokens: ["cdj-900"]
    # "TASCAM DA-3000"  → filter_tokens: ["da-3000"]
    # "Pioneer XDJ-RX"  → filter_tokens: ["xdj-rx"]  (ハイフンあり)
    # "Pioneer A-717"   → filter_tokens: ["a-717"]
    kw_tokens = [w.lower() for w in keyword.split() if len(w) >= 2]

    def _has_model_chars(tok: str) -> bool:
        return any(c.isdigit() or c == "-" for c in tok)

    model_tokens = [t for t in kw_tokens if _has_model_chars(t)]
    filter_tokens = model_tokens if model_tokens else kw_tokens
    logger.info(
        f"relevance filter tokens: {filter_tokens} (from kw_tokens: {kw_tokens})"
    )

    def _is_relevant(item: dict) -> bool:
        title = item.get("title", "").lower()
        title_flat = title.replace("-", "").replace(" ", "")
        for tok in filter_tokens:
            tok_flat = tok.replace("-", "")
            if tok not in title and tok_flat not in title_flat:
                return False
        return True

    by_platform: dict = {}
    errors: dict = {}
    for name, res in results:
        if isinstance(res, dict) and "error" in res:
            errors[name] = res["error"]
            by_platform[name] = []
        else:
            filtered = []
            for it in res:
                if _is_relevant(it):
                    filtered.append(it)
                else:
                    logger.info(f"[{name}] filtered out: {it.get('title', '')!r}")
            if len(res) != len(filtered):
                logger.info(
                    f"[{name}] relevance filter: {len(res)}件 → {len(filtered)}件"
                )
            by_platform[name] = filtered

    all_items = []
    for items in by_platform.values():
        all_items.extend(items)
    all_items.sort(key=lambda x: x.get("total_price_jpy") or x["price_jpy"])

    return web.json_response(
        {
            "keyword": keyword,
            "max_price_jpy": max_price_jpy,
            "items": all_items,
            "by_platform": by_platform,
            "errors": errors,
        }
    )


_YAHOO_AUCTION_URL_RE = re.compile(
    r"^https?://(page\.auctions|auctions)\.yahoo\.co\.jp/", re.I
)

_YAHOO_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://auctions.yahoo.co.jp/",
    "Upgrade-Insecure-Requests": "1",
}


async def fetch_yahoo_html_handler(request: web.Request):
    """ヤフオク単品URLを Mac IP 経由で取得し、生HTMLを返す。

    VPS の Contabo IP は Yahoo に EEA 扱いで弾かれるため、Mac 経由で fetch して
    HTML だけ返し、パースは VPS 側の scrapers/product_detail.py に任せる。

    Request JSON: {"url": "https://page.auctions.yahoo.co.jp/jp/auction/xxx"}
    Response JSON: {"status": 200, "html": "...", "final_url": "...", "headers": {...}}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    url = (body.get("url") or "").strip()
    if not url:
        return web.json_response({"error": "url is required"}, status=400)
    if not _YAHOO_AUCTION_URL_RE.match(url):
        return web.json_response(
            {"error": "only Yahoo Auction URLs are allowed"}, status=400
        )

    timeout = int(body.get("timeout", 15))
    logger.info(f"fetch_yahoo_html: {url}")

    try:
        resp = await asyncio.to_thread(
            requests.get,
            url,
            headers=_YAHOO_FETCH_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
    except Exception as e:
        logger.warning(f"fetch_yahoo_html: 取得失敗 {url} — {e}")
        return web.json_response({"error": f"fetch failed: {e}"}, status=502)

    return web.json_response(
        {
            "status": resp.status_code,
            "html": resp.text,
            "final_url": resp.url,
            "encoding": resp.encoding,
        }
    )


# 画像取得を許可するホスト（SSRF対策）。Yahoo 画像CDN のみ。
_IMAGE_HOST_SUFFIXES = (".yimg.jp", ".yahoo.co.jp")


def _image_host_allowed(netloc: str) -> bool:
    host = netloc.lower().split(":", 1)[0]
    return any(
        host == suf.lstrip(".") or host.endswith(suf) for suf in _IMAGE_HOST_SUFFIXES
    )


async def fetch_image_handler(request: web.Request):
    """画像URLを Mac IP 経由で取得し、生バイトを返す。

    VPS の Contabo IP は Yahoo 画像CDN(yimg.jp)に 403 されるため、HTML と同様に
    Mac 経由で取得する。出品時の白背景化(whitebg)から呼ばれる。

    Request JSON: {"url": "...", "referer": "...", "timeout": 30}
    Response: 成功時は画像バイト（Content-Type 透過）、失敗時は JSON エラー。
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    url = (body.get("url") or "").strip()
    if not url:
        return web.json_response({"error": "url is required"}, status=400)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return web.json_response({"error": "only http(s) URLs allowed"}, status=400)
    if not _image_host_allowed(parsed.netloc):
        return web.json_response(
            {"error": f"host not allowed: {parsed.netloc}"}, status=403
        )

    timeout = int(body.get("timeout", 30))
    referer = (body.get("referer") or "https://auctions.yahoo.co.jp/").strip()
    headers = {
        "User-Agent": _YAHOO_FETCH_HEADERS["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
        "Accept-Language": _YAHOO_FETCH_HEADERS["Accept-Language"],
        "Referer": referer,
    }

    try:
        resp = await asyncio.to_thread(
            requests.get,
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
    except Exception as e:
        logger.warning(f"fetch_image: 取得失敗 {url} — {e}")
        return web.json_response({"error": f"fetch failed: {e}"}, status=502)

    if resp.status_code != 200:
        logger.warning(f"fetch_image: upstream HTTP {resp.status_code} {url}")
        return web.json_response(
            {"error": f"upstream HTTP {resp.status_code}"}, status=502
        )

    content_type = resp.headers.get("Content-Type", "application/octet-stream")
    return web.Response(body=resp.content, content_type=content_type.split(";")[0])


async def health_handler(request: web.Request):
    return web.json_response(
        {
            "ok": True,
            "platforms": [s.platform_name for s in SCRAPERS],
            "endpoints": ["/search", "/fetch_yahoo_html", "/fetch_image", "/health"],
        }
    )


def create_app() -> web.Application:
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app.router.add_post("/search", search_handler)
    app.router.add_post("/fetch_yahoo_html", fetch_yahoo_html_handler)
    app.router.add_post("/fetch_image", fetch_image_handler)
    app.router.add_get("/health", health_handler)
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5759"))
    host = os.getenv("HOST", "127.0.0.1")
    logger.info(f"ebay-agent local search server starting on {host}:{port}")
    web.run_app(create_app(), host=host, port=port, print=None)
