"""拡張 /api/generate/image エンドポイントのテスト。

provider / aspect_ratio / duration_seconds / camera_preset / image_source /
template_id の各パラメータが Job に正しく保存されることを確認する。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base
import database
import api.generate as gen_mod
import core.templates as tmpl_mod


@pytest.fixture
def client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    # Patch all three namespaces that captured get_session at import time
    monkeypatch.setattr(database, "get_session", lambda: Session(engine))
    monkeypatch.setattr(gen_mod, "get_session", lambda: Session(engine))
    monkeypatch.setattr(tmpl_mod, "get_session", lambda: Session(engine))

    from main import app

    return TestClient(app)


def test_generate_image_with_extended_params(client, monkeypatch):
    captured = {}

    async def fake_image_gen(prompt, output_path):
        captured["prompt"] = prompt
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake")

    monkeypatch.setattr(gen_mod, "generate_image", fake_image_gen)

    resp = client.post(
        "/api/generate/image",
        json={
            "image_prompt": "Portrait of a fictional character",
            "video_prompt": "she smiles",
            "provider": "kling3_pro",
            "aspect_ratio": "1:1",
            "duration_seconds": 5,
            "camera_preset": "dolly_in",
            "image_source": "generated",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    job_id = body["job_id"]

    import database as db_mod

    with db_mod.get_session() as session:
        job = session.get(db_mod.Job, job_id)
        assert job.provider == "kling3_pro"
        assert job.aspect_ratio == "1:1"
        assert job.duration_seconds == 5
        assert job.camera_preset == "dolly_in"
        assert job.image_source == "generated"


def test_generate_image_with_template_id(client, monkeypatch):
    async def fake_image_gen(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake")

    monkeypatch.setattr(gen_mod, "generate_image", fake_image_gen)

    cid = client.post(
        "/api/templates",
        json={
            "name": "T1",
            "category": "custom",
            "image_prompt": "img",
            "video_prompt": "vid",
            "default_provider": "veo3_lite",
            "default_aspect": "16:9",
            "default_duration": 6,
            "default_camera_preset": "pan_left",
        },
    ).json()["id"]

    resp = client.post("/api/generate/image", json={"template_id": cid})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    import database as db_mod

    with db_mod.get_session() as session:
        job = session.get(db_mod.Job, job_id)
        assert job.template_id == cid
        assert job.provider == "veo3_lite"
        assert job.aspect_ratio == "16:9"
        assert job.duration_seconds == 6
        assert job.camera_preset == "pan_left"


def test_generate_image_blocked_prompt(client):
    resp = client.post(
        "/api/generate/image",
        json={
            "image_prompt": "aragaki yui",
            "video_prompt": "v",
            "provider": "seedance",
            "aspect_ratio": "9:16",
            "duration_seconds": 10,
        },
    )
    assert resp.status_code == 400
