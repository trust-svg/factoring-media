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
