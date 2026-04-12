"""Overview CRUD クエリのユニットテスト（インメモリ SQLite）"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# プロジェクトルートを sys.path に追加
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.models import Base, SalesRecord, Listing, BuyerMessage
from database.crud import (
    get_monthly_achievement,
    get_monthly_calendar,
    get_overview_alerts,
    get_overview_pace,
)


@pytest.fixture
def db():
    """インメモリ DB セッション"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _sale(sold_at, received_jpy=10000, net_profit_jpy=2000, margin=20.0, exchange_rate=150.0, sale_price_usd=66.67):
    return SalesRecord(
        order_id=f"order-{sold_at}",
        sku="TEST-SKU",
        title="Test Item",
        sold_at=sold_at,
        received_jpy=received_jpy,
        net_profit_jpy=net_profit_jpy,
        profit_margin_pct=margin,
        exchange_rate=exchange_rate,
        sale_price_usd=sale_price_usd,
        net_profit_usd=net_profit_jpy / exchange_rate,
    )


def test_get_monthly_achievement_empty(db):
    result = get_monthly_achievement(db, 2026, 4)
    assert result["revenue"]["actual"] == 0
    assert result["profit"]["actual"] == 0
    assert result["revenue"]["target"] == 5_000_000
    assert result["profit"]["target"] == 1_000_000


def test_get_monthly_achievement_with_data(db):
    db.add(_sale(datetime(2026, 4, 1), received_jpy=100_000, net_profit_jpy=20_000))
    db.add(_sale(datetime(2026, 4, 5), received_jpy=200_000, net_profit_jpy=40_000))
    db.commit()

    result = get_monthly_achievement(db, 2026, 4)
    assert result["revenue"]["actual"] == 300_000
    assert result["profit"]["actual"] == 60_000
    assert result["profit_margin"]["actual"] == 20.0


def test_get_monthly_calendar_groups_by_day(db):
    db.add(_sale(datetime(2026, 4, 1, 10, 0), received_jpy=50_000, net_profit_jpy=10_000))
    db.add(_sale(datetime(2026, 4, 1, 15, 0), received_jpy=30_000, net_profit_jpy=6_000))
    db.add(_sale(datetime(2026, 4, 3, 9, 0),  received_jpy=80_000, net_profit_jpy=16_000))
    db.commit()

    result = get_monthly_calendar(db, 2026, 4)
    assert result["year"] == 2026
    assert result["month"] == 4
    assert len(result["days"]) == 30  # April has 30 days

    day1 = next(d for d in result["days"] if d["date"] == "2026-04-01")
    assert day1["revenue"] == 80_000
    assert day1["orders"] == 2

    day3 = next(d for d in result["days"] if d["date"] == "2026-04-03")
    assert day3["revenue"] == 80_000
    assert day3["orders"] == 1

    day2 = next(d for d in result["days"] if d["date"] == "2026-04-02")
    assert day2["revenue"] == 0


def test_get_overview_alerts_severity(db):
    # 空データ → ok
    result = get_overview_alerts(db)
    assert result["severity"] == "ok"
    assert result["out_of_stock"] == 0
    assert result["unread_messages"] == 0

    # 在庫切れ追加 → warning
    db.add(Listing(sku="A", quantity=0))
    db.commit()
    result = get_overview_alerts(db)
    assert result["severity"] == "warning"
    assert result["out_of_stock"] == 1

    # 在庫切れ10件以上 → critical
    for i in range(10):
        db.add(Listing(sku=f"OOS-{i}", quantity=0))
    db.commit()
    result = get_overview_alerts(db)
    assert result["severity"] == "critical"


def test_get_overview_pace_no_data(db):
    result = get_overview_pace(db)
    assert result["today_revenue"] == 0
    assert result["today_orders"] == 0
    assert result["prev_month_same_day_revenue"] == 0
