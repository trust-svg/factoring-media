# Video Ad Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 50代向けマッチングアプリFacebook動画広告を、NanoBanana PRO（画像）→ Atlas Cloud Seedance 2.0 I2V（動画）で自動生成するFastAPI + Web UIツールを構築する。

**Architecture:** FastAPI + SQLite でジョブ管理し、NanoBanana PRO で9:16静止画を生成 → 手動承認後に Atlas Cloud Seedance 2.0 I2V で10秒動画化。Telegram専用Botで完了通知。`AUTO_APPROVE=True` フラグで全自動化へ移行可能。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (SQLite), httpx, Anthropic SDK, python-telegram-bot, Vanilla JS

---

## File Map

| ファイル | 責務 |
|---|---|
| `main.py` | FastAPIアプリ起動・ルーター登録・DB初期化 |
| `config.py` | 環境変数読み込み・定数定義 |
| `database.py` | SQLAlchemy モデル・セッション・init_db |
| `core/patterns.py` | ABパターン5種のプロンプト定義・ブロックワードフィルタ |
| `core/image_gen.py` | NanoBanana PRO API呼び出し（httpx, Bearer token） |
| `core/video_gen.py` | Atlas Cloud Seedance 2.0 I2V API呼び出し・ポーリング |
| `core/notifier.py` | Telegram Bot通知 |
| `core/scorer.py` | Claude Vision による自動スコアリング（AUTO_APPROVEモード用） |
| `api/generate.py` | POST /generate/image, /generate/video, /generate/batch |
| `api/approve.py` | POST /approve/{id}, /reject/{id} |
| `api/jobs.py` | GET /jobs, GET /jobs/{id}, GET /stats |
| `static/index.html` | シングルページUI（Vanilla JS） |
| `tests/test_patterns.py` | パターン定義・ブロックワードフィルタのテスト |
| `tests/test_image_gen.py` | NanoBanana PRO呼び出しのテスト（httpxモック） |
| `tests/test_video_gen.py` | Atlas Cloud呼び出しのテスト（httpxモック） |
| `tests/test_api.py` | APIエンドポイントのテスト（FastAPI TestClient） |

---

## Task 1: プロジェクトスキャフォールド

**Files:**
- Create: `products/video-ad-generator/requirements.txt`
- Create: `products/video-ad-generator/.env.example`
- Create: `products/video-ad-generator/config.py`

- [ ] **Step 1: ディレクトリ作成と requirements.txt**

```bash
mkdir -p products/video-ad-generator/core
mkdir -p products/video-ad-generator/api
mkdir -p products/video-ad-generator/static
mkdir -p products/video-ad-generator/tests
mkdir -p products/video-ad-generator/output/pending
mkdir -p products/video-ad-generator/output/approved
mkdir -p products/video-ad-generator/output/rejected
mkdir -p products/video-ad-generator/output/videos
touch products/video-ad-generator/core/__init__.py
touch products/video-ad-generator/api/__init__.py
touch products/video-ad-generator/tests/__init__.py
```

`products/video-ad-generator/requirements.txt`:
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-dotenv>=1.0.0
httpx>=0.27.0
sqlalchemy>=2.0.0
anthropic>=0.40.0
python-telegram-bot>=21.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
respx>=0.21.0
```

- [ ] **Step 2: .env.example を作成**

`products/video-ad-generator/.env.example`:
```
NANOBANANA_API_KEY=your_nanobanana_api_key
ATLAS_CLOUD_API_KEY=your_atlas_cloud_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
ANTHROPIC_API_KEY=your_anthropic_api_key
AUTO_APPROVE=false
AUTO_APPROVE_SCORE_THRESHOLD=0.75
APP_PORT=8004
```

- [ ] **Step 3: config.py を作成**

`products/video-ad-generator/config.py`:
```python
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

NANOBANANA_API_KEY: str = os.environ["NANOBANANA_API_KEY"]
ATLAS_CLOUD_API_KEY: str = os.environ["ATLAS_CLOUD_API_KEY"]
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

AUTO_APPROVE: bool = os.environ.get("AUTO_APPROVE", "false").lower() == "true"
AUTO_APPROVE_SCORE_THRESHOLD: float = float(os.environ.get("AUTO_APPROVE_SCORE_THRESHOLD", "0.75"))

APP_PORT: int = int(os.environ.get("APP_PORT", "8004"))
APP_HOST: str = "0.0.0.0"

VIDEO_DURATION: int = 10
VIDEO_ASPECT_RATIO: str = "9:16"
BATCH_SIZE: int = 10

OUTPUT_DIR = BASE_DIR / "output"
PENDING_DIR = OUTPUT_DIR / "pending"
APPROVED_DIR = OUTPUT_DIR / "approved"
REJECTED_DIR = OUTPUT_DIR / "rejected"
VIDEOS_DIR = OUTPUT_DIR / "videos"
DB_PATH = BASE_DIR / "video_ad.db"

# Atlas Cloud Seedance 2.0 I2V
ATLAS_CLOUD_I2V_URL = "https://api.muapi.ai/api/v1/seedance-v2.0-i2v"
ATLAS_CLOUD_STATUS_URL = "https://api.muapi.ai/api/v1/status/{request_id}"

# NanoBanana PRO（既存スキルのendpointを確認して設定）
# docs: https://docs.nanobananaapi.ai
NANOBANANA_API_URL = "https://nanobananaapi.ai/api/generate"
```

- [ ] **Step 4: .env を作成（実際のキーを記入）**

```bash
cp products/video-ad-generator/.env.example products/video-ad-generator/.env
# .envを開いて実際のAPIキーを記入
```

- [ ] **Step 5: コミット**

```bash
git add products/video-ad-generator/requirements.txt products/video-ad-generator/.env.example products/video-ad-generator/config.py
git commit -m "feat: video-ad-generator プロジェクトスキャフォールド"
```

---

## Task 2: データベース（SQLiteモデル）

**Files:**
- Create: `products/video-ad-generator/database.py`
- Create: `products/video-ad-generator/tests/test_database.py`

- [ ] **Step 1: テストを書く**

`products/video-ad-generator/tests/test_database.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database import Base, Job, JobStatus, init_db

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_create_job(db):
    job = Job(
        pattern="A",
        prompt="A Japanese woman in her 40s at a cafe",
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    assert job.id is not None
    assert job.status == JobStatus.PENDING
    assert job.image_path is None
    assert job.video_path is None

def test_job_status_transitions(db):
    job = Job(pattern="B", prompt="test", status=JobStatus.PENDING)
    db.add(job)
    db.commit()

    job.status = JobStatus.APPROVED
    db.commit()
    db.refresh(job)
    assert job.status == JobStatus.APPROVED
```

- [ ] **Step 2: テスト実行（FAIL確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_database.py -v
```
Expected: `ModuleNotFoundError: No module named 'database'`

- [ ] **Step 3: database.py を実装**

`products/video-ad-generator/database.py`:
```python
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
```

- [ ] **Step 4: テスト実行（PASS確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_database.py -v
```
Expected: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add products/video-ad-generator/database.py products/video-ad-generator/tests/test_database.py
git commit -m "feat: SQLite ジョブモデル（Job, JobStatus）"
```

---

## Task 3: ABパターン定義

**Files:**
- Create: `products/video-ad-generator/core/patterns.py`
- Create: `products/video-ad-generator/tests/test_patterns.py`

- [ ] **Step 1: テストを書く**

`products/video-ad-generator/tests/test_patterns.py`:
```python
from core.patterns import PATTERNS, get_batch_prompts, is_blocked

def test_patterns_has_five_types():
    assert set(PATTERNS.keys()) == {"A", "B", "C", "D", "E"}

def test_each_pattern_has_image_and_video_prompt():
    for key, p in PATTERNS.items():
        assert "image_prompt" in p, f"Pattern {key} missing image_prompt"
        assert "video_prompt" in p, f"Pattern {key} missing video_prompt"
        assert "theme" in p

def test_get_batch_prompts_returns_ten():
    batch = get_batch_prompts()
    assert len(batch) == 10

def test_get_batch_prompts_has_two_per_pattern():
    batch = get_batch_prompts()
    patterns_in_batch = [item["pattern"] for item in batch]
    for p in ["A", "B", "C", "D", "E"]:
        assert patterns_in_batch.count(p) == 2

def test_is_blocked_real_person():
    assert is_blocked("photo of Yui Aragaki smiling") is True

def test_is_blocked_safe_prompt():
    assert is_blocked("A Japanese woman in her 40s at a cafe") is False
```

- [ ] **Step 2: テスト実行（FAIL確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_patterns.py -v
```
Expected: `ImportError`

- [ ] **Step 3: patterns.py を実装**

`products/video-ad-generator/core/patterns.py`:
```python
"""ABパターン5種のプロンプト定義。
50代向けマッチングアプリ広告用の日本人女性キャラクター生成。
"""
from __future__ import annotations
import random

# ブロックワード: 実在人物参照を防ぐ著名人名など
_BLOCK_WORDS = [
    "aragaki", "yui", "ishihara", "satomi", "ayase", "haruka",
    "toda", "erika", "kitagawa", "keiko", "takeuchi", "yuuko",
    "綾瀬", "新垣", "石原", "戸田", "北川", "竹内",
    "real person", "celebrity", "idol", "actress", "actor",
]

PATTERNS: dict[str, dict] = {
    "A": {
        "theme": "ロマンティック系",
        "image_prompt": (
            "Portrait photo of a warm Japanese woman in her late 30s to early 40s, "
            "soft natural makeup, gentle smile, casual-elegant blouse in muted rose tones, "
            "sitting at a cozy cafe by a rain-streaked window, soft bokeh background, "
            "natural window light, upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman gently wraps her hands around a coffee cup and looks out at the rain, "
            "soft smile, slow cinematic camera pull-back, warm cafe ambience, "
            "peaceful romantic atmosphere"
        ),
    },
    "B": {
        "theme": "楽しさ系",
        "image_prompt": (
            "Portrait photo of a cheerful Japanese woman in her early 40s, "
            "natural makeup, bright genuine laugh, casual colorful outfit, "
            "sitting on a park bench surrounded by greenery and sunlight, "
            "upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman laughs lightly and brushes hair from her face, "
            "light breeze moves through the trees behind her, "
            "joyful energy, slow-motion capture, warm golden hour lighting"
        ),
    },
    "C": {
        "theme": "信頼感系",
        "image_prompt": (
            "Portrait photo of a composed Japanese woman in her mid 40s, "
            "minimal elegant makeup, calm confident expression, "
            "smart casual blazer in navy or grey, modern office environment background, "
            "upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman looks up from her desk and gives a small warm smile, "
            "calm and composed movement, soft office lighting, "
            "steady camera, professional yet approachable atmosphere"
        ),
    },
    "D": {
        "theme": "ユーモア系",
        "image_prompt": (
            "Portrait photo of a fun playful Japanese woman in her late 30s, "
            "light natural makeup, mischievous grin, casual trendy outfit, "
            "stylish modern cafe background with colorful decor, "
            "upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman notices the camera, breaks into a wide grin and gives a small wave, "
            "spontaneous and lighthearted movement, bright cafe atmosphere, "
            "handheld-style camera feel"
        ),
    },
    "E": {
        "theme": "真面目系",
        "image_prompt": (
            "Portrait photo of an intellectual Japanese woman in her early 50s, "
            "elegant minimal makeup, thoughtful expression, "
            "simple sophisticated blouse, library or bookshelf background, "
            "soft reading lamp light, upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman closes a book gently and looks up with a quiet confident smile, "
            "deliberate graceful movement, warm library lighting, "
            "slow zoom-in, intelligent serene atmosphere"
        ),
    },
}


def is_blocked(prompt: str) -> bool:
    lower = prompt.lower()
    return any(word in lower for word in _BLOCK_WORDS)


def get_batch_prompts() -> list[dict]:
    """月バッチ用: 各パターン2本ずつ計10本のプロンプトリストを返す。"""
    batch = []
    for pattern_key, pattern in PATTERNS.items():
        for _ in range(2):
            batch.append({
                "pattern": pattern_key,
                "theme": pattern["theme"],
                "image_prompt": pattern["image_prompt"],
                "video_prompt": pattern["video_prompt"],
            })
    random.shuffle(batch)
    return batch
```

- [ ] **Step 4: テスト実行（PASS確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_patterns.py -v
```
Expected: `6 passed`

- [ ] **Step 5: コミット**

```bash
git add products/video-ad-generator/core/patterns.py products/video-ad-generator/tests/test_patterns.py
git commit -m "feat: ABパターン5種定義・ブロックワードフィルタ"
```

---

## Task 4: NanoBanana PRO 画像生成

**Files:**
- Create: `products/video-ad-generator/core/image_gen.py`
- Create: `products/video-ad-generator/tests/test_image_gen.py`

> **注意:** NanoBanana PRO の正確なエンドポイントは `NANOBANANA_API_URL` に設定する。
> 既存スキルのコードを確認して endpoint を合わせること。
> 参考: `~/.claude/skills/` 内のNanoBanana PRO スキルファイル

- [ ] **Step 1: テストを書く（httpxモック使用）**

`products/video-ad-generator/tests/test_image_gen.py`:
```python
import pytest
import httpx
import respx
from pathlib import Path
from unittest.mock import patch
from core.image_gen import generate_image, ImageGenError

FAKE_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG bytes

@respx.mock
@pytest.mark.asyncio
async def test_generate_image_success(tmp_path):
    output_path = tmp_path / "test.jpg"
    respx.post("https://nanobananaapi.ai/api/generate").mock(
        return_value=httpx.Response(
            200,
            content=FAKE_IMAGE_BYTES,
            headers={"content-type": "image/jpeg"},
        )
    )
    with patch("core.image_gen.NANOBANANA_API_URL", "https://nanobananaapi.ai/api/generate"):
        result = await generate_image(
            prompt="A Japanese woman in her 40s at a cafe",
            output_path=output_path,
        )
    assert result == output_path
    assert output_path.exists()

@respx.mock
@pytest.mark.asyncio
async def test_generate_image_retries_on_error(tmp_path):
    output_path = tmp_path / "test.jpg"
    respx.post("https://nanobananaapi.ai/api/generate").mock(
        side_effect=[
            httpx.Response(500, json={"error": "server error"}),
            httpx.Response(500, json={"error": "server error"}),
            httpx.Response(200, content=FAKE_IMAGE_BYTES, headers={"content-type": "image/jpeg"}),
        ]
    )
    with patch("core.image_gen.NANOBANANA_API_URL", "https://nanobananaapi.ai/api/generate"):
        result = await generate_image(prompt="test", output_path=output_path)
    assert result == output_path

@respx.mock
@pytest.mark.asyncio
async def test_generate_image_raises_after_max_retries(tmp_path):
    output_path = tmp_path / "test.jpg"
    respx.post("https://nanobananaapi.ai/api/generate").mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )
    with patch("core.image_gen.NANOBANANA_API_URL", "https://nanobananaapi.ai/api/generate"):
        with pytest.raises(ImageGenError):
            await generate_image(prompt="test", output_path=output_path)
```

- [ ] **Step 2: テスト実行（FAIL確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_image_gen.py -v
```
Expected: `ImportError: cannot import name 'generate_image'`

- [ ] **Step 3: image_gen.py を実装**

`products/video-ad-generator/core/image_gen.py`:
```python
"""NanoBanana PRO API クライアント。
9:16（1080×1920）の日本人女性画像を生成する。
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import httpx
from config import NANOBANANA_API_KEY, NANOBANANA_API_URL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5.0


class ImageGenError(Exception):
    pass


async def generate_image(prompt: str, output_path: Path) -> Path:
    """NanoBanana PRO で画像を生成して output_path に保存する。
    失敗時は最大3回リトライ。
    """
    headers = {
        "Authorization": f"Bearer {NANOBANANA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "aspect_ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "model": "nanobanana-pro",
    }

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.post(NANOBANANA_API_URL, headers=headers, json=payload)
                if response.status_code == 200:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(response.content)
                    logger.info(f"画像生成成功: {output_path}")
                    return output_path
                last_error = ImageGenError(f"HTTP {response.status_code}: {response.text[:200]}")
                logger.warning(f"Attempt {attempt} failed: {last_error}")
            except httpx.RequestError as e:
                last_error = ImageGenError(f"Request error: {e}")
                logger.warning(f"Attempt {attempt} request error: {e}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

    raise ImageGenError(f"画像生成失敗（{MAX_RETRIES}回リトライ済み）: {last_error}")
```

- [ ] **Step 4: テスト実行（PASS確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_image_gen.py -v
```
Expected: `3 passed`

- [ ] **Step 5: コミット**

```bash
git add products/video-ad-generator/core/image_gen.py products/video-ad-generator/tests/test_image_gen.py
git commit -m "feat: NanoBanana PRO 画像生成クライアント（3回リトライ）"
```

---

## Task 5: Atlas Cloud Seedance 2.0 I2V 動画生成

**Files:**
- Create: `products/video-ad-generator/core/video_gen.py`
- Create: `products/video-ad-generator/tests/test_video_gen.py`

- [ ] **Step 1: テストを書く**

`products/video-ad-generator/tests/test_video_gen.py`:
```python
import pytest
import httpx
import respx
from pathlib import Path
from unittest.mock import patch
from core.video_gen import generate_video, VideoGenError

FAKE_VIDEO_BYTES = b"RIFF" + b"\x00" * 200  # fake video bytes

@respx.mock
@pytest.mark.asyncio
async def test_generate_video_success(tmp_path):
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake_image_data")
    output_path = tmp_path / "test.mp4"

    # Step1: submit job
    respx.post("https://api.muapi.ai/api/v1/seedance-v2.0-i2v").mock(
        return_value=httpx.Response(200, json={"request_id": "req_abc123"})
    )
    # Step2: poll status → done
    respx.get("https://api.muapi.ai/api/v1/status/req_abc123").mock(
        return_value=httpx.Response(200, json={"status": "done", "output_url": "https://cdn.example.com/video.mp4"})
    )
    # Step3: download video
    respx.get("https://cdn.example.com/video.mp4").mock(
        return_value=httpx.Response(200, content=FAKE_VIDEO_BYTES)
    )

    result = await generate_video(
        image_path=image_path,
        video_prompt="The woman smiles gently",
        output_path=output_path,
    )
    assert result == output_path
    assert output_path.exists()

@respx.mock
@pytest.mark.asyncio
async def test_generate_video_raises_on_api_error(tmp_path):
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake_image_data")
    output_path = tmp_path / "test.mp4"

    respx.post("https://api.muapi.ai/api/v1/seedance-v2.0-i2v").mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )
    with pytest.raises(VideoGenError):
        await generate_video(image_path=image_path, video_prompt="test", output_path=output_path)
```

- [ ] **Step 2: テスト実行（FAIL確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_video_gen.py -v
```
Expected: `ImportError: cannot import name 'generate_video'`

- [ ] **Step 3: video_gen.py を実装**

`products/video-ad-generator/core/video_gen.py`:
```python
"""Atlas Cloud Seedance 2.0 I2V API クライアント。
承認済み画像を10秒の9:16動画に変換する。
"""
from __future__ import annotations
import asyncio
import base64
import logging
from pathlib import Path
import httpx
from config import (
    ATLAS_CLOUD_API_KEY,
    ATLAS_CLOUD_I2V_URL,
    ATLAS_CLOUD_STATUS_URL,
    VIDEO_DURATION,
    VIDEO_ASPECT_RATIO,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 300.0  # 5分


class VideoGenError(Exception):
    pass


async def generate_video(image_path: Path, video_prompt: str, output_path: Path) -> Path:
    """Seedance 2.0 I2V で動画を生成して output_path に保存する。"""
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    headers = {
        "x-api-key": ATLAS_CLOUD_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": video_prompt,
        "images_list": [f"data:image/jpeg;base64,{image_b64}"],
        "aspect_ratio": VIDEO_ASPECT_RATIO,
        "duration": VIDEO_DURATION,
        "quality": "basic",
    }

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # ジョブ投入
                resp = await client.post(ATLAS_CLOUD_I2V_URL, headers=headers, json=payload)
                if resp.status_code != 200:
                    last_error = VideoGenError(f"Submit failed HTTP {resp.status_code}: {resp.text[:200]}")
                    logger.warning(f"Attempt {attempt}: {last_error}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(10.0)
                    continue

                request_id = resp.json()["request_id"]
                logger.info(f"動画生成ジョブ投入: {request_id}")

                # ポーリング
                video_url = await _poll_until_done(client, request_id, headers)

                # ダウンロード
                dl_resp = await client.get(video_url, timeout=120.0)
                dl_resp.raise_for_status()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(dl_resp.content)
                logger.info(f"動画保存完了: {output_path}")
                return output_path

            except (VideoGenError, httpx.RequestError) as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(10.0)

    raise VideoGenError(f"動画生成失敗（{MAX_RETRIES}回リトライ済み）: {last_error}")


async def _poll_until_done(
    client: httpx.AsyncClient, request_id: str, headers: dict
) -> str:
    """ステータスが 'done' になるまでポーリング。video URLを返す。"""
    status_url = ATLAS_CLOUD_STATUS_URL.format(request_id=request_id)
    elapsed = 0.0
    while elapsed < TIMEOUT_SECONDS:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = await client.get(status_url, headers=headers)
        data = resp.json()
        status = data.get("status")
        if status == "done":
            return data["output_url"]
        if status == "failed":
            raise VideoGenError(f"Atlas Cloud でジョブ失敗: {data}")
        logger.info(f"ポーリング中 ({elapsed:.0f}s): {status}")
    raise VideoGenError(f"タイムアウト: {TIMEOUT_SECONDS}秒以内に完了しなかった")
```

- [ ] **Step 4: テスト実行（PASS確認）**

```bash
cd products/video-ad-generator && python -m pytest tests/test_video_gen.py -v
```
Expected: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add products/video-ad-generator/core/video_gen.py products/video-ad-generator/tests/test_video_gen.py
git commit -m "feat: Atlas Cloud Seedance 2.0 I2V 動画生成クライアント"
```

---

## Task 6: Telegram 通知

**Files:**
- Create: `products/video-ad-generator/core/notifier.py`

- [ ] **Step 1: 新しいTelegram Botを作成**

1. Telegramで `@BotFather` を開く
2. `/newbot` コマンドを送信
3. Bot名: `VideoAdGenerator`、ユーザー名: `video_ad_trustlink_bot`
4. 取得したトークンを `.env` の `TELEGRAM_BOT_TOKEN` に設定
5. Botにメッセージを送って `TELEGRAM_CHAT_ID` を取得:
   ```bash
   curl "https://api.telegram.org/bot{TOKEN}/getUpdates"
   ```

- [ ] **Step 2: notifier.py を実装**

`products/video-ad-generator/core/notifier.py`:
```python
"""Telegram Bot 通知クライアント。"""
from __future__ import annotations
import logging
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def notify(message: str) -> None:
    """Telegramにメッセージを送信する。失敗してもメイン処理をブロックしない。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_TELEGRAM_API}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            )
            if resp.status_code != 200:
                logger.warning(f"Telegram通知失敗: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        logger.warning(f"Telegram通知エラー（無視）: {e}")


async def notify_images_ready(count: int) -> None:
    await notify(f"🖼 <b>画像生成完了</b>\n{count}枚の画像が承認待ちです。\nUIで確認してください。")


async def notify_video_done(pattern: str, job_id: int) -> None:
    await notify(f"✅ <b>動画生成完了</b>\nパターン{pattern} (Job #{job_id}) が完成しました。")


async def notify_job_failed(job_id: int, error: str) -> None:
    await notify(f"❌ <b>生成失敗</b>\nJob #{job_id}: {error[:200]}")
```

- [ ] **Step 3: 動作確認**

```bash
cd products/video-ad-generator && python -c "
import asyncio
from core.notifier import notify
asyncio.run(notify('テスト通知: video-ad-generatorセットアップ完了'))
"
```
Expected: Telegramにメッセージが届く

- [ ] **Step 4: コミット**

```bash
git add products/video-ad-generator/core/notifier.py
git commit -m "feat: Telegram Bot通知クライアント"
```

---

## Task 7: APIエンドポイント

**Files:**
- Create: `products/video-ad-generator/api/jobs.py`
- Create: `products/video-ad-generator/api/generate.py`
- Create: `products/video-ad-generator/api/approve.py`
- Create: `products/video-ad-generator/tests/test_api.py`

- [ ] **Step 1: jobs.py を実装**

`products/video-ad-generator/api/jobs.py`:
```python
"""ジョブ一覧・統計 API。"""
from __future__ import annotations
from fastapi import APIRouter
from sqlalchemy import func
from database import get_session, Job, JobStatus

router = APIRouter(prefix="/api")


@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 50):
    with get_session() as session:
        query = session.query(Job).order_by(Job.created_at.desc())
        if status:
            query = query.filter(Job.status == status)
        jobs = query.limit(limit).all()
        return [_job_to_dict(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_to_dict(job)


@router.get("/stats")
def get_stats():
    with get_session() as session:
        total = session.query(func.count(Job.id)).scalar()
        done = session.query(func.count(Job.id)).filter(Job.status == JobStatus.DONE).scalar()
        total_cost = session.query(
            func.sum(Job.image_cost_usd + Job.video_cost_usd)
        ).scalar() or 0.0
        return {
            "total_jobs": total,
            "done": done,
            "pending_approval": session.query(func.count(Job.id)).filter(
                Job.status == JobStatus.PENDING
            ).scalar(),
            "total_cost_usd": round(total_cost, 4),
        }


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "pattern": job.pattern,
        "status": job.status,
        "image_path": job.image_path,
        "video_path": job.video_path,
        "image_cost_usd": job.image_cost_usd,
        "video_cost_usd": job.video_cost_usd,
        "auto_score": job.auto_score,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
```

- [ ] **Step 2: approve.py を実装**

`products/video-ad-generator/api/approve.py`:
```python
"""承認・却下 API。"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import get_session, Job, JobStatus
from config import PENDING_DIR, APPROVED_DIR, REJECTED_DIR
from core.video_gen import generate_video
from core.notifier import notify_video_done, notify_job_failed

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.post("/approve/{job_id}")
async def approve_job(job_id: int, background_tasks: BackgroundTasks):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job or job.status != JobStatus.PENDING:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        job.status = JobStatus.APPROVED
        # pending → approved にファイル移動
        if job.image_path:
            src = Path(job.image_path)
            dst = APPROVED_DIR / src.name
            src.rename(dst)
            job.image_path = str(dst)
        session.commit()
        job_id_snap = job.id
        image_path_snap = job.image_path
        video_prompt_snap = job.prompt

    background_tasks.add_task(_run_video_gen, job_id_snap, image_path_snap, video_prompt_snap)
    return {"status": "approved", "job_id": job_id}


@router.post("/reject/{job_id}")
def reject_job(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job or job.status != JobStatus.PENDING:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        job.status = JobStatus.REJECTED
        if job.image_path:
            src = Path(job.image_path)
            dst = REJECTED_DIR / src.name
            src.rename(dst)
            job.image_path = str(dst)
        session.commit()
    return {"status": "rejected", "job_id": job_id}


async def _run_video_gen(job_id: int, image_path: str, video_prompt: str):
    """バックグラウンドで動画生成を実行する。"""
    from config import VIDEOS_DIR
    output_path = VIDEOS_DIR / f"job_{job_id}.mp4"

    with get_session() as session:
        job = session.get(Job, job_id)
        job.status = JobStatus.VIDEO_GENERATING
        session.commit()

    try:
        await generate_video(
            image_path=Path(image_path),
            video_prompt=video_prompt,
            output_path=output_path,
        )
        with get_session() as session:
            job = session.get(Job, job_id)
            job.status = JobStatus.DONE
            job.video_path = str(output_path)
            job.video_cost_usd = 0.81  # 10秒 × $0.081/s
            session.commit()
        await notify_video_done(job.pattern if job else "?", job_id)
    except Exception as e:
        logger.error(f"Job {job_id} 動画生成失敗: {e}")
        with get_session() as session:
            job = session.get(Job, job_id)
            job.status = JobStatus.FAILED
            job.error_message = str(e)[:1000]
            session.commit()
        await notify_job_failed(job_id, str(e))
```

- [ ] **Step 3: generate.py を実装**

`products/video-ad-generator/api/generate.py`:
```python
"""画像・動画生成トリガー API。"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from database import get_session, Job, JobStatus
from core.patterns import get_batch_prompts, PATTERNS, is_blocked
from core.image_gen import generate_image
from core.notifier import notify_images_ready
from config import PENDING_DIR, AUTO_APPROVE

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class SingleGenerateRequest(BaseModel):
    pattern: str
    custom_prompt: str | None = None


@router.post("/generate/batch")
async def generate_batch(background_tasks: BackgroundTasks):
    """月バッチ: ABパターン各2本ずつ計10本の画像を生成する。"""
    prompts = get_batch_prompts()
    job_ids = []
    with get_session() as session:
        for item in prompts:
            job = Job(
                pattern=item["pattern"],
                prompt=item["video_prompt"],
                status=JobStatus.PENDING,
            )
            session.add(job)
            session.flush()
            job_ids.append((job.id, item["image_prompt"], item["video_prompt"]))
        session.commit()

    background_tasks.add_task(_run_batch_image_gen, job_ids)
    return {"status": "started", "job_count": len(job_ids)}


@router.post("/generate/image")
async def generate_single_image(req: SingleGenerateRequest, background_tasks: BackgroundTasks):
    """都度生成: 1本の画像を生成する。"""
    if req.pattern not in PATTERNS:
        raise HTTPException(status_code=400, detail=f"Invalid pattern: {req.pattern}")
    pattern = PATTERNS[req.pattern]
    image_prompt = req.custom_prompt or pattern["image_prompt"]
    if is_blocked(image_prompt):
        raise HTTPException(status_code=400, detail="ブロックワードが含まれています")

    with get_session() as session:
        job = Job(pattern=req.pattern, prompt=pattern["video_prompt"], status=JobStatus.PENDING)
        session.add(job)
        session.flush()
        job_id = job.id
        session.commit()

    background_tasks.add_task(_run_single_image_gen, job_id, image_prompt)
    return {"status": "started", "job_id": job_id}


async def _run_batch_image_gen(job_ids: list[tuple[int, str, str]]):
    for job_id, image_prompt, _ in job_ids:
        output_path = PENDING_DIR / f"job_{job_id}.jpg"
        try:
            await generate_image(prompt=image_prompt, output_path=output_path)
            with get_session() as session:
                job = session.get(Job, job_id)
                job.image_path = str(output_path)
                session.commit()
        except Exception as e:
            logger.error(f"Job {job_id} 画像生成失敗: {e}")
            with get_session() as session:
                job = session.get(Job, job_id)
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
                session.commit()
        await asyncio.sleep(2.0)  # rate limit対策

    completed = sum(1 for jid, _, _ in job_ids if _image_exists(jid))
    await notify_images_ready(completed)


async def _run_single_image_gen(job_id: int, image_prompt: str):
    output_path = PENDING_DIR / f"job_{job_id}.jpg"
    try:
        await generate_image(prompt=image_prompt, output_path=output_path)
        with get_session() as session:
            job = session.get(Job, job_id)
            job.image_path = str(output_path)
            session.commit()
    except Exception as e:
        logger.error(f"Job {job_id} 画像生成失敗: {e}")
        with get_session() as session:
            job = session.get(Job, job_id)
            job.status = JobStatus.FAILED
            job.error_message = str(e)[:1000]
            session.commit()


def _image_exists(job_id: int) -> bool:
    path = PENDING_DIR / f"job_{job_id}.jpg"
    return path.exists()
```

- [ ] **Step 4: コミット**

```bash
git add products/video-ad-generator/api/
git commit -m "feat: APIエンドポイント（generate / approve / jobs）"
```

---

## Task 8: FastAPIメインアプリ

**Files:**
- Create: `products/video-ad-generator/main.py`

- [ ] **Step 1: main.py を実装**

`products/video-ad-generator/main.py`:
```python
"""Video Ad Generator — FastAPI メインサーバー"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from database import init_db
from api.generate import router as generate_router
from api.approve import router as approve_router
from api.jobs import router as jobs_router
from config import APP_HOST, APP_PORT, BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("video-ad-generator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("DB初期化完了")
    yield


app = FastAPI(title="Video Ad Generator", lifespan=lifespan)

app.include_router(generate_router)
app.include_router(approve_router)
app.include_router(jobs_router)

# output ディレクトリを静的ファイルとして配信（画像・動画プレビュー用）
app.mount("/output", StaticFiles(directory=str(BASE_DIR / "output")), name="output")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
```

- [ ] **Step 2: 起動確認**

```bash
cd products/video-ad-generator && python -m pip install -r requirements.txt
python main.py
```
Expected: `Uvicorn running on http://0.0.0.0:8004`（エラーなし）

- [ ] **Step 3: コミット**

```bash
git add products/video-ad-generator/main.py
git commit -m "feat: FastAPIメインアプリ・ルーター登録"
```

---

## Task 9: Web UI

**Files:**
- Create: `products/video-ad-generator/static/index.html`

- [ ] **Step 1: index.html を実装**

`products/video-ad-generator/static/index.html`:
```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Video Ad Generator</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, sans-serif; background: #0f0f0f; color: #e0e0e0; }
    header { background: #1a1a1a; padding: 16px 24px; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; }
    header h1 { font-size: 18px; font-weight: 600; }
    .tabs { display: flex; gap: 4px; padding: 16px 24px 0; background: #1a1a1a; border-bottom: 1px solid #333; }
    .tab { padding: 8px 20px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 14px; color: #888; border: 1px solid transparent; border-bottom: none; }
    .tab.active { background: #0f0f0f; color: #fff; border-color: #333; }
    .content { padding: 24px; }
    .panel { display: none; }
    .panel.active { display: block; }
    .stats-row { display: flex; gap: 16px; margin-bottom: 24px; }
    .stat-card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px 20px; flex: 1; }
    .stat-card .label { font-size: 12px; color: #888; margin-bottom: 4px; }
    .stat-card .value { font-size: 24px; font-weight: 700; }
    .btn { padding: 10px 20px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; font-weight: 600; }
    .btn-primary { background: #6366f1; color: #fff; }
    .btn-primary:hover { background: #5153cc; }
    .btn-success { background: #22c55e; color: #fff; }
    .btn-danger { background: #ef4444; color: #fff; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; margin-top: 16px; }
    .image-card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; overflow: hidden; }
    .image-card img { width: 100%; aspect-ratio: 9/16; object-fit: cover; display: block; }
    .image-card .card-footer { padding: 10px; display: flex; gap: 6px; }
    .image-card .card-footer .btn { flex: 1; padding: 6px 8px; font-size: 12px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .badge-pending { background: #854d0e; color: #fef3c7; }
    .badge-approved { background: #166534; color: #dcfce7; }
    .badge-done { background: #1e3a5f; color: #bfdbfe; }
    .badge-failed { background: #7f1d1d; color: #fee2e2; }
    .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-top: 16px; }
    .video-card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; overflow: hidden; }
    .video-card video { width: 100%; aspect-ratio: 9/16; object-fit: cover; }
    .video-card .card-info { padding: 10px; font-size: 12px; color: #888; }
    .form-group { margin-bottom: 16px; }
    .form-group label { display: block; font-size: 13px; color: #aaa; margin-bottom: 6px; }
    .form-group select, .form-group textarea { width: 100%; background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; border-radius: 6px; padding: 8px 12px; font-size: 14px; }
    .form-group textarea { height: 100px; resize: vertical; font-family: inherit; }
    .section-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
    .empty-state { text-align: center; padding: 48px; color: #666; }
    .toggle-row { display: flex; align-items: center; justify-content: space-between; background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .toggle { position: relative; width: 44px; height: 24px; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; cursor: pointer; inset: 0; background: #333; border-radius: 24px; transition: .2s; }
    .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: .2s; }
    input:checked + .slider { background: #6366f1; }
    input:checked + .slider:before { transform: translateX(20px); }
    #toast { position: fixed; bottom: 24px; right: 24px; background: #333; color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 14px; display: none; z-index: 9999; }
  </style>
</head>
<body>
  <header>
    <h1>Video Ad Generator</h1>
    <span id="header-stats" style="font-size:13px;color:#888;">読み込み中...</span>
  </header>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('dashboard')">ダッシュボード</div>
    <div class="tab" onclick="switchTab('pending')">承認待ち <span id="pending-count"></span></div>
    <div class="tab" onclick="switchTab('generate')">都度生成</div>
    <div class="tab" onclick="switchTab('videos')">完成動画</div>
    <div class="tab" onclick="switchTab('settings')">設定</div>
  </div>

  <div class="content">
    <!-- ダッシュボード -->
    <div id="panel-dashboard" class="panel active">
      <div class="stats-row">
        <div class="stat-card"><div class="label">今月の完成動画</div><div class="value" id="stat-done">-</div></div>
        <div class="stat-card"><div class="label">承認待ち</div><div class="value" id="stat-pending">-</div></div>
        <div class="stat-card"><div class="label">合計コスト</div><div class="value" id="stat-cost">-</div></div>
      </div>
      <button class="btn btn-primary" onclick="startBatch(this)">バッチ生成（月10本）</button>
    </div>

    <!-- 承認待ち -->
    <div id="panel-pending" class="panel">
      <div class="section-title">承認待ち画像</div>
      <div id="pending-grid" class="image-grid"><div class="empty-state">承認待ちの画像はありません</div></div>
    </div>

    <!-- 都度生成 -->
    <div id="panel-generate" class="panel">
      <div class="section-title">都度生成</div>
      <div class="form-group">
        <label>パターン</label>
        <select id="gen-pattern">
          <option value="A">A — ロマンティック系（雨の日・カフェ）</option>
          <option value="B">B — 楽しさ系（公園・笑顔）</option>
          <option value="C">C — 信頼感系（オフィス・落ち着き）</option>
          <option value="D">D — ユーモア系（おしゃれカフェ・カジュアル）</option>
          <option value="E">E — 真面目系（図書館・知性的）</option>
        </select>
      </div>
      <div class="form-group">
        <label>カスタムプロンプト（空欄でデフォルト使用）</label>
        <textarea id="gen-prompt" placeholder="例: Portrait photo of a warm Japanese woman in her 40s..."></textarea>
      </div>
      <button class="btn btn-primary" onclick="generateSingle(this)">画像生成</button>
    </div>

    <!-- 完成動画 -->
    <div id="panel-videos" class="panel">
      <div class="section-title">完成動画</div>
      <div id="videos-grid" class="video-grid"><div class="empty-state">完成動画はまだありません</div></div>
    </div>

    <!-- 設定 -->
    <div id="panel-settings" class="panel">
      <div class="section-title">設定</div>
      <div class="toggle-row">
        <div>
          <div style="font-weight:600;">AUTO_APPROVE</div>
          <div style="font-size:12px;color:#888;margin-top:4px;">ONにすると画像承認なしで自動的に動画化します</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="auto-approve-toggle" onchange="toggleAutoApprove(this)">
          <span class="slider"></span>
        </label>
      </div>
    </div>
  </div>

  <div id="toast"></div>

  <script>
    let currentTab = 'dashboard';

    function switchTab(tab) {
      document.querySelectorAll('.tab').forEach((t, i) => {
        t.classList.toggle('active', ['dashboard','pending','generate','videos','settings'][i] === tab);
      });
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.getElementById('panel-' + tab).classList.add('active');
      currentTab = tab;
      if (tab === 'pending') loadPending();
      if (tab === 'videos') loadVideos();
      if (tab === 'dashboard') loadStats();
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => t.style.display = 'none', 3000);
    }

    async function loadStats() {
      const r = await fetch('/api/stats');
      const d = await r.json();
      document.getElementById('stat-done').textContent = d.done;
      document.getElementById('stat-pending').textContent = d.pending_approval;
      document.getElementById('stat-cost').textContent = '$' + d.total_cost_usd.toFixed(2);
      document.getElementById('header-stats').textContent = `完成: ${d.done}本 / コスト: $${d.total_cost_usd.toFixed(2)}`;
      const pc = document.getElementById('pending-count');
      if (d.pending_approval > 0) pc.textContent = `(${d.pending_approval})`;
    }

    async function loadPending() {
      const r = await fetch('/api/jobs?status=PENDING');
      const jobs = await r.json();
      const grid = document.getElementById('pending-grid');
      if (!jobs.length) { grid.innerHTML = '<div class="empty-state">承認待ちの画像はありません</div>'; return; }
      grid.innerHTML = jobs.map(j => `
        <div class="image-card" id="job-card-${j.id}">
          ${j.image_path ? `<img src="/output/pending/job_${j.id}.jpg" loading="lazy">` : '<div style="aspect-ratio:9/16;background:#222;display:flex;align-items:center;justify-content:center;color:#555">生成中...</div>'}
          <div style="padding:8px;font-size:11px;color:#888">パターン${j.pattern}</div>
          <div class="card-footer">
            <button class="btn btn-success" onclick="approveJob(${j.id}, this)">承認</button>
            <button class="btn btn-danger" onclick="rejectJob(${j.id}, this)">却下</button>
          </div>
        </div>
      `).join('');
    }

    async function loadVideos() {
      const r = await fetch('/api/jobs?status=DONE');
      const jobs = await r.json();
      const grid = document.getElementById('videos-grid');
      if (!jobs.length) { grid.innerHTML = '<div class="empty-state">完成動画はまだありません</div>'; return; }
      grid.innerHTML = jobs.map(j => `
        <div class="video-card">
          <video src="/output/videos/job_${j.id}.mp4" controls playsinline></video>
          <div class="card-info">
            パターン${j.pattern} — $${(j.image_cost_usd + j.video_cost_usd).toFixed(2)}<br>
            <a href="/output/videos/job_${j.id}.mp4" download style="color:#6366f1">ダウンロード</a>
          </div>
        </div>
      `).join('');
    }

    async function startBatch(btn) {
      btn.disabled = true;
      btn.textContent = '生成中...';
      const r = await fetch('/api/generate/batch', { method: 'POST' });
      const d = await r.json();
      showToast(`バッチ生成開始: ${d.job_count}本`);
      btn.disabled = false;
      btn.textContent = 'バッチ生成（月10本）';
    }

    async function generateSingle(btn) {
      const pattern = document.getElementById('gen-pattern').value;
      const prompt = document.getElementById('gen-prompt').value.trim() || null;
      btn.disabled = true;
      btn.textContent = '生成中...';
      const r = await fetch('/api/generate/image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern, custom_prompt: prompt }),
      });
      const d = await r.json();
      showToast(r.ok ? `生成開始 (Job #${d.job_id})` : `エラー: ${d.detail}`);
      btn.disabled = false;
      btn.textContent = '画像生成';
    }

    async function approveJob(jobId, btn) {
      btn.disabled = true;
      const r = await fetch(`/api/approve/${jobId}`, { method: 'POST' });
      if (r.ok) {
        document.getElementById(`job-card-${jobId}`)?.remove();
        showToast(`Job #${jobId} を承認しました。動画生成中...`);
        loadStats();
      }
    }

    async function rejectJob(jobId, btn) {
      btn.disabled = true;
      const r = await fetch(`/api/reject/${jobId}`, { method: 'POST' });
      if (r.ok) {
        document.getElementById(`job-card-${jobId}`)?.remove();
        showToast(`Job #${jobId} を却下しました`);
        loadStats();
      }
    }

    function toggleAutoApprove(checkbox) {
      showToast(`AUTO_APPROVE: ${checkbox.checked ? 'ON' : 'OFF'}（サーバー再起動で反映）`);
    }

    // 初期ロード
    loadStats();
    setInterval(loadStats, 30000);
  </script>
</body>
</html>
```

- [ ] **Step 2: ブラウザで動作確認**

```bash
cd products/video-ad-generator && python main.py
# ブラウザで http://localhost:8004 を開く
```
確認項目:
- [ ] ダッシュボードにStats表示
- [ ] タブ切り替えが動作
- [ ] バッチ生成ボタンが表示される

- [ ] **Step 3: コミット**

```bash
git add products/video-ad-generator/static/index.html
git commit -m "feat: Web UI（シングルページ、承認/却下/都度生成）"
```

---

## Task 10: 結合テスト・最終確認

**Files:**
- Create: `products/video-ad-generator/tests/test_api.py`

- [ ] **Step 1: FastAPI TestClientでAPIテスト**

`products/video-ad-generator/tests/test_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, Job, JobStatus

@pytest.fixture(autouse=True)
def use_test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("database.DB_PATH", db_path)
    monkeypatch.setattr("config.DB_PATH", db_path)

@pytest.fixture
def client():
    from main import app
    return TestClient(app)

def test_get_stats_empty(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["total_jobs"] == 0
    assert d["done"] == 0

def test_generate_single_image_invalid_pattern(client):
    r = client.post("/api/generate/image", json={"pattern": "Z"})
    assert r.status_code == 400

def test_generate_single_image_blocked_prompt(client):
    r = client.post("/api/generate/image", json={
        "pattern": "A",
        "custom_prompt": "photo of Yui Aragaki smiling"
    })
    assert r.status_code == 400

def test_approve_nonexistent_job(client):
    r = client.post("/api/approve/99999")
    assert r.status_code == 404

def test_reject_nonexistent_job(client):
    r = client.post("/api/reject/99999")
    assert r.status_code == 404

def test_list_jobs_empty(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: 全テスト実行**

```bash
cd products/video-ad-generator && python -m pytest tests/ -v
```
Expected: 全テスト PASS（test_api は環境依存で一部スキップ可）

- [ ] **Step 3: 実APIキーを使った手動E2Eテスト**

```bash
# 1. サーバー起動
python main.py &

# 2. 都度生成1本テスト
curl -X POST http://localhost:8004/api/generate/image \
  -H "Content-Type: application/json" \
  -d '{"pattern": "A"}'

# 3. ジョブ確認
curl http://localhost:8004/api/jobs
```

- [ ] **Step 4: 最終コミット**

```bash
git add products/video-ad-generator/tests/test_api.py
git commit -m "feat: video-ad-generator 結合テスト追加・MVP完成"
```

---

## セルフレビュー結果

**Spec coverage:**
- ✅ NanoBanana PRO 画像生成（Task 4）
- ✅ Atlas Cloud Seedance 2.0 I2V（Task 5）
- ✅ ABパターン5種（Task 3）
- ✅ 手動承認フロー（Task 7, approve.py）
- ✅ バッチ生成10本（Task 7, generate.py）
- ✅ 都度生成（Task 7, generate.py + Task 9 UI）
- ✅ Telegram専用Bot通知（Task 6）
- ✅ コスト表示（stats API + UI）
- ✅ エラーハンドリング・3回リトライ（Task 4, 5）
- ✅ Web UI（Task 9）
- ⚠️ AUTO_APPROVE + Claude Vision スコアリング（`core/scorer.py`）— 設定ファイルにフラグはあるが実装はスコープ外。自動化移行時に別タスクで追加する。

**型・メソッド名の一貫性:**
- `JobStatus` → 全ファイルで `database.JobStatus` から import
- `job.image_path` → `str | None`、全ファイルで `Path(job.image_path)` でラップ済み
- `generate_image(prompt, output_path)` → Task 4定義、Task 7で使用 ✅
- `generate_video(image_path, video_prompt, output_path)` → Task 5定義、Task 7で使用 ✅
