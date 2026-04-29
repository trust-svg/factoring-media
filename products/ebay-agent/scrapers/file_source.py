"""ファイル経由 scraper — Mac の launchd で scrape した JP データを VPS で読む

VPS の IP は Yahoo オークション・Yahoo!フリマで HTTP 403 になるため、
Mac (住宅IP) で scrape した JSON を読んで結果を返す。

呼び出し: site_registry の YAHOO_SCRAPE_SOURCE=file 時にスクレイパー差し替え。
データ形式: data/jp_scrape_<YYYY-MM-DD>.json
{
  "scraped_at": "2026-04-29T08:30:00+09:00",
  "results": {
    "yahoo_auctions": {
      "<keyword>": [{"title":..., "price_jpy":..., ...}, ...]
    },
    "paypay_flea": {...}
  }
}
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sourcing.schema import SourceCandidate

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# キャッシュ（同一プロセス内で1回だけファイルを読む）
_CACHE: dict | None = None
_CACHE_PATH: str | None = None


def _data_dir() -> Path:
    return Path(
        os.getenv(
            "EBAY_AGENT_DATA_DIR",
            str(Path(__file__).resolve().parent.parent / "data"),
        )
    )


def _scrape_file_path() -> Path:
    today = datetime.now(JST).strftime("%Y-%m-%d")
    return _data_dir() / f"jp_scrape_{today}.json"


def _load() -> dict:
    global _CACHE, _CACHE_PATH
    path = _scrape_file_path()
    if _CACHE is not None and _CACHE_PATH == str(path):
        return _CACHE

    if not path.exists():
        logger.warning(
            f"[file_source] {path} 未存在 — Mac からの転送が遅延？degraded mode 継続"
        )
        _CACHE = {"results": {}}
        _CACHE_PATH = str(path)
        return _CACHE

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        scraped_at = data.get("scraped_at", "?")
        n_yh = sum(
            len(v) for v in data.get("results", {}).get("yahoo_auctions", {}).values()
        )
        n_fl = sum(
            len(v) for v in data.get("results", {}).get("paypay_flea", {}).values()
        )
        logger.info(
            f"[file_source] {path.name} 読込完了 (scraped_at={scraped_at}, "
            f"ヤフオク={n_yh}件 / Yahoo!フリマ={n_fl}件)"
        )
        _CACHE = data
        _CACHE_PATH = str(path)
        return _CACHE
    except Exception as e:
        logger.error(f"[file_source] {path} パース失敗: {e}")
        _CACHE = {"results": {}}
        _CACHE_PATH = str(path)
        return _CACHE


class _FileBasedScraper:
    """ファイルから検索結果を返す共通基底クラス"""

    site_key: str = ""
    platform_name: str = ""

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 20,
    ) -> list[SourceCandidate]:
        data = _load()
        site_data = data.get("results", {}).get(self.site_key, {})
        items = site_data.get(keyword, [])

        results: list[SourceCandidate] = []
        for d in items[: limit * 3]:
            if len(results) >= limit:
                break
            try:
                cand = SourceCandidate(
                    title=d.get("title", ""),
                    price_jpy=int(d.get("price_jpy", 0) or 0),
                    platform=d.get("platform", self.platform_name),
                    url=d.get("url", ""),
                    image_url=d.get("image_url", "") or "",
                    condition=d.get("condition", "記載なし"),
                    is_junk=bool(d.get("is_junk", False)),
                )
            except Exception as e:
                logger.debug(f"[file_source/{self.site_key}] パースエラー: {e}")
                continue

            if not cand.title or not cand.url:
                continue
            if cand.price_jpy <= 0 or cand.price_jpy > max_price_jpy:
                continue
            if not junk_ok and cand.is_junk:
                continue
            results.append(cand)

        logger.info(
            f"[{self.platform_name}/file] '{keyword}': {len(results)}件 (file 由来)"
        )
        return results


class YahooAuctionFileScraper(_FileBasedScraper):
    site_key = "yahoo_auctions"
    platform_name = "ヤフオク"


class PayPayFleaFileScraper(_FileBasedScraper):
    site_key = "paypay_flea"
    platform_name = "Yahoo!フリマ"
