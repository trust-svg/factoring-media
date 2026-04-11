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
