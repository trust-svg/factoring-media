# ZINQ Suite MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** マッチングアプリ攻略Bot Suiteの基盤を構築し、プロフィール写真診断AI（Free体験）とSquare決済（Standard/Premium）を動作させる。

**Architecture:** ZINQと同構造（FastAPI + LINE Bot v3 + SQLAlchemy async）を新プロジェクト `products/zinq-suite/` に構築。プロフィール写真をClaude Vision APIで診断してスコア+3改善ポイントを返す。Square Checkoutで支払いリンクを生成し、WebhookでLINE UIDと紐付けてプランを更新する。

**Tech Stack:** Python 3.12, FastAPI, LINE Bot SDK v3, SQLAlchemy 2.0 (async/aiosqlite/asyncpg), Claude Vision API (claude-sonnet-4-6), Square Python SDK, APScheduler, Docker

---

## File Structure

```
products/zinq-suite/
├── main.py                    # FastAPI app + LINE webhook handlers
├── database/
│   ├── __init__.py
│   ├── models.py              # User, DiagnosisHistory テーブル定義
│   └── crud.py                # CRUD操作
├── bots/
│   ├── __init__.py
│   └── profile_bot.py         # Claude Vision API 写真診断ロジック
├── payment/
│   ├── __init__.py
│   └── square_webhook.py      # Square Webhook + Checkout リンク生成
├── tests/
│   ├── __init__.py
│   ├── test_profile_bot.py
│   ├── test_crud.py
│   └── test_square_webhook.py
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Task 1: プロジェクトセットアップ

**Files:**
- Create: `products/zinq-suite/requirements.txt`
- Create: `products/zinq-suite/.env.example`
- Create: `products/zinq-suite/Dockerfile`
- Create: `products/zinq-suite/database/__init__.py`
- Create: `products/zinq-suite/bots/__init__.py`
- Create: `products/zinq-suite/payment/__init__.py`
- Create: `products/zinq-suite/tests/__init__.py`

- [ ] **Step 1: requirements.txt を作成**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
line-bot-sdk==3.13.0
anthropic==0.40.0
sqlalchemy==2.0.36
aiosqlite==0.20.0
asyncpg==0.30.0
python-dotenv==1.0.1
apscheduler==3.10.4
squareup==40.0.0
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

- [ ] **Step 2: .env.example を作成**

```
# LINE
LINE_CHANNEL_ACCESS_TOKEN=
LINE_CHANNEL_SECRET=

# Anthropic
ANTHROPIC_API_KEY=

# Square
SQUARE_ACCESS_TOKEN=
SQUARE_WEBHOOK_SIGNATURE_KEY=
SQUARE_STANDARD_PLAN_ID=
SQUARE_PREMIUM_PLAN_ID=
SQUARE_LOCATION_ID=

# App
DATABASE_URL=sqlite:///./zinq_suite.db
ADMIN_SECRET_KEY=
APP_BASE_URL=https://your-domain.com
```

- [ ] **Step 3: Dockerfile を作成**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: 空の __init__.py を作成**

`database/__init__.py`, `bots/__init__.py`, `payment/__init__.py`, `tests/__init__.py` を空ファイルで作成。

- [ ] **Step 5: コミット**

```bash
git add products/zinq-suite/
git commit -m "feat(zinq-suite): プロジェクト初期セットアップ"
```

---

## Task 2: DBモデル定義

**Files:**
- Create: `products/zinq-suite/database/models.py`
- Create: `products/zinq-suite/tests/test_crud.py`

- [ ] **Step 1: テストを書く（失敗確認用）**

```python
# tests/test_crud.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import Base, User, DiagnosisHistory


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_default_plan(session):
    user = User(line_user_id="U123", referral_code="ABC12345")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    assert user.plan == "free"
    assert user.free_diagnosis_used is False


@pytest.mark.asyncio
async def test_diagnosis_history(session):
    user = User(line_user_id="U456", referral_code="XYZ98765")
    session.add(user)
    await session.commit()

    history = DiagnosisHistory(
        line_user_id="U456",
        bot_type="profile",
        score=6.8,
        feedback_summary="背景に生活感\n表情が硬い\n逆光",
        is_free=True,
    )
    session.add(history)
    await session.commit()
    await session.refresh(history)
    assert history.score == 6.8
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/zinq-suite
python -m pytest tests/test_crud.py -v
```

Expected: `ModuleNotFoundError: No module named 'database.models'`

- [ ] **Step 3: models.py を作成**

```python
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
```

- [ ] **Step 4: テスト実行 → パス確認**

```bash
python -m pytest tests/test_crud.py -v
```

Expected: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add database/models.py tests/test_crud.py
git commit -m "feat(zinq-suite): DBモデル定義 (User, DiagnosisHistory)"
```

---

## Task 3: CRUD操作

**Files:**
- Create: `products/zinq-suite/database/crud.py`
- Modify: `products/zinq-suite/tests/test_crud.py`

- [ ] **Step 1: テストに CRUD テストを追加**

```python
# tests/test_crud.py に追加
from database.crud import (
    get_or_create_user,
    mark_free_diagnosis_used,
    increment_monthly_count,
    upgrade_user,
    downgrade_user,
    record_diagnosis,
)


@pytest.mark.asyncio
async def test_get_or_create_user(session):
    user = await get_or_create_user(session, "U789")
    assert user.line_user_id == "U789"
    assert user.plan == "free"
    # 2回呼んでも重複しない
    user2 = await get_or_create_user(session, "U789")
    assert user2.line_user_id == "U789"


@pytest.mark.asyncio
async def test_mark_free_diagnosis_used(session):
    await get_or_create_user(session, "U001")
    user = await mark_free_diagnosis_used(session, "U001")
    assert user.free_diagnosis_used is True


@pytest.mark.asyncio
async def test_increment_monthly_count(session):
    await get_or_create_user(session, "U002")
    count = await increment_monthly_count(session, "U002", "profile")
    assert count == 1
    count = await increment_monthly_count(session, "U002", "profile")
    assert count == 2


@pytest.mark.asyncio
async def test_upgrade_downgrade(session):
    await get_or_create_user(session, "U003")
    user = await upgrade_user(session, "U003", plan="standard")
    assert user.plan == "standard"
    user = await upgrade_user(session, "U003", plan="premium")
    assert user.plan == "premium"
    user = await downgrade_user(session, "U003")
    assert user.plan == "free"


@pytest.mark.asyncio
async def test_record_diagnosis(session):
    await get_or_create_user(session, "U004")
    history = await record_diagnosis(
        session,
        line_user_id="U004",
        bot_type="profile",
        score=7.2,
        feedback_summary="背景が暗い\n笑顔が足りない\n逆光",
        is_free=True,
    )
    assert history.score == 7.2
    assert history.bot_type == "profile"
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
python -m pytest tests/test_crud.py -v
```

Expected: `ImportError: cannot import name 'get_or_create_user' from 'database.crud'`

- [ ] **Step 3: crud.py を作成**

```python
"""ZINQ Suite — データベースCRUD操作"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, DiagnosisHistory, User

_raw_url = os.environ.get("DATABASE_URL", "sqlite:///./zinq_suite.db")


def _convert_db_url(url: str) -> str:
    if url.startswith("sqlite:///") and "aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://") and "asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://") and "asyncpg" not in url:
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _convert_db_url(_raw_url)
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

BotType = Literal["profile", "message", "date", "relation"]
Plan = Literal["free", "standard", "premium"]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(session: AsyncSession, line_user_id: str) -> User:
    result = await session.execute(select(User).where(User.line_user_id == line_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(line_user_id=line_user_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user(session: AsyncSession, line_user_id: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.line_user_id == line_user_id))
    return result.scalar_one_or_none()


async def mark_free_diagnosis_used(session: AsyncSession, line_user_id: str) -> User:
    user = await get_or_create_user(session, line_user_id)
    user.free_diagnosis_used = True
    await session.commit()
    await session.refresh(user)
    return user


async def increment_monthly_count(
    session: AsyncSession,
    line_user_id: str,
    bot_type: BotType,
) -> int:
    """月次利用カウントを+1して新しい値を返す"""
    user = await get_or_create_user(session, line_user_id)
    field = f"monthly_{bot_type}_count"
    current = getattr(user, field)
    setattr(user, field, current + 1)
    await session.commit()
    return current + 1


async def reset_monthly_counts(session: AsyncSession, line_user_id: str) -> User:
    """月次カウントをリセット（毎月1日スケジューラーが呼ぶ）"""
    user = await get_or_create_user(session, line_user_id)
    user.monthly_profile_count = 0
    user.monthly_message_count = 0
    user.monthly_date_count = 0
    user.monthly_relation_count = 0
    user.month_reset_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def upgrade_user(
    session: AsyncSession,
    line_user_id: str,
    plan: Plan,
    square_customer_id: Optional[str] = None,
    square_subscription_id: Optional[str] = None,
) -> User:
    user = await get_or_create_user(session, line_user_id)
    user.plan = plan
    user.plan_updated_at = datetime.utcnow()
    if square_customer_id:
        user.square_customer_id = square_customer_id
    if square_subscription_id:
        user.square_subscription_id = square_subscription_id
    await session.commit()
    await session.refresh(user)
    return user


async def downgrade_user(session: AsyncSession, line_user_id: str) -> Optional[User]:
    user = await get_user(session, line_user_id)
    if user:
        user.plan = "free"
        user.plan_updated_at = datetime.utcnow()
        user.square_subscription_id = None
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_square_subscription(
    session: AsyncSession, subscription_id: str
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.square_subscription_id == subscription_id)
    )
    return result.scalar_one_or_none()


async def record_diagnosis(
    session: AsyncSession,
    line_user_id: str,
    bot_type: BotType,
    feedback_summary: str,
    score: Optional[float] = None,
    is_free: bool = False,
) -> DiagnosisHistory:
    history = DiagnosisHistory(
        line_user_id=line_user_id,
        bot_type=bot_type,
        score=score,
        feedback_summary=feedback_summary,
        is_free=is_free,
    )
    session.add(history)
    await session.commit()
    await session.refresh(history)
    return history


async def get_user_diagnosis_history(
    session: AsyncSession, line_user_id: str, limit: int = 30
) -> list[DiagnosisHistory]:
    result = await session.execute(
        select(DiagnosisHistory)
        .where(DiagnosisHistory.line_user_id == line_user_id)
        .order_by(DiagnosisHistory.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: テスト実行 → パス確認**

```bash
python -m pytest tests/test_crud.py -v
```

Expected: `6 passed`

- [ ] **Step 5: コミット**

```bash
git add database/crud.py tests/test_crud.py
git commit -m "feat(zinq-suite): CRUD操作実装"
```

---

## Task 4: プロフィール写真診断Bot

**Files:**
- Create: `products/zinq-suite/bots/profile_bot.py`
- Create: `products/zinq-suite/tests/test_profile_bot.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_profile_bot.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bots.profile_bot import diagnose_photo, format_diagnosis_result


def test_format_diagnosis_result():
    result = format_diagnosis_result(
        score=6.8,
        points=["背景に生活感が出ている（-1.2点）", "表情が硬い（-0.9点）", "逆光で顔が暗い（-0.6点）"],
        potential_score=8.5,
        is_free=True,
    )
    assert "6.8" in result
    assert "8.5" in result
    assert "背景に生活感" in result
    assert "Standard" in result  # アップセルCTAが含まれる


def test_format_diagnosis_result_standard():
    result = format_diagnosis_result(
        score=7.5,
        points=["笑顔を増やすと印象UP", "背景をシンプルに", "明るさを調整"],
        potential_score=9.0,
        is_free=False,
    )
    assert "Standard" not in result  # 有料ユーザーにはCTAなし
    assert "9.0" in result


@pytest.mark.asyncio
async def test_diagnose_photo_returns_score_and_points():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "score": 6.8,
        "points": ["背景に生活感", "表情が硬い", "逆光"],
        "potential_score": 8.5
    }))]

    with patch("bots.profile_bot.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        score, points, potential = await diagnose_photo(b"fake_image_bytes")

    assert score == 6.8
    assert len(points) == 3
    assert potential == 8.5
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
python -m pytest tests/test_profile_bot.py -v
```

Expected: `ModuleNotFoundError: No module named 'bots.profile_bot'`

- [ ] **Step 3: profile_bot.py を作成**

```python
"""ZINQ Suite — プロフィール写真診断Bot

Claude Vision APIで写真を分析してスコアと改善ポイントを返す。
写真本体はこのモジュールの外に出さない（呼び出し元で即破棄）。
"""
from __future__ import annotations

import base64
import json
import logging

import anthropic

logger = logging.getLogger(__name__)

STANDARD_MONTHLY_LIMIT = 10

DIAGNOSIS_PROMPT = """あなたはマッチングアプリのプロフィール写真の専門家です。

この写真を、20〜35歳の日本人男性がマッチングアプリで使うプロフィール写真として評価してください。

以下のJSON形式のみで回答してください（他の文章は不要）:
{
  "score": <0.0〜10.0の数値、小数点1桁>,
  "points": [
    "<改善ポイント1（具体的な問題点と影響する推定点数を含む）>",
    "<改善ポイント2>",
    "<改善ポイント3>"
  ],
  "potential_score": <改善後の推定スコア、小数点1桁>
}

評価基準:
- 笑顔・表情の自然さ（重要度: 高）
- 背景の清潔感・シンプルさ（重要度: 高）
- 光の向き・顔の明るさ（重要度: 中）
- 服装・清潔感（重要度: 中）
- 構図・角度（重要度: 低）"""


async def diagnose_photo(
    image_data: bytes,
    image_media_type: str = "image/jpeg",
) -> tuple[float, list[str], float]:
    """写真を診断してスコア・改善ポイント3つ・改善後推定スコアを返す。

    Returns:
        (score, points, potential_score)
        写真本体はここで使用後、呼び出し元で破棄すること。
    """
    client = anthropic.AsyncAnthropic()
    image_b64 = base64.standard_b64encode(image_data).decode("utf-8")

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_media_type,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": DIAGNOSIS_PROMPT},
            ],
        }],
    )

    result = json.loads(response.content[0].text)
    return float(result["score"]), list(result["points"]), float(result["potential_score"])


def format_diagnosis_result(
    score: float,
    points: list[str],
    potential_score: float,
    is_free: bool = True,
) -> str:
    """診断結果をLINEメッセージ用にフォーマットする"""
    lines = [
        "📊 プロフィール診断結果\n",
        f"スコア: {score:.1f} / 10\n",
        "改善ポイント:",
    ]
    for i, point in enumerate(points, 1):
        lines.append(f"{'①②③'[i-1]} {point}")

    lines.append(f"\n改善すれば {potential_score:.1f}点 まで上げられます。")

    if is_free:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            "✨ 各改善ポイントの具体的な対策、",
            "自己紹介文の改善もしたい方は",
            "→ Standardプランで続ける",
            "（¥980/月、全Bot月10回利用可）",
        ])

    return "\n".join(lines)


def check_usage_limit(plan: str, monthly_count: int) -> str | None:
    """利用制限チェック。制限超過の場合はアップセルメッセージを返す。Noneなら利用可能。"""
    if plan == "free":
        return (
            "無料診断は1回までです。\n\n"
            "続けて使うには→ Standardプラン（¥980/月）\n"
            "全Bot使い放題→ Premiumプラン（¥2,480/月）"
        )
    if plan == "standard" and monthly_count >= STANDARD_MONTHLY_LIMIT:
        return (
            f"今月のプロフィール診断（{STANDARD_MONTHLY_LIMIT}回）を使い切りました。\n\n"
            "使い放題にするには→ Premiumプラン（¥2,480/月）"
        )
    return None  # 利用可能
```

- [ ] **Step 4: テスト実行 → パス確認**

```bash
python -m pytest tests/test_profile_bot.py -v
```

Expected: `3 passed`

- [ ] **Step 5: コミット**

```bash
git add bots/profile_bot.py tests/test_profile_bot.py
git commit -m "feat(zinq-suite): プロフィール写真診断Bot実装"
```

---

## Task 5: Square 決済連携

**Files:**
- Create: `products/zinq-suite/payment/square_webhook.py`
- Create: `products/zinq-suite/tests/test_square_webhook.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_square_webhook.py
import pytest
from unittest.mock import AsyncMock, patch

from payment.square_webhook import (
    generate_checkout_url,
    parse_subscription_event,
    SquareEvent,
)


def test_parse_subscription_created():
    payload = {
        "type": "subscription.created",
        "data": {
            "object": {
                "subscription": {
                    "id": "sub_abc123",
                    "customer_id": "cust_xyz",
                    "plan_variation_id": "plan_standard_id",
                    "status": "ACTIVE",
                    "metadata": {"line_user_id": "Uabc123"},
                }
            }
        }
    }
    event = parse_subscription_event(payload, standard_plan_id="plan_standard_id", premium_plan_id="plan_premium_id")
    assert event.event_type == "created"
    assert event.line_user_id == "Uabc123"
    assert event.plan == "standard"
    assert event.subscription_id == "sub_abc123"


def test_parse_subscription_canceled():
    payload = {
        "type": "subscription.updated",
        "data": {
            "object": {
                "subscription": {
                    "id": "sub_abc123",
                    "customer_id": "cust_xyz",
                    "plan_variation_id": "plan_standard_id",
                    "status": "CANCELED",
                    "metadata": {"line_user_id": "Uabc123"},
                }
            }
        }
    }
    event = parse_subscription_event(payload, standard_plan_id="plan_standard_id", premium_plan_id="plan_premium_id")
    assert event.event_type == "canceled"


def test_parse_unknown_event_returns_none():
    payload = {"type": "payment.completed", "data": {}}
    event = parse_subscription_event(payload, standard_plan_id="s", premium_plan_id="p")
    assert event is None
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
python -m pytest tests/test_square_webhook.py -v
```

Expected: `ModuleNotFoundError: No module named 'payment.square_webhook'`

- [ ] **Step 3: square_webhook.py を作成**

```python
"""ZINQ Suite — Square 決済連携

フロー:
1. ユーザーがLINE Botで「プランを見る」タップ
2. Botがline_user_idをmetadataに埋め込んだSquare Checkout URLを生成
3. ユーザーがSquareで決済
4. Square Webhookが来る → subscription.created → line_user_idでプランを更新
5. Botがユーザーに「プレミアム登録完了！」をpush送信
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from database.crud import (
    AsyncSessionLocal,
    downgrade_user,
    get_user_by_square_subscription,
    upgrade_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payment", tags=["payment"])

Plan = Literal["standard", "premium"]


@dataclass
class SquareEvent:
    event_type: Literal["created", "canceled"]
    line_user_id: str
    plan: Plan
    subscription_id: str
    customer_id: str


def parse_subscription_event(
    payload: dict,
    standard_plan_id: str,
    premium_plan_id: str,
) -> Optional[SquareEvent]:
    """Square WebhookペイロードをSquareEventに変換する。無関係なイベントはNoneを返す。"""
    event_type_raw = payload.get("type", "")
    if event_type_raw not in ("subscription.created", "subscription.updated"):
        return None

    try:
        sub = payload["data"]["object"]["subscription"]
    except (KeyError, TypeError):
        return None

    status = sub.get("status", "")
    line_user_id = (sub.get("metadata") or {}).get("line_user_id", "")
    if not line_user_id:
        return None

    plan_variation_id = sub.get("plan_variation_id", "")
    if plan_variation_id == standard_plan_id:
        plan: Plan = "standard"
    elif plan_variation_id == premium_plan_id:
        plan = "premium"
    else:
        return None

    if status == "ACTIVE" and event_type_raw == "subscription.created":
        event_type = "created"
    elif status == "CANCELED":
        event_type = "canceled"
    else:
        return None

    return SquareEvent(
        event_type=event_type,
        line_user_id=line_user_id,
        plan=plan,
        subscription_id=sub.get("id", ""),
        customer_id=sub.get("customer_id", ""),
    )


def generate_checkout_url(line_user_id: str, plan: Plan) -> str:
    """Square Checkout URL を生成する（line_user_idをreferenceとして埋め込む）"""
    base_url = os.environ.get("APP_BASE_URL", "")
    # Square Checkout URL生成はAPIで行うが、ここではLINEで表示するリンクページURLを返す
    # 実際のCheckout URLはSquare APIで動的生成する（/payment/checkout エンドポイントで処理）
    return f"{base_url}/payment/checkout?plan={plan}&uid={line_user_id}"


# ===================== Webhook エンドポイント =====================

@router.post("/webhook/square")
async def square_webhook(
    request: Request,
    x_square_hmacsha256_signature: str = Header(alias="X-Square-Hmacsha256-Signature", default=""),
) -> dict:
    body = await request.body()

    # 署名検証
    sig_key = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "")
    if sig_key:
        expected = hmac.new(
            sig_key.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_square_hmacsha256_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    standard_plan_id = os.environ.get("SQUARE_STANDARD_PLAN_ID", "")
    premium_plan_id = os.environ.get("SQUARE_PREMIUM_PLAN_ID", "")

    event = parse_subscription_event(payload, standard_plan_id, premium_plan_id)
    if event is None:
        return {"status": "ignored"}

    async with AsyncSessionLocal() as session:
        if event.event_type == "created":
            await upgrade_user(
                session,
                event.line_user_id,
                plan=event.plan,
                square_customer_id=event.customer_id,
                square_subscription_id=event.subscription_id,
            )
            logger.info(f"プランアップグレード: {event.line_user_id} → {event.plan}")
        elif event.event_type == "canceled":
            await downgrade_user(session, event.line_user_id)
            logger.info(f"プランキャンセル: {event.line_user_id}")

    return {"status": "ok"}


# ===================== Checkout リダイレクト =====================

@router.get("/checkout")
async def checkout_redirect(plan: str, uid: str) -> dict:
    """Square Checkout URLを動的生成してリダイレクト（実装はSquare API呼び出し）"""
    # TODO: Square APIでCheckoutセッションを作成してリダイレクト
    # 現段階では管理者が手動でCheckout URLを発行する運用でも可
    return {"plan": plan, "uid": uid, "message": "Square Checkout連携は別途設定が必要です"}
```

- [ ] **Step 4: テスト実行 → パス確認**

```bash
python -m pytest tests/test_square_webhook.py -v
```

Expected: `3 passed`

- [ ] **Step 5: コミット**

```bash
git add payment/square_webhook.py tests/test_square_webhook.py
git commit -m "feat(zinq-suite): Square決済Webhook実装"
```

---

## Task 6: LINE Webhook メインアプリ

**Files:**
- Create: `products/zinq-suite/main.py`

- [ ] **Step 1: main.py を作成**

```python
"""ZINQ Suite — LINE Bot メインエントリーポイント

マッチングアプリ攻略Bot Suite。
MVP: プロフィール写真診断のみ。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
line_handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

_executor = ThreadPoolExecutor(max_workers=4)
_main_loop: asyncio.AbstractEventLoop | None = None


def _run_async(coro):
    loop = _main_loop
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=120)
    return asyncio.run(coro)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_event_loop()
    from database.crud import init_db
    await init_db()
    logger.info("DB初期化完了")
    yield


app = FastAPI(title="ZINQ Suite", lifespan=lifespan)

from payment.square_webhook import router as payment_router  # noqa: E402
app.include_router(payment_router)


# ===================== 定数 =====================

WELCOME_MESSAGE = (
    "👋 ZINQ Suite へようこそ！\n\n"
    "マッチングアプリ攻略をAIがサポートします。\n\n"
    "まずは無料で「プロフィール写真診断」を試してみてください📸\n"
    "写真を1枚送ってください👇\n\n"
    "⚠️ 写真は診断後すぐに削除します。\n"
    "スコアデータのみ記録します（月次レポート用）。"
)

PLAN_INFO = (
    "💳 ZINQ Suite — プラン\n\n"
    "【Free】¥0\n"
    "・プロフィール写真診断 1回\n\n"
    "【Standard】¥980/月\n"
    "・全Bot月10回ずつ利用可能\n\n"
    "【Premium】¥2,480/月\n"
    "・全Bot使い放題\n"
    "・月次総合診断レポート付き\n\n"
    "▶ プランを変更する: {checkout_url}"
)


# ===================== Webhook =====================

@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(alias="X-Line-Signature"),
) -> dict:
    global _main_loop
    if _main_loop is None:
        _main_loop = asyncio.get_event_loop()

    body = await request.body()
    secret = os.environ["LINE_CHANNEL_SECRET"].encode("utf-8")
    sig = base64.b64encode(hmac.new(secret, body, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(sig, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    body_str = body.decode("utf-8")
    await asyncio.get_event_loop().run_in_executor(
        _executor, line_handler.handle, body_str, x_line_signature
    )
    return {"status": "ok"}


# ===================== イベントハンドラ =====================

@line_handler.add(FollowEvent)
def handle_follow(event: FollowEvent) -> None:
    user_id = event.source.user_id

    async def _register():
        from database.crud import AsyncSessionLocal, get_or_create_user
        async with AsyncSessionLocal() as session:
            await get_or_create_user(session, user_id)

    try:
        _run_async(_register())
    except Exception as e:
        logger.warning(f"ユーザー登録失敗 {user_id}: {e}")

    _reply(event.reply_token, WELCOME_MESSAGE)


@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent) -> None:
    text = event.message.text.strip()
    user_id = event.source.user_id

    if any(kw in text for kw in ("プラン", "料金", "値段", "プレミアム", "スタンダード")):
        from payment.square_webhook import generate_checkout_url
        url = generate_checkout_url(user_id, "standard")
        _reply(event.reply_token, PLAN_INFO.format(checkout_url=url))
        return

    _reply(event.reply_token, "写真を送ると無料でプロフィール診断します📸\nマッチングアプリで使っている写真を1枚送ってください。")


@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event: MessageEvent) -> None:
    user_id = event.source.user_id
    message_id = event.message.id

    _reply(event.reply_token, "診断中です... 少々お待ちください📊")

    try:
        _run_async(_do_photo_diagnosis(user_id, message_id))
    except Exception as e:
        logger.error(f"写真診断エラー {user_id}: {e}")
        _push_message(user_id, "申し訳ありません、診断に失敗しました🙏\nもう一度送ってください。")


# ===================== 診断処理 =====================

async def _do_photo_diagnosis(user_id: str, message_id: str) -> None:
    from database.crud import AsyncSessionLocal, get_or_create_user, mark_free_diagnosis_used, increment_monthly_count, record_diagnosis
    from bots.profile_bot import diagnose_photo, format_diagnosis_result, check_usage_limit

    # LINE APIで画像取得
    with ApiClient(line_config) as api_client:
        blob_api = MessagingApiBlob(api_client)
        image_data: bytes = blob_api.get_message_content(message_id)

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_id)

        # 利用制限チェック
        limit_msg = check_usage_limit(user.plan, user.monthly_profile_count)
        if user.plan == "free" and user.free_diagnosis_used:
            _push_message(user_id, limit_msg)
            return
        if limit_msg and user.plan != "free":
            _push_message(user_id, limit_msg)
            return

        # 診断実行（画像はここで使って破棄）
        score, points, potential_score = await diagnose_photo(image_data)
        del image_data  # 写真を即破棄

        is_free = user.plan == "free"

        # フリーカウント更新
        if is_free:
            await mark_free_diagnosis_used(session, user_id)
        else:
            await increment_monthly_count(session, user_id, "profile")

        # スコアとテキストのみDB保存
        await record_diagnosis(
            session,
            line_user_id=user_id,
            bot_type="profile",
            score=score,
            feedback_summary="\n".join(points),
            is_free=is_free,
        )

    result_text = format_diagnosis_result(score, points, potential_score, is_free=is_free)
    _push_message(user_id, result_text)


# ===================== ヘルパー =====================

def _reply(reply_token: str, text: str) -> None:
    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )


def _push_message(user_id: str, text: str) -> None:
    if len(text) > 4900:
        text = text[:4900] + "\n\n（文字数制限のため省略）"
    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ZINQ Suite"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
```

- [ ] **Step 2: 全テストを実行**

```bash
python -m pytest tests/ -v
```

Expected: `全テストパス`

- [ ] **Step 3: コミット**

```bash
git add main.py
git commit -m "feat(zinq-suite): LINE Webhook メインアプリ実装 (MVP完成)"
```

---

## Task 7: 動作確認 & デプロイ準備

**Files:**
- Modify: `products/zinq-suite/.env.example` (確認)

- [ ] **Step 1: ローカル起動確認**

```bash
cd products/zinq-suite
cp .env.example .env
# .env に実際の値を設定

pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Expected: `INFO: Application startup complete.`
`GET http://localhost:8001/health` → `{"status":"ok","service":"ZINQ Suite"}`

- [ ] **Step 2: LINE Webhook URL を設定**

LINE Developers Console → ZINQ Suite チャネル → Webhook URL:
`https://your-domain.com/webhook`

- [ ] **Step 3: Square Webhook URL を設定**

Square Developer Dashboard → Webhooks → `https://your-domain.com/payment/webhook/square`
購読イベント: `subscription.created`, `subscription.updated`

- [ ] **Step 4: 全テスト最終確認**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: 全テストパス

- [ ] **Step 5: 最終コミット**

```bash
git add .
git commit -m "feat(zinq-suite): MVP完成 — プロフィール写真診断Bot + Square決済"
```

---

## Self-Review チェック

**Spec coverage:**
- ✅ Free: プロフィール診断1回（UID管理で重複防止）
- ✅ Standard: 月10回制限（increment_monthly_count）
- ✅ Premium: 制限なし（check_usage_limitでplan="premium"は通過）
- ✅ 写真即削除・スコアデータのみ保存
- ✅ Square Webhook連携（プラン変更）
- ✅ アップセルCTA（free_diagnosis_used後のメッセージ）
- ⚠️ リマインド（オプトイン制）: Plan 3で実装
- ⚠️ バイラル紹介: Plan 3で実装
- ⚠️ リッチメニュー: Plan 2で実装
- ⚠️ メッセージAI・デートプランAI・関係構築AI: Plan 2で実装
- ⚠️ 月次レポート: Plan 3で実装

**次のステップ:** Plan 2（Bot Suite追加 + リッチメニュー）へ進む。
