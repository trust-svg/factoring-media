# 汎用動画ジェネレーター Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 既存のマッチング広告専用動画ジェネレーターを、画像 + 自由プロンプトで任意動画を生成できる汎用ツールに拡張し、Seedance / Veo 3.1 Lite / Kling V3.0 Pro の3モデル対応・テンプレ DB 化・カメラプリセット制御を導入する。

**Architecture:** `core/video_providers/` に `VideoProvider` 抽象基底クラスを置き、各モデル実装を分離。既存固定パターンは DB の `templates` テーブルに移行し、CRUD 操作を可能にする。Alembic でスキーマ管理を導入。既存「バッチ生成」フローは無傷のまま温存。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic / SQLite / pytest + pytest-asyncio + respx (HTTPモック) / google-genai SDK / httpx

**Spec:** `products/video-ad-generator/docs/specs/2026-05-01-general-video-generator-design.md`

**Working dir:** すべて `products/video-ad-generator/` 配下で作業する。コマンドは特に注記がなければこのディレクトリを cwd として実行する前提。

---

## ファイル構造

### 新規作成ファイル

| パス | 役割 |
|---|---|
| `alembic.ini` | Alembic 設定 |
| `migrations/env.py` | Alembic 環境設定 |
| `migrations/versions/0001_add_templates_and_job_columns.py` | 初回マイグレーション |
| `migrations/run.sh` | backup / migrate / rollback スクリプト |
| `core/camera_presets.py` | 7 種カメラプリセット定義 + プロバイダー別パラメータ変換 |
| `core/safety.py` | ブロックワード検査（既存 `core/patterns.py` から移動） |
| `core/templates.py` | テンプレ CRUD ロジック |
| `core/video_providers/__init__.py` | `VideoProvider` ABC + `VideoGenRequest` dataclass + `get_provider()` ファクトリ |
| `core/video_providers/seedance.py` | 既存 `core/video_gen.py` のロジックを移植 |
| `core/video_providers/veo3.py` | Gemini API 経由の Veo 3.1 Lite |
| `core/video_providers/kling.py` | muapi.ai 経由の Kling V3.0 Pro |
| `core/video_providers/_telegram_upload.py` | 共通の Telegram 画像アップロード関数 |
| `api/templates.py` | テンプレ CRUD API ルーター |
| `api/upload.py` | 画像アップロード API |
| `static/templates.html` | テンプレ管理画面 |
| `tests/test_camera_presets.py` |  |
| `tests/test_video_providers_base.py` |  |
| `tests/test_seedance_provider.py` |  |
| `tests/test_veo3_provider.py` |  |
| `tests/test_kling_provider.py` |  |
| `tests/test_safety.py` |  |
| `tests/test_templates.py` |  |
| `tests/test_api_templates.py` |  |
| `tests/test_api_upload.py` |  |
| `tests/test_api_generate_extended.py` |  |
| `tests/test_api_jobs_cost.py` |  |

### 変更ファイル

| パス | 変更内容 |
|---|---|
| `database.py` | `Template` モデル追加、`Job` に新規列追加 |
| `config.py` | 環境変数追加（GEMINI/MUAPI Kling 等） |
| `core/video_gen.py` | `seedance` プロバイダー呼び出しに移譲する thin wrapper |
| `core/patterns.py` | `_BLOCK_WORDS` を `core/safety.py` に移動、`get_batch_prompts()` を templates テーブル経由に変更 |
| `core/notifier.py` | 失敗通知に `progress_stage` を含める引数追加 |
| `api/generate.py` | 自由入力 + provider 選択を受け付け |
| `api/approve.py` | 承認時にプロバイダーを動的選択 |
| `api/jobs.py` | `/api/jobs/cost-summary` を追加、`_job_to_dict` に新列追加 |
| `static/index.html` | 「動画作成」フォーム拡張 + テンプレ管理リンク |
| `requirements.txt` | `alembic` を追加 |
| `.env.example` | 新キー追加 |
| `conftest.py` | テスト環境変数追加（`MUAPI_KLING_MODEL_ID` 等） |

---

## Task 1: Alembic 導入とバックアップスクリプト

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/run.sh`
- Modify: `requirements.txt`
- Modify: `.gitignore`（`migrations/versions/__pycache__/` を追加）

- [ ] **Step 1: alembic を依存に追加**

`requirements.txt` の末尾に1行追加:

```
alembic>=1.13.0
```

- [ ] **Step 2: 仮想環境を有効化して alembic をインストール**

Run: `source venv/bin/activate && pip install alembic>=1.13.0`
Expected: `Successfully installed alembic-1.x.x`

- [ ] **Step 3: alembic 初期化**

Run: `alembic init migrations`
Expected: `migrations/` ディレクトリが作成され、`alembic.ini` が生成される。

- [ ] **Step 4: alembic.ini で SQLite URL を設定**

`alembic.ini` の `sqlalchemy.url = ` の行を以下に変更:

```ini
sqlalchemy.url = sqlite:///./video_ad.db
```

- [ ] **Step 5: migrations/env.py で SQLAlchemy モデルをロード**

`migrations/env.py` の `target_metadata = None` を以下に変更:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import Base
target_metadata = Base.metadata
```

- [ ] **Step 6: migrations/run.sh を作成**

Create `migrations/run.sh` with content:

```bash
#!/usr/bin/env bash
# Alembic マイグレーションのラッパースクリプト。
# 必ずこのスクリプト経由でマイグレーションを実行する（直接 alembic コマンドを叩かない）。
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-help}" in
  backup)
    ts=$(date +%Y%m%d_%H%M%S)
    cp video_ad.db "video_ad.db.bak.${ts}"
    echo "✓ バックアップ作成: video_ad.db.bak.${ts}"
    ;;
  migrate)
    "$0" backup
    alembic upgrade head
    echo "✓ マイグレーション完了"
    ;;
  rollback)
    if [ -z "${2:-}" ]; then
      echo "Usage: $0 rollback <backup_filename>"
      ls -t video_ad.db.bak.* 2>/dev/null | head -5
      exit 1
    fi
    if [ ! -f "$2" ]; then
      echo "❌ バックアップファイルが見つかりません: $2"
      exit 1
    fi
    cp "$2" video_ad.db
    echo "✓ ロールバック完了: $2 → video_ad.db"
    ;;
  downgrade)
    "$0" backup
    alembic downgrade -1
    echo "✓ Alembic 1段階ダウングレード完了"
    ;;
  *)
    echo "Usage: $0 {backup|migrate|rollback <file>|downgrade}"
    exit 1
    ;;
esac
```

- [ ] **Step 7: 実行権限付与**

Run: `chmod +x migrations/run.sh`

- [ ] **Step 8: バックアップ動作確認**

Run: `./migrations/run.sh backup`
Expected: `✓ バックアップ作成: video_ad.db.bak.YYYYMMDD_HHMMSS` が出力され、ファイルが存在する。

確認: `ls -la video_ad.db.bak.* | head -3`

- [ ] **Step 9: alembic 動作確認**

Run: `alembic current`
Expected: 何も出力されない（マイグレーション未適用の正常状態）。

- [ ] **Step 10: .gitignore 更新**

`.gitignore` の末尾に追加:

```
video_ad.db.bak.*
migrations/__pycache__/
migrations/versions/__pycache__/
```

- [ ] **Step 11: コミット**

```bash
git add requirements.txt alembic.ini migrations/env.py migrations/script.py.mako migrations/run.sh .gitignore
git commit -m "feat(video-ad-generator): introduce Alembic migrations + backup script"
```

---

## Task 2: Template モデル追加とJob列追加

**Files:**
- Modify: `database.py`
- Test: `tests/test_database.py` (拡張)

- [ ] **Step 1: 失敗テストを書く（Template モデルが存在することの確認）**

`tests/test_database.py` の末尾に追加:

```python
def test_template_model_creates():
    from database import Template, Base, JobStatus
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        t = Template(
            name="テスト",
            category="custom",
            image_prompt="img",
            video_prompt="vid",
            default_provider="seedance",
            default_aspect="9:16",
            default_duration=10,
            is_archived=False,
        )
        session.add(t)
        session.commit()
        assert t.id is not None


def test_job_has_new_columns():
    from database import Job, Base
    from sqlalchemy import create_engine, inspect
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert "template_id" in cols
    assert "provider" in cols
    assert "aspect_ratio" in cols
    assert "duration_seconds" in cols
    assert "camera_preset" in cols
    assert "image_source" in cols
    assert "video_progress_stage" in cols
    assert "video_cost_calc_basis" in cols
```

- [ ] **Step 2: テスト実行で失敗を確認**

Run: `pytest tests/test_database.py::test_template_model_creates tests/test_database.py::test_job_has_new_columns -v`
Expected: FAIL `ImportError: cannot import name 'Template'`

- [ ] **Step 3: database.py に Template モデルと Job 新規列を追加**

`database.py` の Job クラスに新規列を追加し、Template クラスを追加する。完全な書き換え版:

```python
import enum
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Float, DateTime, Enum, Integer, Boolean, ForeignKey
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
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"), nullable=True)
    prompt: Mapped[str] = mapped_column(String(2000))
    provider: Mapped[str] = mapped_column(String(50), default="seedance")
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=10)
    camera_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_source: Mapped[str] = mapped_column(String(20), default="generated")
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
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
```

**注**: `pattern` 列は `nullable=True` に変更。既存データの `pattern` 値はそのまま残る。

- [ ] **Step 4: テスト再実行で成功を確認**

Run: `pytest tests/test_database.py -v`
Expected: PASS（既存 `test_database.py` のテストも含めて全パス）

- [ ] **Step 5: コミット**

```bash
git add database.py tests/test_database.py
git commit -m "feat(video-ad-generator): add Template model and extend Job columns"
```

---

## Task 3: 初回 Alembic マイグレーション + テンプレシード

**Files:**
- Create: `migrations/versions/0001_add_templates_and_job_columns.py`

- [ ] **Step 1: マイグレーションファイル自動生成**

Run: `alembic revision --autogenerate -m "add_templates_and_job_columns"`
Expected: `migrations/versions/0001_xxx.py`（または別の hash）が生成される。

- [ ] **Step 2: 生成されたマイグレーションファイルをリネーム**

生成された `migrations/versions/<hash>_add_templates_and_job_columns.py` を `migrations/versions/0001_add_templates_and_job_columns.py` にリネーム（revision id は維持）。

- [ ] **Step 3: マイグレーションファイルにテンプレシードを追加**

ファイル末尾の `def upgrade()` 関数の最後（テーブル作成の後）に、既存5パターンのシードを追加:

```python
def upgrade() -> None:
    # ... auto-generated schema changes ...

    # 既存5パターンを templates テーブルにシード
    from sqlalchemy import table, column, String, Integer, Boolean
    templates_table = table(
        "templates",
        column("name", String),
        column("category", String),
        column("image_prompt", String),
        column("video_prompt", String),
        column("default_provider", String),
        column("default_aspect", String),
        column("default_duration", Integer),
        column("default_camera_preset", String),
        column("is_archived", Boolean),
    )

    seed_data = [
        {
            "name": "ロマンティック系（A）",
            "category": "matching_ad",
            "image_prompt": "Portrait photo of a warm Japanese woman in her late 30s to early 40s, soft natural makeup, gentle smile, casual-elegant blouse in muted rose tones, sitting at a cozy cafe by a rain-streaked window, soft bokeh background, natural window light, upper body shot, realistic photography, no text, not a real person, fictional character",
            "video_prompt": "The woman gently wraps her hands around a coffee cup and looks out at the rain, soft smile, slow cinematic camera pull-back, warm cafe ambience, peaceful romantic atmosphere",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": "dolly_out",
            "is_archived": False,
        },
        {
            "name": "楽しさ系（B）",
            "category": "matching_ad",
            "image_prompt": "Portrait photo of a cheerful Japanese woman in her early 40s, natural makeup, bright genuine laugh, casual colorful outfit, sitting on a park bench surrounded by greenery and sunlight, upper body shot, realistic photography, no text, not a real person, fictional character",
            "video_prompt": "The woman laughs lightly and brushes hair from her face, light breeze moves through the trees behind her, joyful energy, slow-motion capture, warm golden hour lighting",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": "static",
            "is_archived": False,
        },
        {
            "name": "信頼感系（C）",
            "category": "matching_ad",
            "image_prompt": "Portrait photo of a composed Japanese woman in her mid 40s, minimal elegant makeup, calm confident expression, smart casual blazer in navy or grey, modern office environment background, upper body shot, realistic photography, no text, not a real person, fictional character",
            "video_prompt": "The woman looks up from her desk and gives a small warm smile, calm and composed movement, soft office lighting, steady camera, professional yet approachable atmosphere",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": "static",
            "is_archived": False,
        },
        {
            "name": "ユーモア系（D）",
            "category": "matching_ad",
            "image_prompt": "Portrait photo of a fun playful Japanese woman in her late 30s, light natural makeup, mischievous grin, casual trendy outfit, stylish modern cafe background with colorful decor, upper body shot, realistic photography, no text, not a real person, fictional character",
            "video_prompt": "The woman notices the camera, breaks into a wide grin and gives a small wave, spontaneous and lighthearted movement, bright cafe atmosphere, handheld-style camera feel",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": "static",
            "is_archived": False,
        },
        {
            "name": "真面目系（E）",
            "category": "matching_ad",
            "image_prompt": "Portrait photo of an intellectual Japanese woman in her early 50s, elegant minimal makeup, thoughtful expression, simple sophisticated blouse, library or bookshelf background, soft reading lamp light, upper body shot, realistic photography, no text, not a real person, fictional character",
            "video_prompt": "The woman closes a book gently and looks up with a quiet confident smile, deliberate graceful movement, warm library lighting, slow zoom-in, intelligent serene atmosphere",
            "default_provider": "seedance",
            "default_aspect": "9:16",
            "default_duration": 10,
            "default_camera_preset": "dolly_in",
            "is_archived": False,
        },
    ]
    op.bulk_insert(templates_table, seed_data)
```

`downgrade()` は自動生成のままで OK（テーブル削除でシードも消える）。

- [ ] **Step 4: マイグレーション適用（バックアップ→migrate）**

Run: `./migrations/run.sh migrate`
Expected: `✓ バックアップ作成` の後 `✓ マイグレーション完了` が出力。

- [ ] **Step 5: スキーマ確認**

Run: `python -c "from sqlalchemy import create_engine, inspect; e = create_engine('sqlite:///video_ad.db'); insp = inspect(e); print('templates:', [c['name'] for c in insp.get_columns('templates')]); print('jobs:', [c['name'] for c in insp.get_columns('jobs')])"`
Expected: 両方の列リストに新規列が含まれる。

- [ ] **Step 6: シード確認**

Run: `python -c "from database import get_session, Template; s = get_session(); ts = s.query(Template).all(); print(len(ts), [t.name for t in ts])"`
Expected: `5 ['ロマンティック系（A）', '楽しさ系（B）', ...]`

- [ ] **Step 7: ロールバック動作確認**

Run: `./migrations/run.sh downgrade && python -c "from sqlalchemy import create_engine, inspect; print(inspect(create_engine('sqlite:///video_ad.db')).has_table('templates'))"`
Expected: `False`（templates テーブルが消える）

- [ ] **Step 8: 再度マイグレーション適用**

Run: `./migrations/run.sh migrate`
Expected: 再びマイグレーション完了。

- [ ] **Step 9: コミット**

```bash
git add migrations/versions/0001_add_templates_and_job_columns.py
git commit -m "feat(video-ad-generator): initial migration with template seed data"
```

---

## Task 4: Camera Presets モジュール

**Files:**
- Create: `core/camera_presets.py`
- Create: `tests/test_camera_presets.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_camera_presets.py`:

```python
from core.camera_presets import (
    CAMERA_PRESETS,
    get_kling_params,
    get_prompt_hint,
    list_preset_keys,
)


def test_static_preset_exists():
    assert "static" in CAMERA_PRESETS


def test_seven_presets():
    assert len(CAMERA_PRESETS) == 7


def test_get_kling_params_for_dolly_in():
    assert get_kling_params("dolly_in") == {"zoom": 5}


def test_get_kling_params_for_static_returns_empty():
    assert get_kling_params("static") == {}


def test_get_kling_params_for_none_returns_empty():
    assert get_kling_params(None) == {}


def test_get_prompt_hint_for_pan_left():
    assert "pan left" in get_prompt_hint("pan_left").lower()


def test_get_prompt_hint_for_static_returns_empty():
    assert get_prompt_hint("static") == ""


def test_get_prompt_hint_for_none_returns_empty():
    assert get_prompt_hint(None) == ""


def test_unknown_preset_raises():
    import pytest
    with pytest.raises(KeyError):
        get_kling_params("nonexistent_preset")


def test_list_preset_keys():
    keys = list_preset_keys()
    assert set(keys) == {"static", "dolly_in", "dolly_out", "pan_left", "pan_right", "tilt_up", "orbit_left"}
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_camera_presets.py -v`
Expected: FAIL `ImportError: cannot import name 'CAMERA_PRESETS' from 'core.camera_presets'`

- [ ] **Step 3: 実装**

`core/camera_presets.py`:

```python
"""カメラ動作プリセット定義。
プロバイダーごとに「Klingは数値パラメータ／Seedance・Veo3はプロンプト埋め込み」を分岐する。
"""
from __future__ import annotations

CAMERA_PRESETS: dict[str, dict] = {
    "static": {
        "label": "固定",
        "kling": {},
        "prompt_hint": "",
    },
    "dolly_in": {
        "label": "ドリーイン",
        "kling": {"zoom": 5},
        "prompt_hint": "slow dolly-in toward subject",
    },
    "dolly_out": {
        "label": "ドリーアウト",
        "kling": {"zoom": -5},
        "prompt_hint": "slow dolly-out away from subject",
    },
    "pan_left": {
        "label": "左パン",
        "kling": {"pan": -5},
        "prompt_hint": "smooth pan left",
    },
    "pan_right": {
        "label": "右パン",
        "kling": {"pan": 5},
        "prompt_hint": "smooth pan right",
    },
    "tilt_up": {
        "label": "上ティルト",
        "kling": {"tilt": 5},
        "prompt_hint": "tilt up gently",
    },
    "orbit_left": {
        "label": "左オービット",
        "kling": {"horizontal": -5},
        "prompt_hint": "camera orbits left around subject",
    },
}


def get_kling_params(preset_key: str | None) -> dict:
    """Kling 用の camera_control 数値パラメータを返す。"""
    if preset_key is None:
        return {}
    if preset_key not in CAMERA_PRESETS:
        raise KeyError(f"Unknown camera preset: {preset_key}")
    return dict(CAMERA_PRESETS[preset_key]["kling"])


def get_prompt_hint(preset_key: str | None) -> str:
    """Seedance/Veo3 用のプロンプト埋め込み文字列を返す。"""
    if preset_key is None:
        return ""
    if preset_key not in CAMERA_PRESETS:
        raise KeyError(f"Unknown camera preset: {preset_key}")
    return CAMERA_PRESETS[preset_key]["prompt_hint"]


def list_preset_keys() -> list[str]:
    return list(CAMERA_PRESETS.keys())
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_camera_presets.py -v`
Expected: 全 10 テスト PASS

- [ ] **Step 5: コミット**

```bash
git add core/camera_presets.py tests/test_camera_presets.py
git commit -m "feat(video-ad-generator): add camera presets module"
```

---

## Task 5: Safety モジュール（ブロックワード移動）

**Files:**
- Create: `core/safety.py`
- Create: `tests/test_safety.py`
- Modify: `core/patterns.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_safety.py`:

```python
from core.safety import is_blocked, BLOCK_WORDS


def test_blocks_real_actress():
    assert is_blocked("Photo of aragaki yui smiling")


def test_blocks_japanese_name():
    assert is_blocked("綾瀬はるかのような女性")


def test_passes_clean_prompt():
    assert not is_blocked("Portrait of a fictional woman")


def test_passes_empty():
    assert not is_blocked("")


def test_block_words_are_listed():
    assert "aragaki" in BLOCK_WORDS
    assert "綾瀬" in BLOCK_WORDS
    assert "celebrity" in BLOCK_WORDS
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_safety.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: core/safety.py を作成**

```python
"""プロンプト安全性検査。実在人物名・著名人参照をブロックする。"""
from __future__ import annotations

BLOCK_WORDS: tuple[str, ...] = (
    "aragaki", "yui", "ishihara", "satomi", "ayase", "haruka",
    "toda", "erika", "kitagawa", "keiko", "takeuchi", "yuuko",
    "綾瀬", "新垣", "石原", "戸田", "北川", "竹内",
    "celebrity", "idol", "actress", "actor",
)


def is_blocked(prompt: str) -> bool:
    """プロンプトに実在人物の名前や不適切なワードが含まれていないか確認。"""
    lower = prompt.lower()
    return any(word in lower for word in BLOCK_WORDS)
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_safety.py -v`
Expected: 全 5 テスト PASS

- [ ] **Step 5: core/patterns.py から `_BLOCK_WORDS` と `is_blocked` を削除し、再エクスポートに変更**

`core/patterns.py` の冒頭の `_BLOCK_WORDS` 定義（2-13行）と `is_blocked` 関数（94-97行付近）を削除し、ファイル先頭付近に以下を追加:

```python
# 既存呼び出しとの後方互換のため再エクスポート
from core.safety import is_blocked  # noqa: F401
```

- [ ] **Step 6: 既存テスト（test_patterns.py）が壊れていないか確認**

Run: `pytest tests/test_patterns.py -v`
Expected: 全 PASS（`is_blocked` は再エクスポート経由で動作）

- [ ] **Step 7: コミット**

```bash
git add core/safety.py tests/test_safety.py core/patterns.py
git commit -m "refactor(video-ad-generator): extract safety module from patterns"
```

---

## Task 6: VideoProvider 抽象基底クラス

**Files:**
- Create: `core/video_providers/__init__.py`
- Create: `tests/test_video_providers_base.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_video_providers_base.py`:

```python
import pytest
from pathlib import Path
from core.video_providers import (
    VideoProvider,
    VideoGenRequest,
    PROGRESS_STAGES,
    get_provider,
)


class _DummyProvider(VideoProvider):
    name = "dummy"
    supported_aspects = ("9:16",)
    supported_durations = (10,)

    async def generate(self, req: VideoGenRequest) -> Path:
        return req.output_path

    def calc_cost(self, req: VideoGenRequest) -> float:
        return 0.5


def _make_req(aspect="9:16", duration=10):
    return VideoGenRequest(
        image_path=Path("/tmp/x.jpg"),
        video_prompt="test",
        aspect_ratio=aspect,
        duration_seconds=duration,
        camera_preset=None,
        output_path=Path("/tmp/out.mp4"),
    )


def test_validate_passes_for_supported():
    p = _DummyProvider()
    p.validate(_make_req())  # no exception


def test_validate_rejects_unsupported_aspect():
    p = _DummyProvider()
    with pytest.raises(ValueError, match="aspect"):
        p.validate(_make_req(aspect="1:1"))


def test_validate_rejects_unsupported_duration():
    p = _DummyProvider()
    with pytest.raises(ValueError, match="duration"):
        p.validate(_make_req(duration=5))


def test_progress_stages_defined():
    assert "uploading_image" in PROGRESS_STAGES
    assert "submitting" in PROGRESS_STAGES
    assert "polling" in PROGRESS_STAGES
    assert "downloading_video" in PROGRESS_STAGES


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("nonexistent_provider")
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_video_providers_base.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: core/video_providers/__init__.py を作成**

```python
"""動画生成プロバイダー抽象基底クラス。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

PROGRESS_STAGES: tuple[str, ...] = (
    "uploading_image",
    "submitting",
    "polling",
    "downloading_video",
)


@dataclass
class VideoGenRequest:
    image_path: Path
    video_prompt: str
    aspect_ratio: str
    duration_seconds: int
    camera_preset: str | None
    output_path: Path


class VideoProvider(ABC):
    """全プロバイダーが継承する基底クラス。"""

    name: str = ""
    supported_aspects: tuple[str, ...] = ()
    supported_durations: tuple[int, ...] = ()

    @abstractmethod
    async def generate(self, req: VideoGenRequest) -> Path:
        """画像と prompt から動画を生成し、output_path に保存して返す。"""

    @abstractmethod
    def calc_cost(self, req: VideoGenRequest) -> float:
        """ジョブのコストを USD で返す。"""

    def validate(self, req: VideoGenRequest) -> None:
        if req.aspect_ratio not in self.supported_aspects:
            raise ValueError(
                f"{self.name} does not support aspect {req.aspect_ratio}. "
                f"Supported: {self.supported_aspects}"
            )
        if req.duration_seconds not in self.supported_durations:
            raise ValueError(
                f"{self.name} does not support duration {req.duration_seconds}s. "
                f"Supported: {self.supported_durations}"
            )


def get_provider(name: str) -> VideoProvider:
    """プロバイダー名から実装インスタンスを返すファクトリ。"""
    if name == "seedance":
        from core.video_providers.seedance import SeedanceProvider
        return SeedanceProvider()
    if name == "veo3_lite":
        from core.video_providers.veo3 import Veo3LiteProvider
        return Veo3LiteProvider()
    if name == "kling3_pro":
        from core.video_providers.kling import Kling3ProProvider
        return Kling3ProProvider()
    raise ValueError(f"unknown provider: {name}")
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_video_providers_base.py -v`
Expected: 5 PASS（`get_provider` の他のケースは個別プロバイダー実装後にテストする）

- [ ] **Step 5: コミット**

```bash
git add core/video_providers/__init__.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): add VideoProvider abstract base + factory"
```

---

## Task 7: Telegram 画像アップロード共通関数の抽出

**Files:**
- Create: `core/video_providers/_telegram_upload.py`
- Modify: `core/video_gen.py`

- [ ] **Step 1: 既存 video_gen.py の `_upload_image_to_telegram` を共通モジュールに抽出**

`core/video_providers/_telegram_upload.py`:

```python
"""Telegram Bot 経由で画像をアップロードして公開URLを取得する共通関数。
全プロバイダーが同じ方式で画像URLを準備するために使う。
"""
from __future__ import annotations
import logging
from pathlib import Path
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


async def upload_image_to_telegram(image_path: Path) -> str:
    """画像を Telegram にアップロードして公開ダウンロードURLを返す。"""
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(image_path, "rb") as f:
            resp = await client.post(
                f"{base_url}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID},
                files={"document": (image_path.name, f, "image/jpeg")},
            )
        resp.raise_for_status()
        result = resp.json()
        file_id = result["result"]["document"]["file_id"]

        resp2 = await client.get(f"{base_url}/getFile", params={"file_id": file_id})
        resp2.raise_for_status()
        file_path = resp2.json()["result"]["file_path"]

        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        logger.info(f"Telegram upload OK: {download_url}")
        return download_url
```

- [ ] **Step 2: 既存テストが落ちないか確認**

Run: `pytest tests/test_video_gen.py -v`
Expected: 既存テストは既存実装を引き続き使うため PASS

- [ ] **Step 3: コミット**

```bash
git add core/video_providers/_telegram_upload.py
git commit -m "feat(video-ad-generator): extract telegram upload helper for reuse"
```

---

## Task 8: Seedance Provider 実装

**Files:**
- Create: `core/video_providers/seedance.py`
- Create: `tests/test_seedance_provider.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_seedance_provider.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from core.video_providers.seedance import SeedanceProvider
from core.video_providers import VideoGenRequest


def _make_req(tmp_path):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
    )


def test_seedance_metadata():
    p = SeedanceProvider()
    assert p.name == "seedance"
    assert "9:16" in p.supported_aspects
    assert "16:9" in p.supported_aspects
    assert 5 in p.supported_durations
    assert 10 in p.supported_durations


def test_calc_cost_per_video(tmp_path):
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    cost = p.calc_cost(req)
    assert cost > 0


def test_validate_rejects_1to1_ratio(tmp_path):
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    req.aspect_ratio = "1:1"
    with pytest.raises(ValueError):
        p.validate(req)


def test_camera_preset_appended_to_prompt(tmp_path):
    """camera_preset が指定されたら prompt_hint がプロンプトに追加される"""
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "dolly_in"
    enriched = p._build_prompt(req)
    assert "dolly-in" in enriched


def test_no_camera_preset_keeps_prompt_clean(tmp_path):
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    req.camera_preset = None
    assert p._build_prompt(req) == "a cat"
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_seedance_provider.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: SeedanceProvider 実装**

`core/video_providers/seedance.py`:

```python
"""Atlas Cloud Seedance 2.0 I2V API クライアント（VideoProvider 実装）。"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import httpx
from config import (
    ATLAS_CLOUD_API_KEY,
    ATLAS_CLOUD_I2V_URL,
    ATLAS_CLOUD_STATUS_URL,
)
from core.video_providers import VideoProvider, VideoGenRequest
from core.video_providers._telegram_upload import upload_image_to_telegram
from core.camera_presets import get_prompt_hint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 10.0
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0
RATE_LIMIT_WAIT = 30.0


class SeedanceError(Exception):
    pass


class SeedanceProvider(VideoProvider):
    name = "seedance"
    supported_aspects = ("9:16", "16:9")
    supported_durations = (5, 10)

    def calc_cost(self, req: VideoGenRequest) -> float:
        # Seedance 2.0 basic quality: 概算 $0.081/s（既存実装値）
        return round(0.081 * req.duration_seconds, 4)

    def _build_prompt(self, req: VideoGenRequest) -> str:
        hint = get_prompt_hint(req.camera_preset)
        if hint:
            return f"{req.video_prompt}, {hint}"
        return req.video_prompt

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        headers = {
            "x-api-key": ATLAS_CLOUD_API_KEY,
            "Content-Type": "application/json",
        }
        image_url = await upload_image_to_telegram(req.image_path)
        logger.info(f"[seedance] image_url={image_url}")

        payload = {
            "prompt": self._build_prompt(req),
            "images_list": [image_url],
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration_seconds,
            "quality": "basic",
        }

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(ATLAS_CLOUD_I2V_URL, headers=headers, json=payload)

                    # 認証/課金エラーは即時失敗
                    if resp.status_code in (401, 402, 403):
                        raise SeedanceError(
                            f"auth/billing error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    # Rate limit
                    if resp.status_code == 429:
                        logger.warning(f"[seedance] rate limited, waiting {RATE_LIMIT_WAIT}s")
                        await asyncio.sleep(RATE_LIMIT_WAIT)
                        last_error = SeedanceError(f"HTTP 429: {resp.text[:200]}")
                        continue
                    # その他 4xx は即時失敗
                    if 400 <= resp.status_code < 500:
                        raise SeedanceError(
                            f"client error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    # 5xx はリトライ
                    if resp.status_code >= 500:
                        last_error = SeedanceError(
                            f"server error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY)
                        continue

                    resp_data = resp.json()
                    request_id = resp_data["request_id"]
                    logger.info(f"[seedance] submitted: {request_id}")

                    video_url = await self._poll(client, request_id, headers)

                    dl_resp = await client.get(video_url, timeout=120.0)
                    dl_resp.raise_for_status()
                    req.output_path.parent.mkdir(parents=True, exist_ok=True)
                    req.output_path.write_bytes(dl_resp.content)
                    return req.output_path

                except SeedanceError:
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    logger.warning(f"[seedance] attempt {attempt} network error: {e}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

        raise SeedanceError(f"failed after {MAX_RETRIES} retries: {last_error}")

    async def _poll(self, client: httpx.AsyncClient, request_id: str, headers: dict) -> str:
        status_url = ATLAS_CLOUD_STATUS_URL.format(request_id=request_id)
        elapsed = 0.0
        while elapsed < TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = await client.get(status_url, headers=headers)
            if resp.status_code == 404:
                raise SeedanceError(f"status URL 404: {status_url}")
            data = resp.json()
            status = data.get("status")
            outputs = data.get("outputs") or []
            output_url = outputs[0] if outputs else (data.get("output_url") or data.get("video_url"))
            if status in ("done", "succeeded", "completed", "success"):
                if output_url:
                    return output_url
                raise SeedanceError(f"completed without output URL: {data}")
            if status in ("failed", "error", "cancelled"):
                raise SeedanceError(f"job failed: {data}")
        raise SeedanceError(f"timeout {TIMEOUT_SECONDS}s")
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_seedance_provider.py -v`
Expected: 5 PASS

- [ ] **Step 5: get_provider("seedance") のテスト追加**

`tests/test_video_providers_base.py` の末尾に追加:

```python
def test_get_provider_seedance():
    p = get_provider("seedance")
    assert p.name == "seedance"
```

Run: `pytest tests/test_video_providers_base.py -v`
Expected: 6 PASS

- [ ] **Step 6: コミット**

```bash
git add core/video_providers/seedance.py tests/test_seedance_provider.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): add SeedanceProvider with unified error handling"
```

---

## Task 9: 既存 video_gen.py を Seedance Provider への thin wrapper に変更

**Files:**
- Modify: `core/video_gen.py`

- [ ] **Step 1: video_gen.py を thin wrapper に書き換え**

```python
"""後方互換のための thin wrapper。
新規コードは core.video_providers から get_provider("seedance") を使うこと。
"""
from __future__ import annotations
import logging
from pathlib import Path
from core.video_providers import VideoGenRequest, get_provider

logger = logging.getLogger(__name__)


class VideoGenError(Exception):
    """後方互換のためのエイリアス。新規コードは SeedanceError を使う。"""
    pass


async def generate_video(image_path: Path, video_prompt: str, output_path: Path) -> Path:
    """既存呼び出しとの後方互換。Seedance 9:16/10s 固定で動画生成。"""
    provider = get_provider("seedance")
    req = VideoGenRequest(
        image_path=image_path,
        video_prompt=video_prompt,
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=output_path,
    )
    try:
        return await provider.generate(req)
    except Exception as e:
        raise VideoGenError(str(e)) from e
```

- [ ] **Step 2: 既存テスト test_video_gen.py が通るか確認**

Run: `pytest tests/test_video_gen.py -v`
Expected: 既存テストが PASS（API 互換のため）

- [ ] **Step 3: コミット**

```bash
git add core/video_gen.py
git commit -m "refactor(video-ad-generator): video_gen.py becomes thin wrapper over SeedanceProvider"
```

---

## Task 10: Veo 3.1 Lite Provider 実装

**Files:**
- Create: `core/video_providers/veo3.py`
- Create: `tests/test_veo3_provider.py`
- Modify: `config.py`（後の Task 16 でまとめて修正、ここでは触れない）

**注**: この Task 時点では `config.py` の `VEO3_MODEL_ID` 等は未定義。デフォルト値で動かしておき、Task 16 で正式に環境変数化する。

- [ ] **Step 1: 失敗テストを書く（HTTP モック使用）**

`tests/test_veo3_provider.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from core.video_providers.veo3 import Veo3LiteProvider
from core.video_providers import VideoGenRequest


def _make_req(tmp_path, duration=8):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio="9:16",
        duration_seconds=duration,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
    )


def test_veo3_metadata():
    p = Veo3LiteProvider()
    assert p.name == "veo3_lite"
    assert "9:16" in p.supported_aspects
    assert "16:9" in p.supported_aspects
    assert set(p.supported_durations) >= {4, 6, 8}


def test_calc_cost_per_second(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path, duration=8)
    cost = p.calc_cost(req)
    assert abs(cost - 0.40) < 0.001  # $0.05 × 8


def test_validate_rejects_unsupported_duration(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path, duration=10)
    with pytest.raises(ValueError, match="duration"):
        p.validate(req)


def test_camera_preset_appended_to_prompt(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "pan_left"
    assert "pan left" in p._build_prompt(req).lower()
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_veo3_provider.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: Veo3LiteProvider 実装**

`core/video_providers/veo3.py`:

```python
"""Google Gemini API 経由 Veo 3.1 Lite I2V クライアント。"""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
import base64
import httpx
from core.video_providers import VideoProvider, VideoGenRequest
from core.camera_presets import get_prompt_hint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 10.0
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0
RATE_LIMIT_WAIT = 30.0
COST_PER_SECOND_USD = 0.05


class Veo3Error(Exception):
    pass


class Veo3LiteProvider(VideoProvider):
    name = "veo3_lite"
    supported_aspects = ("9:16", "16:9")
    supported_durations = (4, 6, 8)

    def calc_cost(self, req: VideoGenRequest) -> float:
        return round(COST_PER_SECOND_USD * req.duration_seconds, 4)

    def _build_prompt(self, req: VideoGenRequest) -> str:
        hint = get_prompt_hint(req.camera_preset)
        return f"{req.video_prompt}, {hint}" if hint else req.video_prompt

    def _api_key(self) -> str:
        from config import GEMINI_API_KEY
        return GEMINI_API_KEY

    def _model_id(self) -> str:
        return os.environ.get("VEO3_MODEL_ID", "veo-3.1-fast-generate-001")

    def _generate_url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self._model_id()}:generateVideo"

    def _operation_url(self, op_name: str) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/{op_name}"

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        image_b64 = base64.b64encode(req.image_path.read_bytes()).decode("ascii")

        payload = {
            "instances": [
                {
                    "prompt": self._build_prompt(req),
                    "image": {
                        "bytesBase64Encoded": image_b64,
                        "mimeType": "image/jpeg",
                    },
                }
            ],
            "parameters": {
                "aspectRatio": req.aspect_ratio,
                "durationSeconds": req.duration_seconds,
                "sampleCount": 1,
            },
        }
        params = {"key": self._api_key()}

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        self._generate_url(), params=params, json=payload
                    )
                    if resp.status_code in (401, 402, 403):
                        raise Veo3Error(f"auth/billing HTTP {resp.status_code}: {resp.text[:200]}")
                    if resp.status_code == 429:
                        await asyncio.sleep(RATE_LIMIT_WAIT)
                        last_error = Veo3Error(f"HTTP 429: {resp.text[:200]}")
                        continue
                    if 400 <= resp.status_code < 500:
                        raise Veo3Error(f"client error HTTP {resp.status_code}: {resp.text[:200]}")
                    if resp.status_code >= 500:
                        last_error = Veo3Error(f"server error HTTP {resp.status_code}: {resp.text[:200]}")
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY)
                        continue

                    op = resp.json()
                    op_name = op.get("name")
                    if not op_name:
                        raise Veo3Error(f"no operation name in response: {op}")

                    video_url = await self._poll(client, op_name, params)
                    dl_resp = await client.get(
                        video_url, params=params, timeout=120.0
                    )
                    dl_resp.raise_for_status()
                    req.output_path.parent.mkdir(parents=True, exist_ok=True)
                    req.output_path.write_bytes(dl_resp.content)
                    return req.output_path

                except Veo3Error:
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

        raise Veo3Error(f"failed after {MAX_RETRIES} retries: {last_error}")

    async def _poll(self, client: httpx.AsyncClient, op_name: str, params: dict) -> str:
        elapsed = 0.0
        while elapsed < TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = await client.get(self._operation_url(op_name), params=params)
            if resp.status_code != 200:
                raise Veo3Error(f"poll error HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            if data.get("done"):
                if "error" in data:
                    raise Veo3Error(f"operation failed: {data['error']}")
                response = data.get("response", {})
                videos = response.get("generatedVideos") or response.get("videos") or []
                if not videos:
                    raise Veo3Error(f"no video in response: {data}")
                video = videos[0]
                video_uri = video.get("video", {}).get("uri") or video.get("uri")
                if not video_uri:
                    raise Veo3Error(f"no video URI: {video}")
                return video_uri
        raise Veo3Error(f"timeout {TIMEOUT_SECONDS}s")
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_veo3_provider.py -v`
Expected: 4 PASS

- [ ] **Step 5: get_provider("veo3_lite") のテスト追加**

`tests/test_video_providers_base.py` の末尾に追加:

```python
def test_get_provider_veo3_lite():
    p = get_provider("veo3_lite")
    assert p.name == "veo3_lite"
```

Run: `pytest tests/test_video_providers_base.py -v`
Expected: 7 PASS

- [ ] **Step 6: コミット**

```bash
git add core/video_providers/veo3.py tests/test_veo3_provider.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): add Veo3LiteProvider via Gemini API"
```

---

## Task 11: Kling V3.0 Pro Provider 実装

**Files:**
- Create: `core/video_providers/kling.py`
- Create: `tests/test_kling_provider.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_kling_provider.py`:

```python
import pytest
from pathlib import Path
from core.video_providers.kling import Kling3ProProvider
from core.video_providers import VideoGenRequest


def _make_req(tmp_path):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
    )


def test_kling_metadata():
    p = Kling3ProProvider()
    assert p.name == "kling3_pro"
    assert {"9:16", "16:9", "1:1"} <= set(p.supported_aspects)
    assert {5, 10} <= set(p.supported_durations)


def test_calc_cost_per_video(tmp_path):
    p = Kling3ProProvider()
    cost = p.calc_cost(_make_req(tmp_path))
    assert cost > 0


def test_camera_params_for_dolly_in(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "dolly_in"
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert "camera_control" in payload
    assert payload["camera_control"]["config"] == {"zoom": 5}


def test_no_camera_preset_omits_camera_control(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.camera_preset = None
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert "camera_control" not in payload


def test_camera_preset_static_omits_camera_control(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "static"
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert "camera_control" not in payload
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_kling_provider.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: Kling3ProProvider 実装**

`core/video_providers/kling.py`:

```python
"""muapi.ai 経由 Kling V3.0 Pro I2V クライアント。"""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
import httpx
from config import ATLAS_CLOUD_API_KEY, ATLAS_CLOUD_STATUS_URL
from core.video_providers import VideoProvider, VideoGenRequest
from core.video_providers._telegram_upload import upload_image_to_telegram
from core.camera_presets import get_kling_params, get_prompt_hint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 10.0
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0
RATE_LIMIT_WAIT = 30.0
COST_PER_VIDEO_USD = 0.46  # 概算（muapi.ai 公称値）


class KlingError(Exception):
    pass


class Kling3ProProvider(VideoProvider):
    name = "kling3_pro"
    supported_aspects = ("9:16", "16:9", "1:1")
    supported_durations = (5, 10)

    def calc_cost(self, req: VideoGenRequest) -> float:
        return COST_PER_VIDEO_USD

    def _i2v_url(self) -> str:
        return os.environ.get(
            "MUAPI_KLING_I2V_URL",
            "https://api.muapi.ai/api/v1/kling-v3-pro-i2v",
        )

    def _build_payload(self, req: VideoGenRequest, image_url: str) -> dict:
        prompt = req.video_prompt
        hint = get_prompt_hint(req.camera_preset)
        if hint:
            prompt = f"{prompt}, {hint}"

        payload = {
            "prompt": prompt,
            "image": image_url,
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration_seconds,
        }

        kling_params = get_kling_params(req.camera_preset)
        if kling_params:
            payload["camera_control"] = {
                "type": "simple",
                "config": kling_params,
            }
        return payload

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        image_url = await upload_image_to_telegram(req.image_path)
        payload = self._build_payload(req, image_url)
        headers = {"x-api-key": ATLAS_CLOUD_API_KEY, "Content-Type": "application/json"}

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(self._i2v_url(), headers=headers, json=payload)
                    if resp.status_code in (401, 402, 403):
                        raise KlingError(f"auth/billing HTTP {resp.status_code}: {resp.text[:200]}")
                    if resp.status_code == 429:
                        await asyncio.sleep(RATE_LIMIT_WAIT)
                        last_error = KlingError(f"HTTP 429: {resp.text[:200]}")
                        continue
                    if 400 <= resp.status_code < 500:
                        raise KlingError(f"client error HTTP {resp.status_code}: {resp.text[:200]}")
                    if resp.status_code >= 500:
                        last_error = KlingError(f"server error HTTP {resp.status_code}: {resp.text[:200]}")
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY)
                        continue

                    request_id = resp.json()["request_id"]
                    video_url = await self._poll(client, request_id, headers)
                    dl_resp = await client.get(video_url, timeout=120.0)
                    dl_resp.raise_for_status()
                    req.output_path.parent.mkdir(parents=True, exist_ok=True)
                    req.output_path.write_bytes(dl_resp.content)
                    return req.output_path
                except KlingError:
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

        raise KlingError(f"failed after {MAX_RETRIES} retries: {last_error}")

    async def _poll(self, client: httpx.AsyncClient, request_id: str, headers: dict) -> str:
        status_url = ATLAS_CLOUD_STATUS_URL.format(request_id=request_id)
        elapsed = 0.0
        while elapsed < TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = await client.get(status_url, headers=headers)
            if resp.status_code == 404:
                raise KlingError(f"status URL 404: {status_url}")
            data = resp.json()
            status = data.get("status")
            outputs = data.get("outputs") or []
            output_url = outputs[0] if outputs else (data.get("output_url") or data.get("video_url"))
            if status in ("done", "succeeded", "completed", "success"):
                if output_url:
                    return output_url
                raise KlingError(f"completed without output URL: {data}")
            if status in ("failed", "error", "cancelled"):
                raise KlingError(f"job failed: {data}")
        raise KlingError(f"timeout {TIMEOUT_SECONDS}s")
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_kling_provider.py -v`
Expected: 5 PASS

- [ ] **Step 5: get_provider("kling3_pro") のテスト追加**

`tests/test_video_providers_base.py` の末尾に追加:

```python
def test_get_provider_kling3_pro():
    p = get_provider("kling3_pro")
    assert p.name == "kling3_pro"
```

Run: `pytest tests/test_video_providers_base.py -v`
Expected: 8 PASS

- [ ] **Step 6: コミット**

```bash
git add core/video_providers/kling.py tests/test_kling_provider.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): add Kling3ProProvider with camera_control params"
```

---

## Task 12: Templates CRUD ロジック

**Files:**
- Create: `core/templates.py`
- Create: `tests/test_templates.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_templates.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database import Base, Template
from core import templates as tmpl_mod


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    monkeypatch.setattr(tmpl_mod, "get_session", lambda: sess)
    yield sess
    sess.close()


def test_create_template(session):
    t = tmpl_mod.create_template(
        name="新規",
        category="custom",
        image_prompt="img",
        video_prompt="vid",
        default_provider="seedance",
        default_aspect="9:16",
        default_duration=10,
        default_camera_preset="dolly_in",
    )
    assert t.id is not None
    assert t.name == "新規"
    assert t.is_archived is False


def test_create_template_blocks_unsafe_prompt(session):
    with pytest.raises(ValueError, match="block"):
        tmpl_mod.create_template(
            name="bad", category="custom",
            image_prompt="aragaki yui",
            video_prompt="ok",
            default_provider="seedance", default_aspect="9:16",
            default_duration=10, default_camera_preset=None,
        )


def test_list_templates_excludes_archived_by_default(session):
    tmpl_mod.create_template(
        name="A", category="custom", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    t2 = tmpl_mod.create_template(
        name="B", category="custom", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    tmpl_mod.archive_template(t2.id)
    items = tmpl_mod.list_templates()
    assert len(items) == 1
    assert items[0].name == "A"


def test_list_templates_with_archived(session):
    tmpl_mod.create_template(
        name="A", category="custom", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    t2 = tmpl_mod.create_template(
        name="B", category="custom", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    tmpl_mod.archive_template(t2.id)
    items = tmpl_mod.list_templates(include_archived=True)
    assert len(items) == 2


def test_update_template(session):
    t = tmpl_mod.create_template(
        name="A", category="custom", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    tmpl_mod.update_template(t.id, name="A2", default_duration=5)
    fresh = tmpl_mod.get_template(t.id)
    assert fresh.name == "A2"
    assert fresh.default_duration == 5


def test_filter_by_category(session):
    tmpl_mod.create_template(
        name="A", category="custom", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    tmpl_mod.create_template(
        name="B", category="matching_ad", image_prompt="i", video_prompt="v",
        default_provider="seedance", default_aspect="9:16",
        default_duration=10, default_camera_preset=None,
    )
    items = tmpl_mod.list_templates(category="matching_ad")
    assert len(items) == 1
    assert items[0].name == "B"
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_templates.py -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: 実装**

`core/templates.py`:

```python
"""テンプレート CRUD ロジック。"""
from __future__ import annotations
from database import get_session, Template
from core.safety import is_blocked


def create_template(
    *,
    name: str,
    category: str,
    image_prompt: str,
    video_prompt: str,
    default_provider: str,
    default_aspect: str,
    default_duration: int,
    default_camera_preset: str | None,
) -> Template:
    if is_blocked(image_prompt) or is_blocked(video_prompt):
        raise ValueError("プロンプトにブロックワードが含まれています")
    with get_session() as session:
        t = Template(
            name=name,
            category=category,
            image_prompt=image_prompt,
            video_prompt=video_prompt,
            default_provider=default_provider,
            default_aspect=default_aspect,
            default_duration=default_duration,
            default_camera_preset=default_camera_preset,
            is_archived=False,
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        return t


def get_template(template_id: int) -> Template | None:
    with get_session() as session:
        return session.get(Template, template_id)


def list_templates(
    *, category: str | None = None, include_archived: bool = False
) -> list[Template]:
    with get_session() as session:
        q = session.query(Template)
        if not include_archived:
            q = q.filter(Template.is_archived == False)  # noqa: E712
        if category:
            q = q.filter(Template.category == category)
        return q.order_by(Template.created_at.desc()).all()


def update_template(template_id: int, **fields) -> Template | None:
    allowed = {
        "name", "category", "image_prompt", "video_prompt",
        "default_provider", "default_aspect", "default_duration",
        "default_camera_preset", "is_archived",
    }
    sanitized = {k: v for k, v in fields.items() if k in allowed and v is not None}

    if "image_prompt" in sanitized and is_blocked(sanitized["image_prompt"]):
        raise ValueError("image_prompt にブロックワードが含まれています")
    if "video_prompt" in sanitized and is_blocked(sanitized["video_prompt"]):
        raise ValueError("video_prompt にブロックワードが含まれています")

    with get_session() as session:
        t = session.get(Template, template_id)
        if not t:
            return None
        for k, v in sanitized.items():
            setattr(t, k, v)
        session.commit()
        session.refresh(t)
        return t


def archive_template(template_id: int) -> bool:
    with get_session() as session:
        t = session.get(Template, template_id)
        if not t:
            return False
        t.is_archived = True
        session.commit()
        return True
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_templates.py -v`
Expected: 6 PASS

- [ ] **Step 5: コミット**

```bash
git add core/templates.py tests/test_templates.py
git commit -m "feat(video-ad-generator): add templates CRUD logic"
```

---

## Task 13: Templates API ルーター

**Files:**
- Create: `api/templates.py`
- Create: `tests/test_api_templates.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_api_templates.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from database import Base


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    from main import app
    return TestClient(app)


def test_create_template(client):
    resp = client.post("/api/templates", json={
        "name": "T1", "category": "custom",
        "image_prompt": "img", "video_prompt": "vid",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
    })
    assert resp.status_code == 201
    assert resp.json()["id"] > 0


def test_list_templates(client):
    client.post("/api/templates", json={
        "name": "T1", "category": "custom",
        "image_prompt": "img", "video_prompt": "vid",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
    })
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["name"] == "T1" for t in data)


def test_blocked_word_returns_400(client):
    resp = client.post("/api/templates", json={
        "name": "bad", "category": "custom",
        "image_prompt": "aragaki yui",
        "video_prompt": "vid",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
    })
    assert resp.status_code == 400


def test_update_template(client):
    cid = client.post("/api/templates", json={
        "name": "T1", "category": "custom",
        "image_prompt": "img", "video_prompt": "vid",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
    }).json()["id"]
    resp = client.patch(f"/api/templates/{cid}", json={"name": "T2"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "T2"


def test_archive_template(client):
    cid = client.post("/api/templates", json={
        "name": "T1", "category": "custom",
        "image_prompt": "img", "video_prompt": "vid",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
    }).json()["id"]
    resp = client.delete(f"/api/templates/{cid}")
    assert resp.status_code == 204
    listed = client.get("/api/templates").json()
    assert all(t["id"] != cid for t in listed)
    listed_all = client.get("/api/templates?include_archived=true").json()
    assert any(t["id"] == cid for t in listed_all)
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_api_templates.py -v`
Expected: FAIL（ルーターが未登録のため 404）

- [ ] **Step 3: api/templates.py 実装**

```python
"""テンプレート CRUD API。"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from core import templates as tmpl

router = APIRouter(prefix="/api/templates")


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field("custom", max_length=50)
    image_prompt: str = Field(..., min_length=1, max_length=2000)
    video_prompt: str = Field(..., min_length=1, max_length=2000)
    default_provider: str = "seedance"
    default_aspect: str = "9:16"
    default_duration: int = 10
    default_camera_preset: str | None = None


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    default_provider: str | None = None
    default_aspect: str | None = None
    default_duration: int | None = None
    default_camera_preset: str | None = None


def _to_dict(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "category": t.category,
        "image_prompt": t.image_prompt,
        "video_prompt": t.video_prompt,
        "default_provider": t.default_provider,
        "default_aspect": t.default_aspect,
        "default_duration": t.default_duration,
        "default_camera_preset": t.default_camera_preset,
        "is_archived": t.is_archived,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template(req: TemplateCreateRequest):
    try:
        t = tmpl.create_template(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_dict(t)


@router.get("")
def list_templates(category: str | None = None, include_archived: bool = False):
    items = tmpl.list_templates(category=category, include_archived=include_archived)
    return [_to_dict(t) for t in items]


@router.get("/{template_id}")
def get_template(template_id: int):
    t = tmpl.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_dict(t)


@router.patch("/{template_id}")
def update_template(template_id: int, req: TemplateUpdateRequest):
    try:
        t = tmpl.update_template(template_id, **req.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_dict(t)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int):
    if not tmpl.archive_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return None
```

- [ ] **Step 4: main.py にルーターを登録**

`main.py` の `from api.jobs import router as jobs_router` の下に追加:

```python
from api.templates import router as templates_router
```

そして `app.include_router(jobs_router)` の下に追加:

```python
app.include_router(templates_router)
```

- [ ] **Step 5: テスト成功確認**

Run: `pytest tests/test_api_templates.py -v`
Expected: 5 PASS

- [ ] **Step 6: コミット**

```bash
git add api/templates.py main.py tests/test_api_templates.py
git commit -m "feat(video-ad-generator): add templates CRUD REST API"
```

---

## Task 14: 画像アップロード API

**Files:**
- Create: `api/upload.py`
- Create: `tests/test_api_upload.py`
- Modify: `config.py`（`UPLOADED_DIR` 定数を追加）
- Modify: `main.py`（ルーター登録）

- [ ] **Step 1: config.py に UPLOADED_DIR を追加**

`config.py` の `VIDEOS_DIR = OUTPUT_DIR / "videos"` の下に追加:

```python
UPLOADED_DIR = OUTPUT_DIR / "uploaded"
MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "20"))
```

- [ ] **Step 2: 失敗テストを書く**

`tests/test_api_upload.py`:

```python
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("config.DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("config.UPLOADED_DIR", tmp_path / "uploaded")
    monkeypatch.setattr("config.PENDING_DIR", tmp_path / "pending")
    (tmp_path / "uploaded").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pending").mkdir(parents=True, exist_ok=True)
    from sqlalchemy import create_engine
    from database import Base
    Base.metadata.create_all(create_engine(f"sqlite:///{tmp_path / 'test.db'}"))

    from main import app
    return TestClient(app)


def _png_bytes(width=512, height=512) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_upload_creates_job(client):
    files = {"file": ("test.png", _png_bytes(), "image/png")}
    data = {
        "video_prompt": "test motion",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] > 0
    assert body["status"] == "PENDING"


def test_upload_rejects_unsupported_extension(client):
    files = {"file": ("evil.exe", b"x", "application/octet-stream")}
    data = {
        "video_prompt": "x", "provider": "seedance",
        "aspect_ratio": "9:16", "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 400
    assert "jpg" in resp.json()["detail"]


def test_upload_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr("config.MAX_UPLOAD_SIZE_MB", 1)
    big = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024)
    files = {"file": ("big.png", big, "image/png")}
    data = {
        "video_prompt": "x", "provider": "seedance",
        "aspect_ratio": "9:16", "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 413


def test_upload_rejects_too_small_resolution(client):
    files = {"file": ("tiny.png", _png_bytes(width=100, height=100), "image/png")}
    data = {
        "video_prompt": "x", "provider": "seedance",
        "aspect_ratio": "9:16", "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 400
    assert "解像度" in resp.json()["detail"]


def test_upload_blocked_prompt(client):
    files = {"file": ("test.png", _png_bytes(), "image/png")}
    data = {
        "video_prompt": "video of aragaki yui smiling",
        "provider": "seedance",
        "aspect_ratio": "9:16", "duration_seconds": "10",
    }
    resp = client.post("/api/upload-image", files=files, data=data)
    assert resp.status_code == 400
```

- [ ] **Step 3: テスト失敗確認**

Run: `pytest tests/test_api_upload.py -v`
Expected: FAIL（ルーターなし）

- [ ] **Step 4: api/upload.py 実装**

```python
"""画像アップロード API。"""
from __future__ import annotations
import io
import logging
from pathlib import Path
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from database import get_session, Job, JobStatus
from core.safety import is_blocked
from config import UPLOADED_DIR, MAX_UPLOAD_SIZE_MB

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIME = {"image/jpeg", "image/png"}
MIN_DIM = 256
MAX_DIM = 4096


@router.post("/upload-image", status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    video_prompt: str = Form(...),
    provider: str = Form(...),
    aspect_ratio: str = Form(...),
    duration_seconds: int = Form(...),
    camera_preset: str | None = Form(None),
    template_id: int | None = Form(None),
):
    # 拡張子チェック
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="対応形式は jpg/png のみ")

    # MIME チェック
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="画像ファイルではありません")

    # サイズチェック
    content = await file.read()
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"画像が大きすぎます（最大{MAX_UPLOAD_SIZE_MB}MB）")

    # 中身検証 + 解像度チェック
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))  # verify は close するため再open
    except Exception:
        raise HTTPException(status_code=400, detail="画像ファイルではありません")

    if img.width < MIN_DIM or img.height < MIN_DIM:
        raise HTTPException(status_code=400, detail=f"解像度は{MIN_DIM}〜{MAX_DIM}pxの範囲")
    if img.width > MAX_DIM or img.height > MAX_DIM:
        raise HTTPException(status_code=400, detail=f"解像度は{MIN_DIM}〜{MAX_DIM}pxの範囲")

    # プロンプト安全性
    if is_blocked(video_prompt):
        raise HTTPException(status_code=400, detail="プロンプトにブロックワードが含まれています")

    # ジョブ作成
    with get_session() as session:
        job = Job(
            template_id=template_id,
            prompt=video_prompt,
            provider=provider,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            camera_preset=camera_preset,
            image_source="uploaded",
            status=JobStatus.PENDING,
            image_cost_usd=0.0,
        )
        session.add(job)
        session.flush()
        job_id = job.id

        # ファイル保存
        UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
        save_path = UPLOADED_DIR / f"job_{job_id}{ext}"
        save_path.write_bytes(content)
        job.image_path = str(save_path)
        session.commit()

    return {"job_id": job_id, "status": "PENDING", "image_path": str(save_path)}
```

- [ ] **Step 5: main.py にルーター登録**

`from api.templates import router as templates_router` の下に:

```python
from api.upload import router as upload_router
```

`app.include_router(templates_router)` の下に:

```python
app.include_router(upload_router)
```

- [ ] **Step 6: テスト成功確認**

Run: `pytest tests/test_api_upload.py -v`
Expected: 5 PASS

- [ ] **Step 7: コミット**

```bash
git add api/upload.py config.py main.py tests/test_api_upload.py
git commit -m "feat(video-ad-generator): add image upload API with validation"
```

---

## Task 15: Generate API 拡張

**Files:**
- Modify: `api/generate.py`
- Create: `tests/test_api_generate_extended.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_api_generate_extended.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from database import Base


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("config.DB_PATH", tmp_path / "test.db")
    Base.metadata.create_all(create_engine(f"sqlite:///{tmp_path / 'test.db'}"))
    from main import app
    return TestClient(app)


def test_generate_image_with_extended_params(client, monkeypatch):
    captured = {}
    async def fake_image_gen(prompt, output_path):
        captured["prompt"] = prompt
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake")

    monkeypatch.setattr("api.generate.generate_image", fake_image_gen)

    resp = client.post("/api/generate/image", json={
        "image_prompt": "Portrait of a fictional character",
        "video_prompt": "she smiles",
        "provider": "kling3_pro",
        "aspect_ratio": "1:1",
        "duration_seconds": 5,
        "camera_preset": "dolly_in",
        "image_source": "generated",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    job_id = body["job_id"]

    from database import get_session, Job
    with get_session() as session:
        job = session.get(Job, job_id)
        assert job.provider == "kling3_pro"
        assert job.aspect_ratio == "1:1"
        assert job.duration_seconds == 5
        assert job.camera_preset == "dolly_in"
        assert job.image_source == "generated"


def test_generate_image_with_template_id(client, monkeypatch):
    async def fake_image_gen(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake")
    monkeypatch.setattr("api.generate.generate_image", fake_image_gen)

    # まずテンプレ作成
    cid = client.post("/api/templates", json={
        "name": "T1", "category": "custom",
        "image_prompt": "img", "video_prompt": "vid",
        "default_provider": "veo3_lite", "default_aspect": "16:9",
        "default_duration": 6, "default_camera_preset": "pan_left",
    }).json()["id"]

    resp = client.post("/api/generate/image", json={"template_id": cid})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    from database import get_session, Job
    with get_session() as session:
        job = session.get(Job, job_id)
        assert job.template_id == cid
        assert job.provider == "veo3_lite"
        assert job.aspect_ratio == "16:9"
        assert job.duration_seconds == 6
        assert job.camera_preset == "pan_left"


def test_generate_image_blocked_prompt(client):
    resp = client.post("/api/generate/image", json={
        "image_prompt": "aragaki yui",
        "video_prompt": "v",
        "provider": "seedance",
        "aspect_ratio": "9:16",
        "duration_seconds": 10,
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_api_generate_extended.py -v`
Expected: FAIL（既存 SingleGenerateRequest が新パラメータを受けない）

- [ ] **Step 3: api/generate.py を拡張**

`api/generate.py` の `SingleGenerateRequest` クラスと `generate_single_image` 関数を以下に置き換える（`generate_batch` と `_run_batch_image_gen` は維持）:

```python
"""画像・動画生成トリガー API。"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from database import get_session, Job, JobStatus, Template
from core.patterns import get_batch_prompts, PATTERNS
from core.safety import is_blocked
from core.image_gen import generate_image
from core.notifier import notify_images_ready
from config import PENDING_DIR

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class SingleGenerateRequest(BaseModel):
    # 既存（後方互換）
    pattern: str | None = None
    custom_prompt: str | None = None
    # 新規
    template_id: int | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    provider: str | None = None
    aspect_ratio: str | None = None
    duration_seconds: int | None = None
    camera_preset: str | None = None
    image_source: str = "generated"


@router.post("/generate/batch")
async def generate_batch(background_tasks: BackgroundTasks):
    prompts = get_batch_prompts()
    job_ids = []
    with get_session() as session:
        for item in prompts:
            job = Job(
                pattern=item["pattern"],
                prompt=item["video_prompt"],
                provider="seedance",
                aspect_ratio="9:16",
                duration_seconds=10,
                camera_preset=None,
                image_source="generated",
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
    # 入力解決優先順位:
    # 1. template_id があればテンプレを引いてデフォルトを埋める
    # 2. pattern があれば既存PATTERNS（後方互換）
    # 3. それ以外は明示パラメータを使う
    image_prompt: str | None = None
    video_prompt: str | None = None
    provider = req.provider or "seedance"
    aspect_ratio = req.aspect_ratio or "9:16"
    duration_seconds = req.duration_seconds or 10
    camera_preset = req.camera_preset
    template_id = req.template_id

    if req.template_id is not None:
        with get_session() as session:
            tmpl = session.get(Template, req.template_id)
            if not tmpl:
                raise HTTPException(status_code=404, detail="Template not found")
            image_prompt = req.image_prompt or tmpl.image_prompt
            video_prompt = req.video_prompt or tmpl.video_prompt
            provider = req.provider or tmpl.default_provider
            aspect_ratio = req.aspect_ratio or tmpl.default_aspect
            duration_seconds = req.duration_seconds or tmpl.default_duration
            camera_preset = req.camera_preset or tmpl.default_camera_preset
    elif req.pattern is not None:
        if req.pattern not in PATTERNS:
            raise HTTPException(status_code=400, detail=f"Invalid pattern: {req.pattern}")
        pattern = PATTERNS[req.pattern]
        image_prompt = req.custom_prompt or req.image_prompt or pattern["image_prompt"]
        video_prompt = req.video_prompt or pattern["video_prompt"]
    else:
        image_prompt = req.image_prompt
        video_prompt = req.video_prompt
        if not image_prompt or not video_prompt:
            raise HTTPException(status_code=400, detail="image_prompt と video_prompt が必要です")

    if is_blocked(image_prompt) or is_blocked(video_prompt):
        raise HTTPException(status_code=400, detail="プロンプトにブロックワードが含まれています")

    with get_session() as session:
        job = Job(
            pattern=req.pattern,
            template_id=template_id,
            prompt=video_prompt,
            provider=provider,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            camera_preset=camera_preset,
            image_source=req.image_source,
            status=JobStatus.PENDING,
        )
        session.add(job)
        session.flush()
        job_id = job.id
        session.commit()

    background_tasks.add_task(_run_single_image_gen, job_id, image_prompt)
    return {"status": "started", "job_id": job_id}


async def _run_batch_image_gen(job_ids: list[tuple[int, str, str]]):
    successful = 0
    for job_id, image_prompt, _ in job_ids:
        output_path = PENDING_DIR / f"job_{job_id}.jpg"
        try:
            await generate_image(prompt=image_prompt, output_path=output_path)
            with get_session() as session:
                job = session.get(Job, job_id)
                if job:
                    job.image_path = str(output_path)
                    session.commit()
            successful += 1
        except Exception as e:
            logger.error(f"Job {job_id} 画像生成失敗: {e}")
            with get_session() as session:
                job = session.get(Job, job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)[:1000]
                    session.commit()
        await asyncio.sleep(2.0)

    await notify_images_ready(successful)


async def _run_single_image_gen(job_id: int, image_prompt: str):
    output_path = PENDING_DIR / f"job_{job_id}.jpg"
    try:
        await generate_image(prompt=image_prompt, output_path=output_path)
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.image_path = str(output_path)
                session.commit()
    except Exception as e:
        logger.error(f"Job {job_id} 画像生成失敗: {e}")
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
                session.commit()
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_api_generate_extended.py tests/test_api.py -v`
Expected: 全 PASS（既存 test_api も含めて）

- [ ] **Step 5: コミット**

```bash
git add api/generate.py tests/test_api_generate_extended.py
git commit -m "feat(video-ad-generator): extend /api/generate/image with provider/template params"
```

---

## Task 16: Approve API のプロバイダー動的選択

**Files:**
- Modify: `api/approve.py`

- [ ] **Step 1: 既存テスト test_api.py で _run_video_gen に注目した部分を確認**

Run: `grep -n "_run_video_gen\|generate_video\|approve" tests/test_api.py | head -20`

`_run_video_gen` をモックしているテストがあれば、関数シグネチャ変更で壊れないように注意する。

- [ ] **Step 2: api/approve.py を書き換え（プロバイダー動的選択 + 進捗段階更新）**

```python
"""承認・却下 API。"""
from __future__ import annotations
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import get_session, Job, JobStatus
from config import PENDING_DIR, APPROVED_DIR, REJECTED_DIR, VIDEOS_DIR
from core.video_providers import get_provider, VideoGenRequest
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

        # アップロード画像はファイル移動しない（uploaded フォルダ維持）
        if job.image_source == "generated" and job.image_path:
            src = Path(job.image_path)
            dst = APPROVED_DIR / src.name
            if src.exists():
                src.rename(dst)
            job.image_path = str(dst)

        session.commit()
        snap = {
            "id": job.id,
            "image_path": job.image_path,
            "video_prompt": job.prompt,
            "provider": job.provider,
            "aspect_ratio": job.aspect_ratio,
            "duration_seconds": job.duration_seconds,
            "camera_preset": job.camera_preset,
            "pattern": job.pattern,
        }

    background_tasks.add_task(_run_video_gen, snap)
    return {"status": "approved", "job_id": job_id}


@router.post("/reject/{job_id}")
def reject_job(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job or job.status != JobStatus.PENDING:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        job.status = JobStatus.REJECTED
        if job.image_path and job.image_source == "generated":
            src = Path(job.image_path)
            dst = REJECTED_DIR / src.name
            if src.exists():
                src.rename(dst)
            job.image_path = str(dst)
        session.commit()
    return {"status": "rejected", "job_id": job_id}


def _set_stage(job_id: int, stage: str | None) -> None:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.video_progress_stage = stage
            session.commit()


async def _run_video_gen(snap: dict):
    job_id = snap["id"]
    output_path = VIDEOS_DIR / f"job_{job_id}.mp4"

    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.VIDEO_GENERATING
            job.video_progress_stage = "submitting"
            session.commit()

    try:
        provider = get_provider(snap["provider"])
        req = VideoGenRequest(
            image_path=Path(snap["image_path"]),
            video_prompt=snap["video_prompt"],
            aspect_ratio=snap["aspect_ratio"],
            duration_seconds=snap["duration_seconds"],
            camera_preset=snap["camera_preset"],
            output_path=output_path,
        )
        provider.validate(req)
        cost = provider.calc_cost(req)

        _set_stage(job_id, "uploading_image")
        await provider.generate(req)
        _set_stage(job_id, None)

        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.DONE
                job.video_path = str(output_path)
                job.video_cost_usd = cost
                job.video_cost_calc_basis = (
                    "per_second" if snap["provider"] == "veo3_lite" else "per_video"
                )
                session.commit()
                pattern_or_provider = snap.get("pattern") or snap["provider"]
                await notify_video_done(pattern_or_provider, job_id)
    except Exception as e:
        logger.error(f"Job {job_id} 動画生成失敗: {e}")
        stage = None
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                stage = job.video_progress_stage
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
                session.commit()
        await notify_job_failed(job_id, f"[{stage or 'unknown'}] {e}")
```

- [ ] **Step 3: 既存テスト確認**

Run: `pytest tests/test_api.py -v`
Expected: PASS（既存挙動を維持）

- [ ] **Step 4: コミット**

```bash
git add api/approve.py
git commit -m "feat(video-ad-generator): approve uses provider factory + tracks stage"
```

---

## Task 17: Cost Summary API

**Files:**
- Modify: `api/jobs.py`
- Create: `tests/test_api_jobs_cost.py`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_api_jobs_cost.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from database import Base, Job, JobStatus, get_session


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("config.DB_PATH", tmp_path / "test.db")
    Base.metadata.create_all(create_engine(f"sqlite:///{tmp_path / 'test.db'}"))
    from main import app
    return TestClient(app)


def _add_job(provider: str, cost: float):
    with get_session() as session:
        j = Job(
            prompt="x", provider=provider,
            aspect_ratio="9:16", duration_seconds=10,
            image_source="generated", status=JobStatus.DONE,
            image_cost_usd=0.02, video_cost_usd=cost,
        )
        session.add(j)
        session.commit()


def test_cost_summary_aggregates_by_provider(client):
    _add_job("seedance", 0.81)
    _add_job("seedance", 0.81)
    _add_job("veo3_lite", 0.40)
    _add_job("kling3_pro", 0.46)

    resp = client.get("/api/jobs/cost-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_video_cost_usd"] == pytest.approx(2.48, abs=0.01)
    by_provider = {p["provider"]: p for p in data["by_provider"]}
    assert by_provider["seedance"]["count"] == 2
    assert by_provider["seedance"]["total_usd"] == pytest.approx(1.62, abs=0.01)
    assert by_provider["veo3_lite"]["count"] == 1
    assert by_provider["kling3_pro"]["count"] == 1


def test_cost_summary_date_filter(client):
    _add_job("seedance", 0.81)
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    resp = client.get(f"/api/jobs/cost-summary?from={today}&to={today}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_video_cost_usd"] >= 0.81
```

- [ ] **Step 2: テスト失敗確認**

Run: `pytest tests/test_api_jobs_cost.py -v`
Expected: FAIL（エンドポイントなし）

- [ ] **Step 3: api/jobs.py を拡張**

`api/jobs.py` の末尾に追加し、`_job_to_dict` を新列対応に拡張:

```python
@router.get("/jobs/cost-summary")
def cost_summary(from_: str | None = None, to: str | None = None):
    """期間内の動画コストを provider 別に集計する。
    from / to は YYYY-MM-DD 形式。省略時は全期間。
    """
    from datetime import datetime
    from sqlalchemy import func
    with get_session() as session:
        q = session.query(
            Job.provider, func.count(Job.id), func.sum(Job.video_cost_usd)
        ).group_by(Job.provider)
        if from_:
            from_dt = datetime.fromisoformat(from_)
            q = q.filter(Job.created_at >= from_dt)
        if to:
            to_dt = datetime.fromisoformat(to + " 23:59:59" if "T" not in to else to)
            q = q.filter(Job.created_at <= to_dt)
        rows = q.all()

    by_provider = [
        {"provider": p or "unknown", "count": c, "total_usd": round(s or 0.0, 4)}
        for p, c, s in rows
    ]
    total = round(sum(p["total_usd"] for p in by_provider), 4)
    return {
        "total_video_cost_usd": total,
        "by_provider": by_provider,
        "note": "概算値です。muapi.ai ダッシュボードで実額を確認してください。",
    }
```

そして `_job_to_dict` を以下に置き換え:

```python
def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "pattern": job.pattern,
        "template_id": job.template_id,
        "provider": job.provider,
        "aspect_ratio": job.aspect_ratio,
        "duration_seconds": job.duration_seconds,
        "camera_preset": job.camera_preset,
        "image_source": job.image_source,
        "status": job.status,
        "image_path": job.image_path,
        "video_path": job.video_path,
        "image_cost_usd": job.image_cost_usd,
        "video_cost_usd": job.video_cost_usd,
        "video_cost_calc_basis": job.video_cost_calc_basis,
        "video_progress_stage": job.video_progress_stage,
        "auto_score": job.auto_score,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
```

**注**: FastAPI のクエリパラメータで `from` は予約語なので Python 関数引数として `from_` を受け、エイリアスで対応。実際は `Query(..., alias="from")` を使う必要がある:

```python
from fastapi import Query

@router.get("/jobs/cost-summary")
def cost_summary(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
):
```

- [ ] **Step 4: テスト成功確認**

Run: `pytest tests/test_api_jobs_cost.py -v`
Expected: 2 PASS

- [ ] **Step 5: コミット**

```bash
git add api/jobs.py tests/test_api_jobs_cost.py
git commit -m "feat(video-ad-generator): add /api/jobs/cost-summary endpoint"
```

---

## Task 18: Config と .env 整理

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `conftest.py`

- [ ] **Step 1: config.py に新キー追加**

`config.py` の末尾に追加:

```python
# Veo 3.1 Lite (Gemini API)
VEO3_MODEL_ID: str = os.environ.get("VEO3_MODEL_ID", "veo-3.1-fast-generate-001")

# Kling V3.0 Pro (muapi.ai)
MUAPI_KLING_MODEL_ID: str = os.environ.get("MUAPI_KLING_MODEL_ID", "kling-v3-pro")
MUAPI_KLING_I2V_URL: str = os.environ.get(
    "MUAPI_KLING_I2V_URL", "https://api.muapi.ai/api/v1/kling-v3-pro-i2v"
)

# UI/Defaults
DEFAULT_PROVIDER: str = os.environ.get("DEFAULT_PROVIDER", "seedance")
```

- [ ] **Step 2: .env.example を更新**

`.env.example` の末尾に追加（既存キーは触らない）:

```
# Veo 3.1 Lite (Gemini API directly)
VEO3_MODEL_ID=veo-3.1-fast-generate-001

# Kling V3.0 Pro (via muapi.ai)
MUAPI_KLING_MODEL_ID=kling-v3-pro
MUAPI_KLING_I2V_URL=https://api.muapi.ai/api/v1/kling-v3-pro-i2v

# UI defaults
DEFAULT_PROVIDER=seedance
MAX_UPLOAD_SIZE_MB=20
```

- [ ] **Step 3: conftest.py にテスト用ダミーキーを追加**

`conftest.py` の最後の行（`collect_ignore = ...`）の前に追加:

```python
os.environ.setdefault("MUAPI_KLING_MODEL_ID", "test-kling")
os.environ.setdefault("MUAPI_KLING_I2V_URL", "https://example.test/kling")
os.environ.setdefault("VEO3_MODEL_ID", "test-veo3")
```

- [ ] **Step 4: 全テストが通るか確認**

Run: `pytest -v`
Expected: 既存追加すべてのテストが PASS

- [ ] **Step 5: コミット**

```bash
git add config.py .env.example conftest.py
git commit -m "chore(video-ad-generator): add provider env vars to config and example"
```

---

## Task 19: UI - 動画作成タブと API 接続

**Files:**
- Modify: `static/index.html`

UI は手動テスト前提。HTML/JS のみ。サーバー起動して動作確認する。

- [ ] **Step 1: 既存 index.html を確認**

Run: `wc -l static/index.html && head -30 static/index.html`

既存構造（タブ構成・スタイル）を踏襲し、「動画作成」タブを書き換え＋「テンプレ管理」リンクを追加する形。

- [ ] **Step 2: index.html の「動画作成」/「都度生成」タブ部分を以下フォームに置き換え**

`static/index.html` の該当タブ部分を以下に置き換える（既存タブ枠組みは維持し、タブ内の form 要素のみ書き換え）。タブ名も「動画作成」にする。

```html
<div id="tab-create" class="tab-content">
  <h2>動画作成</h2>

  <fieldset>
    <legend>入力モード</legend>
    <label><input type="radio" name="mode" value="template" checked> テンプレから選ぶ</label>
    <label><input type="radio" name="mode" value="custom"> 自由入力</label>
  </fieldset>

  <div id="mode-template">
    <label>カテゴリ:
      <select id="tmpl-category">
        <option value="">すべて</option>
        <option value="matching_ad">マッチング広告</option>
        <option value="custom">カスタム</option>
      </select>
    </label>
    <label>テンプレ:
      <select id="tmpl-select"></select>
    </label>
  </div>

  <div id="mode-custom" style="display:none;">
    <label>画像プロンプト:
      <textarea id="image-prompt" rows="3" cols="60"></textarea>
    </label>
    <label>動画プロンプト:
      <textarea id="video-prompt" rows="3" cols="60"></textarea>
    </label>
  </div>

  <fieldset>
    <legend>画像ソース</legend>
    <label><input type="radio" name="image-source" value="generated" checked> NanoBanana で生成</label>
    <label><input type="radio" name="image-source" value="uploaded"> 既存画像をアップロード</label>
    <input type="file" id="image-file" accept="image/png,image/jpeg" style="display:none;">
  </fieldset>

  <fieldset>
    <legend>動画パラメータ</legend>
    <label>モデル:
      <select id="provider">
        <option value="seedance">Seedance 2.0</option>
        <option value="veo3_lite">Veo 3.1 Lite</option>
        <option value="kling3_pro">Kling V3.0 Pro</option>
      </select>
    </label>
    <label>アスペクト比:
      <select id="aspect-ratio"></select>
    </label>
    <label>長さ:
      <select id="duration"></select>
    </label>
    <label>カメラ動作:
      <select id="camera-preset">
        <option value="">なし</option>
        <option value="static">固定</option>
        <option value="dolly_in">ドリーイン</option>
        <option value="dolly_out">ドリーアウト</option>
        <option value="pan_left">左パン</option>
        <option value="pan_right">右パン</option>
        <option value="tilt_up">上ティルト</option>
        <option value="orbit_left">左オービット</option>
      </select>
    </label>
  </fieldset>

  <button id="btn-create">動画作成を開始</button>
  <p id="create-result"></p>

  <p><a href="/static/templates.html">→ テンプレ管理</a></p>
</div>

<script>
const PROVIDER_SUPPORT = {
  seedance:   { aspects: ["9:16","16:9"], durations: [5,10] },
  veo3_lite:  { aspects: ["9:16","16:9"], durations: [4,6,8] },
  kling3_pro: { aspects: ["9:16","16:9","1:1"], durations: [5,10] },
};

function refreshProviderOptions() {
  const p = document.getElementById("provider").value;
  const aspectSel = document.getElementById("aspect-ratio");
  const durSel = document.getElementById("duration");
  aspectSel.innerHTML = PROVIDER_SUPPORT[p].aspects.map(a => `<option value="${a}">${a}</option>`).join("");
  durSel.innerHTML = PROVIDER_SUPPORT[p].durations.map(d => `<option value="${d}">${d}秒</option>`).join("");
}

async function refreshTemplates() {
  const cat = document.getElementById("tmpl-category").value;
  const url = "/api/templates" + (cat ? `?category=${cat}` : "");
  const items = await fetch(url).then(r => r.json());
  const sel = document.getElementById("tmpl-select");
  sel.innerHTML = items.map(t => `<option value="${t.id}">${t.name} (${t.category})</option>`).join("");
}

document.querySelectorAll('input[name="mode"]').forEach(r => {
  r.addEventListener("change", () => {
    document.getElementById("mode-template").style.display = r.value === "template" ? "" : "none";
    document.getElementById("mode-custom").style.display = r.value === "custom" ? "" : "none";
  });
});

document.querySelectorAll('input[name="image-source"]').forEach(r => {
  r.addEventListener("change", () => {
    document.getElementById("image-file").style.display = r.value === "uploaded" ? "" : "none";
  });
});

document.getElementById("provider").addEventListener("change", refreshProviderOptions);
document.getElementById("tmpl-category").addEventListener("change", refreshTemplates);

document.getElementById("btn-create").addEventListener("click", async () => {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const imageSource = document.querySelector('input[name="image-source"]:checked').value;
  const provider = document.getElementById("provider").value;
  const aspect = document.getElementById("aspect-ratio").value;
  const duration = parseInt(document.getElementById("duration").value, 10);
  const cameraPreset = document.getElementById("camera-preset").value || null;

  const result = document.getElementById("create-result");
  result.textContent = "送信中...";

  try {
    if (imageSource === "uploaded") {
      const file = document.getElementById("image-file").files[0];
      if (!file) throw new Error("画像ファイルを選択してください");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("video_prompt", document.getElementById("video-prompt").value);
      fd.append("provider", provider);
      fd.append("aspect_ratio", aspect);
      fd.append("duration_seconds", duration);
      if (cameraPreset) fd.append("camera_preset", cameraPreset);
      const resp = await fetch("/api/upload-image", { method: "POST", body: fd });
      if (!resp.ok) throw new Error(await resp.text());
      result.textContent = `アップロード完了: Job #${(await resp.json()).job_id}`;
    } else {
      const body = mode === "template"
        ? { template_id: parseInt(document.getElementById("tmpl-select").value, 10),
            provider, aspect_ratio: aspect, duration_seconds: duration, camera_preset: cameraPreset }
        : { image_prompt: document.getElementById("image-prompt").value,
            video_prompt: document.getElementById("video-prompt").value,
            provider, aspect_ratio: aspect, duration_seconds: duration, camera_preset: cameraPreset };
      const resp = await fetch("/api/generate/image", {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await resp.text());
      result.textContent = `生成開始: Job #${(await resp.json()).job_id}`;
    }
  } catch (e) {
    result.textContent = `エラー: ${e.message}`;
  }
});

refreshProviderOptions();
refreshTemplates();
</script>
```

- [ ] **Step 3: サーバー起動して目視確認**

Run: `python main.py &` （または既存の起動方法）
ブラウザで `http://localhost:8004/` を開く。

確認項目:
- 「動画作成」タブが表示される
- モデル切替で aspect/duration オプションが動的に変わる
- テンプレモード/自由入力モードのトグルが動作する
- 既存テンプレ5件がドロップダウンに表示される
- アップロードラジオで input[type=file] が表示される

問題があれば修正してから次へ。

- [ ] **Step 4: コミット**

```bash
git add static/index.html
git commit -m "feat(video-ad-generator): extend index.html with create form"
```

---

## Task 20: UI - テンプレ管理画面

**Files:**
- Create: `static/templates.html`

- [ ] **Step 1: templates.html を作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>テンプレ管理</title>
  <style>
    body { font-family: sans-serif; max-width: 1000px; margin: 20px auto; padding: 0 20px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
    .archived { opacity: 0.5; }
    .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
    .modal-body { background: white; max-width: 600px; margin: 50px auto; padding: 20px; }
    label { display: block; margin: 8px 0; }
    textarea { width: 100%; min-height: 60px; }
    button { margin: 4px; }
  </style>
</head>
<body>
  <h1>テンプレ管理</h1>
  <p><a href="/">← トップに戻る</a></p>

  <button id="btn-new">+ 新規作成</button>
  <label><input type="checkbox" id="show-archived"> アーカイブを表示</label>

  <table id="tmpl-table">
    <thead>
      <tr>
        <th>ID</th><th>名前</th><th>カテゴリ</th><th>モデル</th><th>aspect</th><th>長さ</th><th>カメラ</th><th>操作</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <div id="modal" class="modal">
    <div class="modal-body">
      <h2 id="modal-title">テンプレ作成</h2>
      <input type="hidden" id="m-id">
      <label>名前: <input type="text" id="m-name"></label>
      <label>カテゴリ:
        <select id="m-category">
          <option value="custom">custom</option>
          <option value="matching_ad">matching_ad</option>
          <option value="sns_post">sns_post</option>
          <option value="product_showcase">product_showcase</option>
        </select>
      </label>
      <label>画像プロンプト: <textarea id="m-image-prompt"></textarea></label>
      <label>動画プロンプト: <textarea id="m-video-prompt"></textarea></label>
      <label>デフォルトモデル:
        <select id="m-provider">
          <option value="seedance">seedance</option>
          <option value="veo3_lite">veo3_lite</option>
          <option value="kling3_pro">kling3_pro</option>
        </select>
      </label>
      <label>デフォルトaspect:
        <select id="m-aspect"><option>9:16</option><option>16:9</option><option>1:1</option></select>
      </label>
      <label>デフォルト長さ:
        <select id="m-duration"><option>5</option><option>6</option><option>8</option><option>10</option></select>
      </label>
      <label>デフォルトカメラ:
        <select id="m-camera">
          <option value="">（なし）</option>
          <option value="static">static</option>
          <option value="dolly_in">dolly_in</option>
          <option value="dolly_out">dolly_out</option>
          <option value="pan_left">pan_left</option>
          <option value="pan_right">pan_right</option>
          <option value="tilt_up">tilt_up</option>
          <option value="orbit_left">orbit_left</option>
        </select>
      </label>
      <button id="m-save">保存</button>
      <button id="m-cancel">キャンセル</button>
      <p id="m-error" style="color: red;"></p>
    </div>
  </div>

<script>
async function load() {
  const showArchived = document.getElementById("show-archived").checked;
  const items = await fetch(`/api/templates?include_archived=${showArchived}`).then(r => r.json());
  const tbody = document.querySelector("#tmpl-table tbody");
  tbody.innerHTML = items.map(t => `
    <tr class="${t.is_archived ? 'archived' : ''}">
      <td>${t.id}</td>
      <td>${escapeHtml(t.name)}</td>
      <td>${t.category}</td>
      <td>${t.default_provider}</td>
      <td>${t.default_aspect}</td>
      <td>${t.default_duration}s</td>
      <td>${t.default_camera_preset || '-'}</td>
      <td>
        <button onclick="edit(${t.id})">編集</button>
        ${t.is_archived ? '' : `<button onclick="archive(${t.id})">アーカイブ</button>`}
        <button onclick="useFor(${t.id})">→ 動画作成</button>
      </td>
    </tr>
  `).join("");
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function openModal(template) {
  document.getElementById("modal-title").textContent = template ? "テンプレ編集" : "テンプレ作成";
  document.getElementById("m-id").value = template?.id || "";
  document.getElementById("m-name").value = template?.name || "";
  document.getElementById("m-category").value = template?.category || "custom";
  document.getElementById("m-image-prompt").value = template?.image_prompt || "";
  document.getElementById("m-video-prompt").value = template?.video_prompt || "";
  document.getElementById("m-provider").value = template?.default_provider || "seedance";
  document.getElementById("m-aspect").value = template?.default_aspect || "9:16";
  document.getElementById("m-duration").value = template?.default_duration || 10;
  document.getElementById("m-camera").value = template?.default_camera_preset || "";
  document.getElementById("m-error").textContent = "";
  document.getElementById("modal").style.display = "block";
}

document.getElementById("btn-new").addEventListener("click", () => openModal(null));
document.getElementById("m-cancel").addEventListener("click", () => {
  document.getElementById("modal").style.display = "none";
});
document.getElementById("show-archived").addEventListener("change", load);

async function edit(id) {
  const t = await fetch(`/api/templates/${id}`).then(r => r.json());
  openModal(t);
}

async function archive(id) {
  if (!confirm("アーカイブしますか？")) return;
  await fetch(`/api/templates/${id}`, { method: "DELETE" });
  load();
}

function useFor(id) {
  window.location.href = `/?template_id=${id}#tab-create`;
}

document.getElementById("m-save").addEventListener("click", async () => {
  const id = document.getElementById("m-id").value;
  const body = {
    name: document.getElementById("m-name").value,
    category: document.getElementById("m-category").value,
    image_prompt: document.getElementById("m-image-prompt").value,
    video_prompt: document.getElementById("m-video-prompt").value,
    default_provider: document.getElementById("m-provider").value,
    default_aspect: document.getElementById("m-aspect").value,
    default_duration: parseInt(document.getElementById("m-duration").value, 10),
    default_camera_preset: document.getElementById("m-camera").value || null,
  };
  const url = id ? `/api/templates/${id}` : "/api/templates";
  const method = id ? "PATCH" : "POST";
  const resp = await fetch(url, {
    method, headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    document.getElementById("m-error").textContent = await resp.text();
    return;
  }
  document.getElementById("modal").style.display = "none";
  load();
});

load();
</script>
</body>
</html>
```

- [ ] **Step 2: サーバー起動して目視確認**

Run: ブラウザで `http://localhost:8004/static/templates.html` を開く

確認項目:
- 既存5テンプレが表示される
- 新規作成・編集・アーカイブが動作する
- 「→ 動画作成」ボタンで `/?template_id=X#tab-create` に遷移する

- [ ] **Step 3: コミット**

```bash
git add static/templates.html
git commit -m "feat(video-ad-generator): add templates management page"
```

---

## Task 21: 統合スモークテスト + ドキュメント更新

**Files:**
- Modify: `core/notifier.py`（progress_stage 引数の追加は最小限）

- [ ] **Step 1: 全 pytest 実行**

Run: `pytest -v`
Expected: すべて PASS

- [ ] **Step 2: 既存「バッチ生成」が壊れていないか手動確認**

サーバー起動後、ブラウザの「バッチ生成」タブを開いて、ボタンを押す → 5パターン×2本のジョブが PENDING 状態で作成されることを確認。

確認: `python -c "from database import get_session, Job, JobStatus; s=get_session(); print(s.query(Job).filter(Job.status==JobStatus.PENDING).count())"`

Expected: 10 件追加されている。

- [ ] **Step 3: 各プロバイダーで E2E テスト（実 API 呼び出し）**

実際にコストが発生するため、各プロバイダーで **1 本だけ** 実動画生成を試す。

1. **Seedance**: 「動画作成」タブ → テンプレから1つ選択 → モデル `seedance` → 9:16 / 10秒 → カメラ `static` → 作成 → 承認
2. **Veo 3.1 Lite**: 同様にモデル `veo3_lite` → 9:16 / 8秒 → カメラ `pan_left` → 作成 → 承認
3. **Kling V3.0 Pro**: 同様にモデル `kling3_pro` → 1:1 / 5秒 → カメラ `dolly_in` → 作成 → 承認

それぞれ完成動画が `output/videos/job_{id}.mp4` に保存され、`/api/jobs/cost-summary` で provider 別の合計が表示されることを確認。

**注**: Veo 3.1 / Kling は API キー or エンドポイントが正しく設定されているか先に確認する。失敗した場合は失敗ジョブを残し、エラーメッセージを次のフォローアップタスクに記録する。

- [ ] **Step 4: マイグレーションロールバック演習**

Run（実行注意 — 実 DB 用）:

```bash
./migrations/run.sh backup
./migrations/run.sh downgrade
```

Expected: `templates` テーブルが消え、`Job` の新列も消える。

復旧:

```bash
./migrations/run.sh migrate
```

Expected: 再びマイグレーションが適用される。テンプレシードは再度 5 件挿入される（IDは引き継がない）。

- [ ] **Step 5: コミット（ドキュメント更新分があれば）**

E2E で見つかった問題があれば修正してコミット。

```bash
git add -p   # 修正分のみ慎重に staging
git commit -m "fix(video-ad-generator): post-E2E adjustments"
```

問題なければこの Task でコミット不要。

---

## 完成チェックリスト（spec §15 受け入れ基準対応）

- [ ] 既存「バッチ生成」が引き続き動く（Task 21 Step 2 で確認）
- [ ] 「動画作成」タブで自由プロンプト + 自由パラメータで動画を生成できる（Task 19 + Task 21 Step 3）
- [ ] 既存画像のアップロード→動画生成パスが動く（Task 14 + Task 19 + Task 21 Step 3）
- [ ] テンプレを作成・編集・アーカイブできる（Task 12 + Task 13 + Task 20）
- [ ] テンプレから「動画作成」へ pre-fill 遷移できる（Task 19 + Task 20）
- [ ] Seedance / Veo 3.1 Lite / Kling V3.0 Pro の3モデルすべてで動画生成成功（Task 21 Step 3）
- [ ] カメラプリセット 7種が Kling では数値パラメータで、他はプロンプト埋め込みで動作する（Task 4 + Task 8 + Task 11）
- [ ] pytest 全パス、新規追加テストが書かれている（Task 21 Step 1）
- [ ] エラーハンドリング統一仕様が全プロバイダーで実装され、認証/課金エラーで即時失敗・ネットワークエラーでリトライすることをテストで検証（Task 8 / 10 / 11 で各 provider の generate ロジックに統一実装。HTTP モックテストは Phase 1 では不採用、E2E で確認）
- [ ] アップロード API のバリデーションが全パターン実装済み（Task 14 で5バリデーションテスト）
- [ ] `Job.video_progress_stage` がジョブ一覧 UI に表示される（Task 17 で `_job_to_dict` に追加。UI表示は jobs タブ既存実装で自動表示。表示崩れがあれば修正）
- [ ] `GET /api/jobs/cost-summary` が動作し、UI で月次コストが見える（Task 17 + UI 改修は最小限のため、現状は API レベル動作確認のみで Phase 1 完了とする。UI への反映は Phase 1 完了後の追加 Task として残す）
- [ ] `migrations/run.sh` の backup/migrate/rollback が手元で動作確認済み（Task 1 Step 8 + Task 21 Step 4）
- [ ] `.env.example` が新キーで更新されている（Task 18）
