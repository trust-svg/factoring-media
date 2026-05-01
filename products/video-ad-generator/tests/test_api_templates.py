"""テンプレート CRUD REST API のテスト。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base
import core.templates as tmpl_mod


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(tmpl_mod, "get_session", lambda: Session(engine))

    from main import app

    return TestClient(app)


def test_create_template(client):
    resp = client.post(
        "/api/templates",
        json={
            "name": "T1",
            "category": "custom",
            "image_prompt": "img",
            "video_prompt": "vid",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": None,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] > 0


def test_list_templates(client):
    client.post(
        "/api/templates",
        json={
            "name": "T1",
            "category": "custom",
            "image_prompt": "img",
            "video_prompt": "vid",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": None,
        },
    )
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["name"] == "T1" for t in data)


def test_blocked_word_returns_400(client):
    resp = client.post(
        "/api/templates",
        json={
            "name": "bad",
            "category": "custom",
            "image_prompt": "aragaki yui",
            "video_prompt": "vid",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": None,
        },
    )
    assert resp.status_code == 400


def test_update_template(client):
    cid = client.post(
        "/api/templates",
        json={
            "name": "T1",
            "category": "custom",
            "image_prompt": "img",
            "video_prompt": "vid",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": None,
        },
    ).json()["id"]
    resp = client.patch(f"/api/templates/{cid}", json={"name": "T2"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "T2"


def test_archive_template(client):
    cid = client.post(
        "/api/templates",
        json={
            "name": "T1",
            "category": "custom",
            "image_prompt": "img",
            "video_prompt": "vid",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": None,
        },
    ).json()["id"]
    resp = client.delete(f"/api/templates/{cid}")
    assert resp.status_code == 204
    listed = client.get("/api/templates").json()
    assert all(t["id"] != cid for t in listed)
    listed_all = client.get("/api/templates?include_archived=true").json()
    assert any(t["id"] == cid for t in listed_all)
