"""テンプレート CRUD ロジックのテスト。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base, Template
from core import templates as tmpl_mod


@pytest.fixture
def session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(tmpl_mod, "get_session", lambda: Session(engine))
    yield engine
    engine.dispose()


def test_create_template(session):
    t = tmpl_mod.create_template(
        name="商品紹介テンプレ",
        category="product",
        image_prompt="white background product photo",
        video_prompt="slow zoom in on product",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    assert t.id is not None
    assert t.name == "商品紹介テンプレ"
    assert t.is_archived is False


def test_create_template_blocks_unsafe_prompt(session):
    with pytest.raises(ValueError, match="ブロック"):
        tmpl_mod.create_template(
            name="bad",
            category="product",
            image_prompt="photo of celebrity actress",
            video_prompt="slow zoom",
            default_provider="kling",
            default_aspect="16:9",
            default_duration=5,
            default_camera_preset=None,
        )


def test_list_templates_excludes_archived_by_default(session):
    tmpl_mod.create_template(
        name="active",
        category="product",
        image_prompt="nice product",
        video_prompt="zoom",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    archived = tmpl_mod.create_template(
        name="archived",
        category="product",
        image_prompt="old product",
        video_prompt="pan",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    tmpl_mod.archive_template(archived.id)
    results = tmpl_mod.list_templates()
    names = [r.name for r in results]
    assert "active" in names
    assert "archived" not in names


def test_list_templates_with_archived(session):
    tmpl_mod.create_template(
        name="active2",
        category="product",
        image_prompt="nice product2",
        video_prompt="zoom2",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    archived = tmpl_mod.create_template(
        name="archived2",
        category="product",
        image_prompt="old product2",
        video_prompt="pan2",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    tmpl_mod.archive_template(archived.id)
    results = tmpl_mod.list_templates(include_archived=True)
    names = [r.name for r in results]
    assert "active2" in names
    assert "archived2" in names


def test_update_template(session):
    t = tmpl_mod.create_template(
        name="original",
        category="product",
        image_prompt="photo",
        video_prompt="zoom",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    updated = tmpl_mod.update_template(t.id, name="updated name", default_duration=10)
    assert updated.name == "updated name"
    assert updated.default_duration == 10


def test_filter_by_category(session):
    tmpl_mod.create_template(
        name="prod_tmpl",
        category="product",
        image_prompt="product shot",
        video_prompt="zoom in",
        default_provider="kling",
        default_aspect="16:9",
        default_duration=5,
        default_camera_preset=None,
    )
    tmpl_mod.create_template(
        name="event_tmpl",
        category="event",
        image_prompt="event scene",
        video_prompt="wide pan",
        default_provider="veo3",
        default_aspect="9:16",
        default_duration=8,
        default_camera_preset=None,
    )
    results = tmpl_mod.list_templates(category="product")
    assert all(r.category == "product" for r in results)
    assert any(r.name == "prod_tmpl" for r in results)
    assert not any(r.name == "event_tmpl" for r in results)
