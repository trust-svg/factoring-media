import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import pytest
from datetime import datetime


def test_init_db_creates_tables(tmp_db):
    import db
    db.init_db()
    portfolio = db.get_portfolio()
    assert portfolio["cash_jp"] == 5000.0
    assert portfolio["cash_us"] == 5000.0


def test_update_cash(tmp_db):
    import db
    db.init_db()
    db.update_cash("JP", -1000.0)
    p = db.get_portfolio()
    assert p["cash_jp"] == 4000.0


def test_upsert_and_get_position(tmp_db):
    import db
    db.init_db()
    db.upsert_position("7203.T", "JP", 10, 2500.0)
    pos = db.get_position("7203.T")
    assert pos["shares"] == 10
    assert pos["avg_cost"] == 2500.0

    # 追加購入 → 平均取得単価が更新される
    db.upsert_position("7203.T", "JP", 10, 3000.0)
    pos = db.get_position("7203.T")
    assert pos["shares"] == 20
    assert pos["avg_cost"] == 2750.0


def test_reduce_position(tmp_db):
    import db
    db.init_db()
    db.upsert_position("AAPL", "US", 5, 150.0)
    result = db.reduce_position("AAPL", 3)
    assert result is True
    pos = db.get_position("AAPL")
    assert pos["shares"] == 2


def test_reduce_position_full_sell(tmp_db):
    import db
    db.init_db()
    db.upsert_position("AAPL", "US", 5, 150.0)
    db.reduce_position("AAPL", 5)
    pos = db.get_position("AAPL")
    assert pos is None


def test_reduce_position_insufficient(tmp_db):
    import db
    db.init_db()
    db.upsert_position("AAPL", "US", 2, 150.0)
    result = db.reduce_position("AAPL", 5)
    assert result is False


def test_record_and_get_trades(tmp_db):
    import db
    db.init_db()
    db.record_trade("AAPL", "US", "BUY", 5, 150.0, "成長期待", None)
    db.record_trade("AAPL", "US", "SELL", 5, 165.0, "利確+8%", 75.0)
    trades = db.get_trades()
    assert len(trades) == 2
    assert trades[0]["action"] == "SELL"  # 直近順


def test_record_snapshot(tmp_db):
    import db
    db.init_db()
    db.record_snapshot(10500.0)
    snapshots = db.get_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["total_value"] == 10500.0


def test_reset_db(tmp_db):
    import db
    db.init_db()
    db.upsert_position("AAPL", "US", 5, 150.0)
    db.record_trade("AAPL", "US", "BUY", 5, 150.0, "test", None)
    db.reset_db()
    assert db.get_positions() == []
    assert db.get_trades() == []
    p = db.get_portfolio()
    assert p["cash_jp"] == 5000.0
