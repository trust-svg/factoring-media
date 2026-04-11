import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, Job, JobStatus

@pytest.fixture(autouse=True)
def use_test_db(tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    import database

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_session():
        return TestingSessionLocal()

    monkeypatch.setattr(database, "get_session", override_get_session)

@pytest.fixture
def client():
    from main import app
    with TestClient(app) as c:
        yield c

def test_get_stats_empty(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["total_jobs"] == 0
    assert d["done"] == 0

def test_generate_single_image_invalid_pattern(client):
    r = client.post("/api/generate/image", json={"pattern": "Z"})
    assert r.status_code == 400

def test_generate_single_image_blocked_prompt(client):
    r = client.post("/api/generate/image", json={
        "pattern": "A",
        "custom_prompt": "photo of Yui Aragaki smiling"
    })
    assert r.status_code == 400

def test_approve_nonexistent_job(client):
    r = client.post("/api/approve/99999")
    assert r.status_code == 404

def test_reject_nonexistent_job(client):
    r = client.post("/api/reject/99999")
    assert r.status_code == 404

def test_list_jobs_empty(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []
