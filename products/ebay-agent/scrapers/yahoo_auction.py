"""ヤフオク 検索スクレイパー — requests + BeautifulSoup

auctions.yahoo.co.jp を検索し、仕入れ候補を返す。
requestsベースで安定動作。Playwright不要。
※ yahoo_auctions.py（落札履歴スクレイパー）とは別ファイル。
"""
import asyncio
import logging
import re
import urllib.parse
from typing import Optional

import requests
from bs4 import BeautifulSoup

from scrapers import HEADERS, guess_condition, is_junk
from sourcing.schema import SourceCandidate

logger = logging.getLogger(__name__)

RATE_LIMIT_SEC = 2.0

# セッション共有（Cookieを保持してbotブロック回避）
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
        _session.headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )
        try:
            _session.get("https://auctions.yahoo.co.jp/", timeout=10)
        except Exception:
            pass
    return _session


class YahooAuctionScraper:
    platform_name = "ヤフオク"

    async def search(
        self,
        keyword: str,
        max_price_jpy: int,
        junk_ok: bool,
        limit: int = 20,
    ) -> list[SourceCandidate]:
        await asyncio.sleep(RATE_LIMIT_SEC)
        results = []
        session = _get_session()

        encoded_kw = urllib.parse.quote(keyword, safe="")
        url = (
            f"https://auctions.yahoo.co.jp/search/search/{encoded_kw}/0/"
            f"?fixed=1&max={max_price_jpy}&n=50"
        )

        try:
            resp = session.get(url, timeout=15)
            # 404の場合: キーワードを簡略化してリトライ
            if resp.status_code == 404:
                short_kw = _simplify_keyword(keyword)
                if short_kw and short_kw != keyword:
                    logger.info(f"[ヤフオク] '{keyword}' → 404 → '{short_kw}' でリトライ")
                    encoded_kw = urllib.parse.quote(short_kw, safe="")
                    url = (
                        f"https://auctions.yahoo.co.jp/search/search/{encoded_kw}/0/"
                        f"?fixed=1&max={max_price_jpy}&n=50"
                    )
                    await asyncio.sleep(1)
                    resp = session.get(url, timeout=15)
            if resp.status_code == 404:
                logger.warning(f"[ヤフオク] '{keyword}': 404（該当なし）")
                return results
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[ヤフオク] 検索失敗: {e}")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("li.Product")

        for item in items[:limit]:
            try:
                candidate = _parse_item(item)
                if candidate:
                    if candidate.price_jpy <= max_price_jpy:
                        if junk_ok or not candidate.is_junk:
                            results.append(candidate)
            except Exception as e:
                logger.debug(f"[ヤフオク] アイテムパースエラー: {e}")

        logger.info(f"[ヤフオク] '{keyword}': {len(results)}件取得")
        return results


def _simplify_keyword(keyword: str) -> str:
    words = keyword.split()
    if len(words) >= 2:
        return words[0]
    return ""


def _parse_item(item) -> Optional[SourceCandidate]:
    title_el = item.select_one(".Product__titleLink") or item.select_one(".Product__title a")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    url = title_el.get("href", "")
    if url and not url.startswith("http"):
        url = "https://auctions.yahoo.co.jp" + url

    price_el = item.select_one(".Product__priceValue") or item.select_one(".Product__price")
    price_text = price_el.get_text(strip=True) if price_el else "0"
    price_jpy = int(re.sub(r"[^\d]", "", price_text) or "0")

    condition = guess_condition(title)

    img_el = item.select_one(".Product__imageData img") or item.select_one("img")
    image_url = ""
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src") or ""

    return SourceCandidate(
        title=title,
        price_jpy=price_jpy,
        platform="ヤフオク",
        url=url,
        image_url=image_url,
        condition=condition,
        is_junk=is_junk(title, condition),
    )
