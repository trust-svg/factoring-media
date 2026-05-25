"""ebay-agent ローカル検索サーバ — port 5759

VPS の listing-assistant 再仕入れ候補から呼ばれる。
ebay-inventory-tool/scrapers を流用してメルカリ・ヤフオク・Yahoo!フリマを並列検索。

VPS の IP は各フリマからブロックされているため、ローカルMacで実行する必要がある。
deal-watcher の autossh tunnel (port 5759) 経由で VPS から呼び出される。

起動:
    /Users/Mac_air/Claude-Workspace/products/ebay-inventory-tool/.venv/bin/python \\
        /Users/Mac_air/Claude-Workspace/products/ebay-agent/local/server.py

launchd plist: com.trustlink.ebay-agent-local.plist
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

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


SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "80"))


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

    tasks = [_run_one(s, keyword, max_price_jpy, limit, junk_ok) for s in SCRAPERS]
    results = await asyncio.gather(*tasks)

    # ブランド名 AND 型番の両方がタイトルに含まれるものだけ通す
    # "TASCAM DA-3000" → tokens: ["tascam", "da-3000"]（ハイフン保持）
    kw_tokens = [w.lower() for w in keyword.split() if len(w) >= 2]

    def _is_relevant(item: dict) -> bool:
        title = item.get("title", "").lower()
        title_flat = title.replace("-", "").replace(" ", "")
        for tok in kw_tokens:
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
            filtered = [it for it in res if _is_relevant(it)]
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


async def health_handler(request: web.Request):
    return web.json_response(
        {
            "ok": True,
            "platforms": [s.platform_name for s in SCRAPERS],
        }
    )


def create_app() -> web.Application:
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app.router.add_post("/search", search_handler)
    app.router.add_get("/health", health_handler)
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5759"))
    host = os.getenv("HOST", "127.0.0.1")
    logger.info(f"ebay-agent local search server starting on {host}:{port}")
    web.run_app(create_app(), host=host, port=port, print=None)
