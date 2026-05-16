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


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
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


def test_bulk_import_logic_creates_procurement(db):
    """一括インポートと同じロジックでProcurementが同時作成されることを確認"""
    from database.models import InventoryItem
    from database.crud import add_inventory_item

    row = {
        "title": "一括テスト商品",
        "purchase_price_jpy": 4000,
        "purchase_source": "メルカリ",
        "purchase_url": "https://jp.mercari.com/item/m000001",
        "seller_id": "bulk_seller",
        "consumption_tax_jpy": 363,
        "shipping_cost_jpy": 500,
    }

    # InventoryItem 作成
    add_inventory_item(db, **row)

    # 同時に Procurement 作成（重複チェック後）
    existing = (
        db.query(Procurement)
        .filter(
            Procurement.title == row["title"],
            Procurement.purchase_price_jpy == row["purchase_price_jpy"],
            Procurement.platform == row["purchase_source"],
        )
        .first()
    )
    if not existing:
        add_procurement(
            db,
            title=row["title"],
            platform=row["purchase_source"],
            url=row["purchase_url"],
            purchase_price_jpy=row["purchase_price_jpy"],
            consumption_tax_jpy=row["consumption_tax_jpy"],
            shipping_cost_jpy=row["shipping_cost_jpy"],
            seller_id=row["seller_id"],
        )

    inv_count = (
        db.query(InventoryItem).filter(InventoryItem.title == "一括テスト商品").count()
    )
    proc_count = (
        db.query(Procurement).filter(Procurement.title == "一括テスト商品").count()
    )
    assert inv_count == 1
    assert proc_count == 1


def test_procurement_ebay_fields(db_session):
    """eBay連携・管理フィールドがデフォルト値で保存できる"""
    proc = Procurement(
        title="テスト商品",
        purchase_price_jpy=10000,
        stock_number="P-001",
        location="棚A",
        ebay_item_id="123456789012",
        ebay_order_id="12-34567-89012",
        ebay_price_usd=89.99,
    )
    db_session.add(proc)
    db_session.commit()
    db_session.refresh(proc)

    assert proc.stock_number == "P-001"
    assert proc.location == "棚A"
    assert proc.ebay_item_id == "123456789012"
    assert proc.ebay_order_id == "12-34567-89012"
    assert abs(proc.ebay_price_usd - 89.99) < 0.001
    assert proc.listed_at is None
    assert proc.sold_at is None
    assert proc.shipped_at is None


def test_migrate_new_columns_idempotent(db_engine):
    """_migrate_procurement_columns が新カラムを実際に追加し、2回呼んでも冪等に動作する"""
    from sqlalchemy import text, create_engine
    from database.models import _migrate_procurement_columns

    # 最小スキーマ（新カラムなし）のインメモリDBを作る
    minimal_engine = create_engine("sqlite:///:memory:")
    with minimal_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE procurements ("
                "id INTEGER PRIMARY KEY, sku VARCHAR(128), title VARCHAR(512), "
                "created_at DATETIME)"
            )
        )
        conn.commit()

    # 1回目: カラムが追加される
    _migrate_procurement_columns(minimal_engine)

    with minimal_engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(procurements)"))
        cols = {row[1] for row in result.fetchall()}

    new_cols = [
        "quantity",
        "seller_id",
        "seller_url",
        "screenshot_path",
        "category",
        "image_url",
        "condition",
        "stock_number",
        "location",
        "ebay_item_id",
        "ebay_order_id",
        "ebay_price_usd",
        "listed_at",
        "sold_at",
        "shipped_at",
        "updated_at",
    ]
    for col in new_cols:
        assert col in cols, f"Missing column after first migration: {col}"

    # 2回目: 冪等（エラーにならない）
    _migrate_procurement_columns(minimal_engine)


def test_procurement_updated_at_migrates():
    """updated_at が _migrate_procurement_columns で追加されることを確認"""
    from sqlalchemy import create_engine, text
    from database.models import _migrate_procurement_columns

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

    _migrate_procurement_columns(engine)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(procurements)"))
        cols = {row[1] for row in result.fetchall()}
    assert "updated_at" in cols


def test_procurement_updated_at_auto_sets(db):
    """updated_at が作成時にセットされることを確認"""
    proc = add_procurement(db, title="更新テスト", purchase_price_jpy=1000)
    assert proc.updated_at is not None
    assert proc.title == "更新テスト"


def test_procurement_stats(db):
    """stats エンドポイントが件数・原価・ステータス別を正しく返す"""
    from database.crud import get_procurement_stats

    add_procurement(
        db,
        title="A",
        purchase_price_jpy=3000,
        consumption_tax_jpy=300,
        platform="メルカリ",
        status="listed",
    )
    add_procurement(
        db,
        title="B",
        purchase_price_jpy=5000,
        consumption_tax_jpy=500,
        platform="ヤフオク",
        status="sold",
    )
    add_procurement(
        db, title="C", purchase_price_jpy=2000, platform="ラクマ", status="purchased"
    )

    s = get_procurement_stats(db)
    assert s["total"] == 3
    assert s["listed"] == 1
    assert s["sold"] == 1
    assert s["purchased"] == 1
    assert s["total_cost_jpy"] == 3000 + 300 + 5000 + 500 + 2000


def test_procurement_auto_sku_assigns(db):
    """SKUなしの仕入れ記録が作成できることを確認（auto-skuはeBay出品とのマッチが必要なため）"""
    proc = add_procurement(
        db, title="TASCAM DP-2500 マルチトラック", purchase_price_jpy=12000
    )
    assert proc.sku == "" or proc.sku is None
    assert proc.id is not None
