import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import pytest
from unittest.mock import patch


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("INITIAL_CAPITAL", "10000")
    monkeypatch.setenv("JP_ALLOCATION", "0.5")
    monkeypatch.setenv("US_ALLOCATION", "0.5")
    monkeypatch.setenv("CHECK_INTERVAL_MINUTES", "99999")

    with patch("scheduler.create_scheduler") as mock_sched:
        mock_sched.return_value.start = lambda: None
        mock_sched.return_value.shutdown = lambda: None
        mock_sched.return_value.running = False

        from fastapi.testclient import TestClient
        import importlib, main
        importlib.reload(main)
        yield TestClient(main.app)


def test_get_portfolio(client):
    with patch("market.get_usdjpy", return_value=150.0):
        with patch("market.get_market_data", return_value={}):
            resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash_jp"] == 5000.0
    assert data["cash_us"] == 5000.0
    assert abs(data["total_value"] - 10000.0) < 0.01
    assert abs(data["pnl"] - 0.0) < 0.01


def test_get_positions_empty(client):
    with patch("market.get_market_data", return_value={}):
        resp = client.get("/api/positions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_trades_empty(client):
    resp = client.get("/api/trades")
    assert resp.status_code == 200
    assert resp.json() == []


def test_reset(client):
    import db
    db.upsert_position("AAPL", "US", 5, 150.0)
    resp = client.post("/api/reset")
    assert resp.status_code == 200
    assert db.get_positions() == []


def test_get_snapshots_empty(client):
    resp = client.get("/api/snapshots")
    assert resp.status_code == 200
    assert resp.json() == []
