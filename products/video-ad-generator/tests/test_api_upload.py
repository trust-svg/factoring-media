"""画像アップロード API のテスト。"""

import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base
import config
import database


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "UPLOADED_DIR", tmp_path / "uploaded")
    monkeypatch.setattr(config, "PENDING_DIR", tmp_path / "pending")
    (tmp_path / "uploaded").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pending").mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "get_session", lambda: Session(engine))

    from main import app

    return TestClient(app)


def _png_bytes(width=512, height=512) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_upload_creates_job(client):
    files = {"file": ("test.png", _png_bytes(), "image/png")}
    data = {
        "video_prompt": "test motion",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] > 0
    assert body["status"] == "PENDING"


def test_upload_rejects_unsupported_extension(client):
    files = {"file": ("evil.exe", b"x", "application/octet-stream")}
    data = {
        "video_prompt": "x",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 400
    assert "jpg" in resp.json()["detail"]


def test_upload_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE_MB", 1)
    big = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024)
    files = {"file": ("big.png", big, "image/png")}
    data = {
        "video_prompt": "x",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 413


def test_upload_rejects_too_small_resolution(client):
    files = {"file": ("tiny.png", _png_bytes(width=100, height=100), "image/png")}
    data = {
        "video_prompt": "x",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 400
    assert "解像度" in resp.json()["detail"]


def test_upload_blocked_prompt(client):
    files = {"file": ("test.png", _png_bytes(), "image/png")}
    data = {
        "video_prompt": "video of aragaki yui smiling",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 400
