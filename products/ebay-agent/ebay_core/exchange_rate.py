"""為替レート取得 (Frankfurter API, 1時間キャッシュ)"""
import logging
import time

import requests

logger = logging.getLogger(__name__)

_cache: dict = {"rate": None, "timestamp": 0}
_CACHE_TTL_SEC = 3600


def get_usd_to_jpy() -> float:
    """USD→JPY の為替レートを返す"""
    now = time.time()
    if _cache["rate"] and (now - _cache["timestamp"]) < _CACHE_TTL_SEC:
        return _cache["rate"]

    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "JPY"},
            timeout=10,
        )
        resp.raise_for_status()
        rate = resp.json()["rates"]["JPY"]
        _cache["rate"] = rate
        _cache["timestamp"] = now
        logger.info(f"為替レート取得: 1 USD = {rate:.2f} JPY")
        return rate
    except Exception as e:
        logger.warning(f"為替レート取得失敗: {e}")
        return _cache["rate"] or 150.0


def usd_to_jpy(usd: float) -> int:
    return int(usd * get_usd_to_jpy())


def jpy_to_usd(jpy: int) -> float:
    rate = get_usd_to_jpy()
    return round(jpy / rate, 2) if rate else 0.0
