import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import String, Integer, Float, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JST = timezone(timedelta(hours=9))


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    grade: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    skill: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), default="ai_generated")
    exam_year: Mapped[int] = mapped_column(Integer, nullable=True)
    exam_round: Mapped[int] = mapped_column(Integer, nullable=True)
    content: Mapped[Any] = mapped_column(JSON, nullable=False)
    audio_text: Mapped[str] = mapped_column(Text, nullable=True)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(JST))
