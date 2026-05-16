"""Procurement 古物台帳統合テスト（インメモリ SQLite）"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.models import Base, Procurement
from database.crud import add_procurement


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_procurement_new_fields_persist(db):
    proc = add_procurement(
        db,
        sku="TEST-001",
        title="テスト商品",
        purchase_price_jpy=5000,
        quantity=2,
        seller_id="mercari_user123",
        seller_url="https://jp.mercari.com/user/profile/123",
        screenshot_path="/data/screenshots/test.png",
        category="道具類",
    )
    fetched = db.query(Procurement).filter(Procurement.id == proc.id).first()
    assert fetched.quantity == 2
    assert fetched.seller_id == "mercari_user123"
    assert fetched.seller_url == "https://jp.mercari.com/user/profile/123"
    assert fetched.screenshot_path == "/data/screenshots/test.png"
    assert fetched.category == "道具類"


def test_procurement_new_fields_default(db):
    proc = add_procurement(
        db, sku="TEST-002", title="デフォルトテスト", purchase_price_jpy=1000
    )
    fetched = db.query(Procurement).filter(Procurement.id == proc.id).first()
    assert fetched.quantity == 1
    assert fetched.seller_id == ""
    assert fetched.category == ""


def test_migrate_procurement_columns_idempotent():
    """_migrate_procurement_columns が既存DBに対して冪等に動作することを確認"""
    from sqlalchemy import create_engine, text
    from database.models import _migrate_procurement_columns

    # カラムなしのスキーマからスタート（Procurementテーブルのみ最小構成で作成）
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE procurements ("
                "id INTEGER PRIMARY KEY, "
                "sku VARCHAR(128), "
                "title VARCHAR(512), "
                "purchase_price_jpy INTEGER DEFAULT 0, "
                "created_at DATETIME"
                ")"
            )
        )
        conn.commit()

    # 1回目: カラム追加
    _migrate_procurement_columns(engine)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(procurements)"))
        cols = {row[1] for row in result.fetchall()}
    assert "quantity" in cols
    assert "seller_id" in cols
    assert "seller_url" in cols
    assert "screenshot_path" in cols
    assert "category" in cols

    # 2回目: 冪等（エラーなし）
    _migrate_procurement_columns(engine)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(procurements)"))
        cols2 = {row[1] for row in result.fetchall()}
    assert cols == cols2  # 同じカラムセットのまま


def test_update_procurement_category(db):
    from database.crud import update_procurement

    proc = add_procurement(
        db, sku="TEST-003", title="更新テスト", purchase_price_jpy=2000
    )
    updated = update_procurement(db, proc.id, category="機械工具類", quantity=3)
    assert updated.category == "機械工具類"
    assert updated.quantity == 3


def test_ledger_csv_columns(db):
    import datetime

    add_procurement(
        db,
        sku="CSV-001",
        title="テスト品",
        purchase_price_jpy=3000,
        purchase_date=datetime.datetime(2026, 5, 16),
        platform="メルカリ",
        category="道具類",
        seller_id="seller001",
        quantity=1,
    )
    procs = db.query(Procurement).all()
    import csv, io

    output = io.StringIO()
    writer = csv.writer(output)
    HEADERS = [
        "取引年月日",
        "品名",
        "数量",
        "取得価格(円)",
        "古物区分",
        "仕入先",
        "仕入先URL",
        "出品者ID",
        "出品者URL",
        "取引証跡パス",
    ]
    writer.writerow(HEADERS)
    for p in procs:
        writer.writerow(
            [
                p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                p.title,
                p.quantity,
                p.purchase_price_jpy,
                p.category,
                p.platform,
                p.url or "",
                p.seller_id or "",
                p.seller_url or "",
                p.screenshot_path or "",
            ]
        )
    output.seek(0)
    reader = csv.DictReader(output)
    rows = list(reader)
    assert rows[0]["品名"] == "テスト品"
    assert rows[0]["古物区分"] == "道具類"
    assert rows[0]["出品者ID"] == "seller001"
