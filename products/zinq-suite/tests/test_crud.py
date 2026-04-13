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
