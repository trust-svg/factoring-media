import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database import Base, Job, JobStatus, init_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_job(db):
    job = Job(
        pattern="A",
        prompt="A Japanese woman in her 40s at a cafe",
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    assert job.id is not None
    assert job.status == JobStatus.PENDING
    assert job.image_path is None
    assert job.video_path is None


def test_job_status_transitions(db):
    job = Job(pattern="B", prompt="test", status=JobStatus.PENDING)
    db.add(job)
    db.commit()

    job.status = JobStatus.APPROVED
    db.commit()
    db.refresh(job)
    assert job.status == JobStatus.APPROVED


def test_template_model_creates():
    from database import Template, Base, JobStatus
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        t = Template(
            name="テスト",
            category="custom",
            image_prompt="img",
            video_prompt="vid",
            default_provider="seedance",
            default_aspect="9:16",
            default_duration=10,
            is_archived=False,
        )
        session.add(t)
        session.commit()
        assert t.id is not None


def test_job_has_new_columns():
    from database import Job, Base
    from sqlalchemy import create_engine, inspect

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert "template_id" in cols
    assert "provider" in cols
    assert "aspect_ratio" in cols
    assert "duration_seconds" in cols
    assert "camera_preset" in cols
    assert "image_source" in cols
    assert "video_progress_stage" in cols
    assert "video_cost_calc_basis" in cols
