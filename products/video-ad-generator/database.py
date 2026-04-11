import enum
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, String, Float, DateTime, Enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from config import DB_PATH


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VIDEO_GENERATING = "VIDEO_GENERATING"
    DONE = "DONE"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(4))
    prompt: Mapped[str] = mapped_column(String(2000))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_cost_usd: Mapped[float] = mapped_column(Float, default=0.02)
    video_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    atlas_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def get_engine():
    return create_engine(f"sqlite:///{DB_PATH}")


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    engine = get_engine()
    return Session(engine)
