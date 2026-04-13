"""ZINQ Suite — データベースモデル定義"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _generate_referral_code() -> str:
    return secrets.token_hex(4).upper()


class User(Base):
    __tablename__ = "users"

    line_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")  # free / standard / premium
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    plan_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Square 連携
    square_customer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    square_subscription_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Free診断: 1回限り（LINE UID単位で管理）
    free_diagnosis_used: Mapped[bool] = mapped_column(Boolean, default=False)

    # Standard月次利用カウント（毎月1日リセット）
    monthly_profile_count: Mapped[int] = mapped_column(Integer, default=0)
    monthly_message_count: Mapped[int] = mapped_column(Integer, default=0)
    monthly_date_count: Mapped[int] = mapped_column(Integer, default=0)
    monthly_relation_count: Mapped[int] = mapped_column(Integer, default=0)
    month_reset_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # リマインド設定（オプトイン制）
    reminder_opted_in: Mapped[bool] = mapped_column(Boolean, default=False)

    # 紹介システム
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, default=_generate_referral_code)
    referred_by: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    referral_bonus_active: Mapped[bool] = mapped_column(Boolean, default=False)

    diagnoses: Mapped[List["DiagnosisHistory"]] = relationship(back_populates="user")


class DiagnosisHistory(Base):
    """診断履歴。写真本体は保存しない。スコアとテキストのみ。"""
    __tablename__ = "diagnosis_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.line_user_id"))
    bot_type: Mapped[str] = mapped_column(String(32))  # profile / message / date / relation

    # 写真診断の場合: スコアと改善ポイントのテキストのみ保存（写真は即削除）
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback_summary: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="diagnoses")
