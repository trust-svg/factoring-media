"""データベースモデル定義"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    line_user_id: str = Column(String(64), primary_key=True)
    plan: str = Column(String(16), nullable=False, default="free")
    joined_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    plan_updated_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    readings: list["Reading"] = relationship("Reading", back_populates="user")


class Reading(Base):
    __tablename__ = "readings"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    line_user_id: str = Column(
        String(64), ForeignKey("users.line_user_id"), nullable=False
    )
    reading_type: str = Column(String(32), nullable=False)  # tarot|horoscope|numerology|daily
    result_text: str = Column(Text, nullable=False)
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    user: "User" = relationship("User", back_populates="readings")


class ThreadsPost(Base):
    __tablename__ = "threads_posts"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    theme: str = Column(String(128), nullable=False)
    content: str = Column(Text, nullable=False)
    post_slot: str = Column(String(16), nullable=False)  # morning|afternoon|evening
    posted_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    threads_post_id: str = Column(String(64), nullable=True)
