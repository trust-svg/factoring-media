"""Mac ローカル scraper — ヤフオク + Yahoo!フリマ を住宅IPから scrape

VPS の Tokyo IP は Yahoo 系で HTTP 403 になるため、
Mac で scrape して JSON を生成、SCP で VPS にアップする構成。

実行タイミング: launchd 8:30 JST (毎日)
出力: $TMPDIR/jp_scrape_<DATE>.json → SCP → /opt/apps/claude-workspace/products/ebay-agent/data/

環境変数:
  VPS_USER       VPSログインユーザー (default: root)
  VPS_HOST       VPS IP/ホスト       (default: 46.250.252.99)
  VPS_DATA_DIR   VPS上のdata path     (default: /opt/apps/claude-workspace/products/ebay-agent/data)
  SKIP_SCP=1     SCPをスキップ (ローカル動作確認用)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EBAY_AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EBAY_AGENT_DIR))

from research.hot_expensive import DEFAULT_QUERIES  # noqa: E402
from scrapers.paypay_flea import PayPayFleaScraper  # noqa: E402
from scrapers.yahoo_auction import YahooAuctionScraper  # noqa: E402
from sourcing.schema import SourceCandidate  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("local_yahoo_scrape")

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).strftime("%Y-%m-%d")

OUTPUT_DIR = Path(os.getenv("LOCAL_SCRAPE_OUTPUT_DIR") or os.getenv("TMPDIR", "/tmp"))
OUTPUT_PATH = OUTPUT_DIR / f"jp_scrape_{TODAY}.json"

VPS_USER = os.getenv("VPS_USER", "root")
VPS_HOST = os.getenv("VPS_HOST", "46.250.252.99")
VPS_DATA_DIR = os.getenv(
    "VPS_DATA_DIR",
    "/opt/apps/claude-workspace/products/ebay-agent/data",
)

# 価格上限は VPS 側で再フィルタするので広めに取る
MAX_PRICE_JPY = 5_000_000
LIMIT_PER_QUERY = 20


def _candidate_to_dict(c: SourceCandidate) -> dict:
    return {
        "title": c.title,
        "price_jpy": c.price_jpy,
        "platform": c.platform,
        "url": c.url,
        "image_url": c.image_url,
        "condition": c.condition,
        "is_junk": c.is_junk,
    }


async def _scrape_one(scraper, keyword: str, label: str) -> list[dict]:
    try:
        results = await scraper.search(
            keyword=keyword,
            max_price_jpy=MAX_PRICE_JPY,
            junk_ok=True,
            limit=LIMIT_PER_QUERY,
        )
        return [_candidate_to_dict(c) for c in results]
    except Exception as e:
        logger.warning(f"[{label}] '{keyword}' 失敗: {e}")
        return []


async def main() -> None:
    queries = [q.get("query", "") for q in DEFAULT_QUERIES if q.get("query")]
    logger.info(f"開始: {len(queries)} クエリ × 2サイト")

    yahoo = YahooAuctionScraper()
    flea = PayPayFleaScraper()

    out: dict = {
        "scraped_at": datetime.now(JST).isoformat(),
        "host": "mac-local",
        "results": {
            "yahoo_auctions": {},
            "paypay_flea": {},
        },
    }

    for i, q in enumerate(queries, 1):
        logger.info(f"[{i}/{len(queries)}] {q}")
        out["results"]["yahoo_auctions"][q] = await _scrape_one(yahoo, q, "ヤフオク")
        out["results"]["paypay_flea"][q] = await _scrape_one(flea, q, "Yahoo!フリマ")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    yh_total = sum(len(v) for v in out["results"]["yahoo_auctions"].values())
    fl_total = sum(len(v) for v in out["results"]["paypay_flea"].values())
    logger.info(f"scrape 完了: ヤフオク={yh_total}件 / Yahoo!フリマ={fl_total}件")
    logger.info(f"出力: {OUTPUT_PATH}")

    if os.getenv("SKIP_SCP") == "1":
        logger.info("SKIP_SCP=1 のため SCP をスキップ")
        return

    target = f"{VPS_USER}@{VPS_HOST}:{VPS_DATA_DIR}/"
    cmd = [
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=15",
        str(OUTPUT_PATH),
        target,
    ]
    logger.info(f"SCP → {target}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        logger.error(f"SCP 失敗 (exit {r.returncode}): {r.stderr.strip()}")
        sys.exit(2)
    logger.info("SCP 成功")


if __name__ == "__main__":
    asyncio.run(main())
