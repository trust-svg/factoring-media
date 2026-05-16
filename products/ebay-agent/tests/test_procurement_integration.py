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
