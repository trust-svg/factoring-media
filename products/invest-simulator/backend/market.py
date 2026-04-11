import yfinance as yf
from datetime import datetime
from typing import Optional
import pytz


def get_usdjpy() -> float:
    try:
        rate = yf.Ticker("USDJPY=X").fast_info.last_price
        return float(rate) if rate else 150.0
    except Exception:
        return 150.0


def get_price_usd(ticker: str, usdjpy: float) -> Optional[float]:
    """現在値をUSDで返す。日本株（.T）はJPY→USD変換。"""
    try:
        price = yf.Ticker(ticker).fast_info.last_price
        if price is None:
            return None
        return float(price) / usdjpy if ticker.endswith(".T") else float(price)
    except Exception:
        return None


def get_market_data(tickers: list) -> dict:
    """複数銘柄の現在値をUSDで返す。取得失敗した銘柄は除外。"""
    usdjpy = get_usdjpy()
    result = {}
    for ticker in tickers:
        price = get_price_usd(ticker, usdjpy)
        if price is not None:
            result[ticker] = price
    return result


def is_jp_market_open() -> bool:
    """東証が開場中か（平日 9:00-15:30 JST）"""
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=0, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now <= close_t


def is_us_market_open() -> bool:
    """NYSE/NASDAQが開場中か（平日 9:30-16:00 ET）"""
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t
