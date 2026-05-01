import enum
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    String,
    Float,
    DateTime,
    Enum,
    Integer,
    Boolean,
    ForeignKey,
)
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


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), default="custom")
    image_prompt: Mapped[str] = mapped_column(String(2000))
    video_prompt: Mapped[str] = mapped_column(String(2000))
    default_provider: Mapped[str] = mapped_column(String(50), default="seedance")
    default_aspect: Mapped[str] = mapped_column(String(10), default="9:16")
    default_duration: Mapped[int] = mapped_column(Integer, default=10)
    default_camera_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_quality: Mapped[str] = mapped_column(String(16), default="low")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str | None] = mapped_column(String(4), nullable=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id"), nullable=True
    )
    prompt: Mapped[str] = mapped_column(String(2000))
    provider: Mapped[str] = mapped_column(String(50), default="seedance")
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=10)
    camera_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_source: Mapped[str] = mapped_column(String(20), default="generated")
    quality: Mapped[str] = mapped_column(String(16), default="low")
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING
    )
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_cost_usd: Mapped[float] = mapped_column(Float, default=0.02)
    video_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    video_cost_calc_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    video_progress_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    atlas_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
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
