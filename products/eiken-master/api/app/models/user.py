import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from sqlalchemy import String, Integer, Date, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JST = timezone(timedelta(hours=9))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    grade: Mapped[str] = mapped_column(String(10), nullable=False)  # 'pre2' or '2'
    exam_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=30)
    reminder_time: Mapped[str] = mapped_column(String(5), default="20:00")
    reminder_days: Mapped[str] = mapped_column(String(20), default="[0,1,2,3,4,5,6]")
    reminder_schedule: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    study_days: Mapped[str] = mapped_column(String(20), default="[0,1,2,3,4,5,6]")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(JST))
