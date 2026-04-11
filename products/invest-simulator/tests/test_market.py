import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from unittest.mock import patch, MagicMock
from datetime import datetime
import pytz


def make_mock_ticker(price: float):
    m = MagicMock()
    m.fast_info.last_price = price
    return m


def test_get_usdjpy(monkeypatch):
    import market
    with patch("yfinance.Ticker", return_value=make_mock_ticker(150.0)):
        rate = market.get_usdjpy()
    assert rate == 150.0


def test_get_price_usd_us_stock(monkeypatch):
    import market
    with patch("yfinance.Ticker", return_value=make_mock_ticker(175.0)):
        price = market.get_price_usd("AAPL", 150.0)
    assert price == 175.0


def test_get_price_usd_jp_stock(monkeypatch):
    import market
    with patch("yfinance.Ticker", return_value=make_mock_ticker(3000.0)):
        # 3000円 / 150 = $20.0
        price = market.get_price_usd("7203.T", 150.0)
    assert abs(price - 20.0) < 0.01


def test_get_market_data(monkeypatch):
    import market

    def mock_ticker(t):
        prices = {"AAPL": 175.0, "NVDA": 500.0}
        m = MagicMock()
        m.fast_info.last_price = prices.get(t, 0)
        return m

    with patch("yfinance.Ticker", side_effect=mock_ticker):
        with patch.object(market, "get_usdjpy", return_value=150.0):
            data = market.get_market_data(["AAPL", "NVDA"])
    assert data["AAPL"] == 175.0
    assert data["NVDA"] == 500.0


def test_is_jp_market_open_weekday_hours():
    import market
    jst = pytz.timezone("Asia/Tokyo")
    # 月曜 10:00 JST → 開場中
    mock_now = jst.localize(datetime(2026, 4, 13, 10, 0, 0))
    with patch("market.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = market.is_jp_market_open()
    assert result is True


def test_is_jp_market_closed_weekend():
    import market
    jst = pytz.timezone("Asia/Tokyo")
    # 土曜 10:00 JST → 閉場
    mock_now = jst.localize(datetime(2026, 4, 11, 10, 0, 0))
    with patch("market.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = market.is_jp_market_open()
    assert result is False


def test_is_us_market_open_weekday_hours():
    import market
    et = pytz.timezone("America/New_York")
    # 月曜 10:00 ET → 開場中
    mock_now = et.localize(datetime(2026, 4, 13, 10, 0, 0))
    with patch("market.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = market.is_us_market_open()
    assert result is True
