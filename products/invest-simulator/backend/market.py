import os
import requests
import time
from datetime import datetime, date
from typing import Optional
import pytz
import holidays as holidays_lib

STOOQ_URL = "https://stooq.com/q/l/?s={ticker}&f=sd2t2ohlcv&h&e=csv"
TWELVEDATA_URL = "https://api.twelvedata.com/price?symbol={symbol}&apikey={key}"
CACHE_TTL = 20 * 60        # 20分キャッシュ
BACKOFF_TTL = 60 * 60      # API失敗後1時間バックオフ

_cache: dict = {}          # {ticker: (price, timestamp)}
_failed_at: float = 0.0    # 最後にAPI全失敗した時刻

# 祝日カレンダー（毎年自動更新）
_jp_holidays = holidays_lib.Japan()
_us_holidays = holidays_lib.NYSE()


def _get_cache(ticker: str) -> Optional[float]:
    if ticker in _cache:
        price, ts = _cache[ticker]
        if time.time() - ts < CACHE_TTL:
            return price
    return None


def _set_cache(ticker: str, price: float) -> None:
    _cache[ticker] = (price, time.time())


def _fetch_twelvedata(ticker: str) -> Optional[float]:
    """Twelve Data APIで価格取得（800クレジット/日、サーバーIPフレンドリー）。"""
    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        return None
    try:
        # .T suffix (東証) → Twelve Data形式: 7203:TSE
        if ticker == "USDJPY=X":
            symbol = "USD/JPY"
        elif ticker.endswith(".T"):
            symbol = ticker[:-2] + ":TSE"
        else:
            symbol = ticker
        r = requests.get(
            TWELVEDATA_URL.format(symbol=symbol, key=api_key), timeout=10
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if "price" not in data:
            return None
        price = float(data["price"])
        return price if price > 0 else None
    except Exception:
        return None


def _fetch_yfinance(ticker: str) -> Optional[float]:
    """yfinanceライブラリで価格取得（セッション・Cookie管理込み）。"""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
        return price if price > 0 else None
    except Exception:
        return None


def _fetch_stooq(ticker: str) -> Optional[float]:
    """Stooqから最新終値を取得（フォールバック）。"""
    try:
        if ticker == "USDJPY=X":
            stooq_sym = "usdjpy"
        elif ticker.endswith(".T"):
            stooq_sym = ticker[:-2] + ".JP"
        elif "." not in ticker:
            stooq_sym = ticker + ".US"
        else:
            stooq_sym = ticker
        r = requests.get(STOOQ_URL.format(ticker=stooq_sym), timeout=10)
        if r.status_code != 200:
            return None
        lines = [l for l in r.text.strip().splitlines() if l and not l.startswith("Symbol")]
        if not lines:
            return None
        close = lines[-1].split(",")[6]
        if not close or close in ("N/D", "Exceeded", ""):
            return None
        return float(close)
    except Exception:
        return None


def _fetch_price(ticker: str) -> Optional[float]:
    """キャッシュ確認 → yfinance → Stooq の順で価格取得。バックオフ中はNoneを返す。"""
    global _failed_at
    cached = _get_cache(ticker)
    if cached is not None:
        return cached

    # バックオフ中（前回の全失敗から1時間以内）はAPIを叩かない
    if _failed_at and time.time() - _failed_at < BACKOFF_TTL:
        return None

    price = _fetch_twelvedata(ticker)
    if not price or price <= 0:
        price = _fetch_yfinance(ticker)
    if not price or price <= 0:
        price = _fetch_stooq(ticker)

    if price and price > 0:
        _set_cache(ticker, price)
        return price
    return None


def mark_api_failure() -> None:
    """全ソースで取得失敗した場合に呼び出し、バックオフを開始する。"""
    global _failed_at
    _failed_at = time.time()


def clear_backoff() -> None:
    """バックオフをリセット（テスト・手動実行用）。"""
    global _failed_at
    _failed_at = 0.0


def get_usdjpy() -> float:
    price = _fetch_price("USDJPY=X")
    return price if price else 150.0


def get_market_data(tickers: list) -> dict:
    """複数銘柄の現在値をUSDで返す。取得失敗した銘柄は除外。"""
    if not tickers:
        return {}
    usdjpy = get_usdjpy()
    result = {}
    for ticker in tickers:
        price = _fetch_price(ticker)
        if price is not None and price > 0:
            result[ticker] = price / usdjpy if ticker.endswith(".T") else price
    return result


def is_jp_market_open() -> bool:
    """東証が開場中か（平日・祝日除く 9:00-15:30 JST）"""
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst)
    if now.weekday() >= 5:
        return False
    if date(now.year, now.month, now.day) in _jp_holidays:
        return False
    open_t = now.replace(hour=9, minute=0, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now <= close_t


def is_us_market_open() -> bool:
    """NYSE/NASDAQが開場中か（平日・祝日除く 9:30-16:00 ET）"""
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return False
    if date(now.year, now.month, now.day) in _us_holidays:
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t
