import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from unittest.mock import patch, MagicMock


def make_tool_use_response(tool_name: str, inputs: dict):
    """Anthropic tool_use レスポンスのモックを生成"""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = inputs

    response = MagicMock()
    response.content = [block]
    return response


def test_buy_stock_cycle(tmp_db, monkeypatch):
    """Claudeが buy_stock を選択 → ポジションが作られ現金が減る"""
    import db
    db.init_db()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    mock_response = make_tool_use_response(
        "buy_stock",
        {"ticker": "AAPL", "shares": 5, "reason": "成長期待"}
    )

    with patch("anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = mock_response
        with patch("market.get_market_data", return_value={"AAPL": 150.0, "NVDA": 500.0, "MSFT": 300.0, "GOOGL": 170.0, "AMZN": 180.0, "TSLA": 250.0, "META": 450.0, "AMD": 160.0}):
            with patch("market.get_usdjpy", return_value=150.0):
                import trader
                result = trader.run_trading_cycle("US")

    assert result["action"] == "buy"
    pos = db.get_position("AAPL")
    assert pos["shares"] == 5
    portfolio = db.get_portfolio()
    assert portfolio["cash_us"] < 5000.0


def test_sell_stock_cycle(tmp_db, monkeypatch):
    """Claudeが sell_stock を選択 → ポジションが減り現金が増える"""
    import db
    db.init_db()
    db.upsert_position("AAPL", "US", 5, 150.0)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    mock_response = make_tool_use_response(
        "sell_stock",
        {"ticker": "AAPL", "shares": 5, "reason": "利確+8%"}
    )

    with patch("anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = mock_response
        with patch("market.get_market_data", return_value={"AAPL": 162.0}):
            with patch("market.get_usdjpy", return_value=150.0):
                import trader
                result = trader.run_trading_cycle("US")

    assert result["action"] == "sell"
    pos = db.get_position("AAPL")
    assert pos is None
    trades = db.get_trades()
    sell_trade = next(t for t in trades if t["action"] == "SELL")
    assert abs(sell_trade["pnl"] - 60.0) < 0.01


def test_hold_cycle(tmp_db, monkeypatch):
    """Claudeが hold を選択 → ポジション変化なし"""
    import db
    db.init_db()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    mock_response = make_tool_use_response(
        "hold",
        {"reason": "様子見"}
    )

    with patch("anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = mock_response
        with patch("market.get_market_data", return_value={}):
            with patch("market.get_usdjpy", return_value=150.0):
                import trader
                result = trader.run_trading_cycle("JP")

    assert result["action"] == "hold"
    assert db.get_positions() == []
