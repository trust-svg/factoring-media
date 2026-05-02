import sys
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, Job, JobStatus
import database
import api.approve as approve_mod
import api.generate as gen_mod
import api.jobs as jobs_mod
import api.upload as upload_mod
from core.video_providers.seedance import SeedanceProvider
from core.video_providers.kling import Kling3ProProvider


@pytest.fixture
def use_test_db(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_session():
        return Session(engine)

    monkeypatch.setattr(database, "get_session", override_get_session)
    monkeypatch.setattr(approve_mod, "get_session", override_get_session)
    monkeypatch.setattr(gen_mod, "get_session", override_get_session)
    monkeypatch.setattr(jobs_mod, "get_session", override_get_session)
    monkeypatch.setattr(upload_mod, "get_session", override_get_session)
    monkeypatch.setattr(approve_mod, "APPROVED_DIR", tmp_path)
    monkeypatch.setattr(approve_mod, "VIDEOS_DIR", tmp_path)


@pytest.fixture
def client(use_test_db):
    from main import app

    with TestClient(app) as c:
        yield c


def _make_job(tmp_path: Path, provider: str, quality: str, duration: int = 10) -> int:
    img = tmp_path / "img.jpg"
    img.write_bytes(b"i")
    with database.get_session() as s:
        job = Job(
            pattern="A",
            prompt="test prompt",
            provider=provider,
            aspect_ratio="9:16",
            duration_seconds=duration,
            camera_preset=None,
            image_source="generated",
            quality=quality,
            image_path=str(img),
            status=JobStatus.PENDING,
        )
        s.add(job)
        s.commit()
        return job.id


def test_approve_passes_quality_to_provider(client, tmp_path, monkeypatch):
    captured = {}

    async def fake_generate(self, req):
        captured["quality"] = req.quality
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        req.output_path.write_bytes(b"v")
        return req.output_path

    monkeypatch.setattr(SeedanceProvider, "generate", fake_generate)

    job_id = _make_job(tmp_path, provider="seedance", quality="high")

    r = client.post(f"/api/approve/{job_id}")
    assert r.status_code == 200

    assert captured["quality"] == "high"


def test_approve_writes_provider_cost_basis_seedance(client, tmp_path, monkeypatch):
    async def fake_generate(self, req):
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        req.output_path.write_bytes(b"v")
        return req.output_path

    monkeypatch.setattr(SeedanceProvider, "generate", fake_generate)

    job_id = _make_job(tmp_path, provider="seedance", quality="low")

    r = client.post(f"/api/approve/{job_id}")
    assert r.status_code == 200

    with database.get_session() as s:
        job = s.get(Job, job_id)
        assert job.video_cost_calc_basis == "per_video"


def test_approve_writes_provider_cost_basis_kling(client, tmp_path, monkeypatch):
    async def fake_generate(self, req):
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        req.output_path.write_bytes(b"v")
        return req.output_path

    monkeypatch.setattr(Kling3ProProvider, "generate", fake_generate)

    job_id = _make_job(tmp_path, provider="kling3_pro", quality="low", duration=10)

    r = client.post(f"/api/approve/{job_id}")
    assert r.status_code == 200

    with database.get_session() as s:
        job = s.get(Job, job_id)
        assert job.video_cost_calc_basis == "per_video"
