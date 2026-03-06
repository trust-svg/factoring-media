"""データベースモデル定義"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    line_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    plan_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    readings: Mapped[List["Reading"]] = relationship(back_populates="user")


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.line_user_id")
    )
    reading_type: Mapped[str] = mapped_column(String(32))
    user_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="readings")


class AppSetting(Base):
    """アプリ設定のキーバリューストア（トークン保存等）"""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ThreadsPost(Base):
    __tablename__ = "threads_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    post_slot: Mapped[str] = mapped_column(String(16))
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    threads_post_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    replies_count: Mapped[int] = mapped_column(Integer, default=0)
    reposts: Mapped[int] = mapped_column(Integer, default=0)
    quotes: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)


class ThreadsReply(Base):
    """Threadsコメントへの返信管理"""
    __tablename__ = "threads_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(String(64))  # 元投稿ID
    comment_id: Mapped[str] = mapped_column(String(64), unique=True)  # コメントID
    comment_text: Mapped[str] = mapped_column(Text)
    comment_username: Mapped[str] = mapped_column(String(128))
    draft_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI生成の下書き
    final_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 承認後のテキスト
    reply_post_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 返信投稿ID
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/approved/sent/skipped
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
