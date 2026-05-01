"""GET /api/jobs/cost-summary エンドポイントのテスト。

provider 別集計と日付フィルタを検証する。
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base, Job, JobStatus
import database
import api.jobs as jobs_mod


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    # Patch all namespaces that captured get_session at import time
    monkeypatch.setattr(database, "get_session", lambda: Session(engine))
    monkeypatch.setattr(jobs_mod, "get_session", lambda: Session(engine))

    from main import app

    return TestClient(app)


def _add_job(client_fixture, engine_ref, provider: str, cost: float):
    """in-memory engine に直接 Job を挿入する。"""
    with Session(engine_ref) as session:
        job = Job(
            prompt="x",
            provider=provider,
            aspect_ratio="9:16",
            duration_seconds=10,
            image_source="generated",
            status=JobStatus.DONE,
            image_cost_usd=0.02,
            video_cost_usd=cost,
        )
        session.add(job)
        session.commit()


# ---------- fixtures with engine access ----------


@pytest.fixture
def client_with_engine(monkeypatch):
    """_add_job のためエンジン参照も返すフィクスチャ。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    monkeypatch.setattr(database, "get_session", lambda: Session(engine))
    monkeypatch.setattr(jobs_mod, "get_session", lambda: Session(engine))

    from main import app

    return TestClient(app), engine


def test_cost_summary_aggregates_by_provider(client_with_engine):
    client, engine = client_with_engine
    _add_job(client, engine, "seedance", 0.81)
    _add_job(client, engine, "seedance", 0.81)
    _add_job(client, engine, "veo3_lite", 0.40)
    _add_job(client, engine, "kling3_pro", 0.46)

    resp = client.get("/api/jobs/cost-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_video_cost_usd"] == pytest.approx(2.48, abs=0.01)
    by_provider = {p["provider"]: p for p in data["by_provider"]}
    assert by_provider["seedance"]["count"] == 2
    assert by_provider["seedance"]["total_usd"] == pytest.approx(1.62, abs=0.01)
    assert by_provider["veo3_lite"]["count"] == 1
    assert by_provider["kling3_pro"]["count"] == 1


def test_cost_summary_date_filter(client_with_engine):
    client, engine = client_with_engine
    _add_job(client, engine, "seedance", 0.81)
    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(f"/api/jobs/cost-summary?from={today}&to={today}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_video_cost_usd"] >= 0.81
