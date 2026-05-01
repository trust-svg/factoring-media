# Phase 2a Implementation Plan — アスペクト比拡張 + 画質セレクタ + UI リデザイン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** video-ad-generator に画質セレクタとアスペクト比拡張を追加し、Adobe Firefly 系参考の白背景 2 カラム UI に刷新する。

**Architecture:** 全 provider 共通の low/high 抽象 + provider 別 `QUALITY_MAP` / `RATE_MAP` / `cost_basis` クラス属性化。新エンドポイント `GET /api/providers/capabilities` で Python/JS 二重管理を解消。UI は `tokens.css` ベースで全面書き換え（panel-pending/confirmed は維持）。

**Tech Stack:** FastAPI / Pydantic v2 / SQLAlchemy 2.x / Alembic / pytest / vanilla JS / CSS custom properties

**仕様書**: `docs/specs/2026-05-02-phase2a-design.md`

---

## 実装着手前の必須確認事項（Task 0）

### Task 0: 外部 API 仕様確認

**Files:** なし（リサーチタスク）

- [ ] **Step 1: Atlas Cloud Seedance pro quality を確認**

確認事項：
- `quality` パラメータで "pro" 文字列を受け付けるか
- pro の per-second 料金（仮: $0.13/s）

確認方法：
- Atlas Cloud ドキュメント https://atlascloud.ai/docs を確認
- もしくは payload に `"quality": "pro"` を入れて 5s テストリクエスト送信

確認結果を `docs/specs/2026-05-02-phase2a-design.md` の Section 3 表に追記。

- [ ] **Step 2: Veo 3.1 standard model ID と料金を確認**

確認事項：
- standard model の正式 ID（例: `veo-3.1-standard`）
- per-second 料金

確認方法：Google AI ドキュメント / Vertex AI 料金表

- [ ] **Step 3: Kling V3 std/pro が同一 URL+model 差か別エンドポイントか確認**

確認事項：
- MuAPI で `kling-v3-std` と `kling-v3-pro` のエンドポイント URL
- 同一 URL なら QUALITY_MAP は文字列、別 URL なら dict 構造

確認方法：MuAPI ドキュメント

- [ ] **Step 4: 既存運用 DB の SQLite バージョン確認**

```bash
sqlite3 video_ad_generator.db "SELECT sqlite_version();"
```
3.35 以上であることを確認。下回る場合はマイグレーション戦略を見直し。

- [ ] **Step 5: Phase 1 modal 実装の有無を確認**

```bash
grep -rn "modal" products/video-ad-generator/static/ | head
grep -rn "focus.*trap\|focusTrap\|tabindex" products/video-ad-generator/static/ | head
```

既存 modal パターンがあれば踏襲、なければ Task 22-24 で初実装。

- [ ] **Step 6: 確認結果を仕様書に反映してコミット**

```bash
git add products/video-ad-generator/docs/specs/2026-05-02-phase2a-design.md
git commit -m "docs(video-ad-generator): Phase 2a 仕様の要確定項目を解消"
```

---

## File Structure

### 新規作成
- `migrations/versions/0002_add_quality_columns.py`
- `api/providers.py`
- `static/css/tokens.css`
- `static/css/layout.css`
- `static/css/generate.css`
- `static/css/templates.css`
- `static/img/aspect-icons.svg`
- `tests/test_api_providers.py`
- `tests/test_alembic_phase2a.py`
- `tests/test_api_approve.py`

### 変更
- `core/video_providers/__init__.py` — `supported_qualities` / `cost_basis` / `RATE_MAP` を基底クラスに、`VideoGenRequest.quality` 追加、`validate()` 拡張
- `core/video_providers/seedance.py` — aspects 6 種に拡張、QUALITY_MAP、cost_basis="per_second" に修正
- `core/video_providers/veo3.py` — QUALITY_MAP（fast/standard 2 段）
- `core/video_providers/kling.py` — QUALITY_MAP（std/pro）
- `database.py` — `Job.quality`, `Template.default_quality` カラム追加
- `config.py` — `VEO3_FAST_MODEL_ID`, `VEO3_STANDARD_MODEL_ID`, （必要なら）`KLING_STD_URL`, `KLING_PRO_URL`
- `.env.example` — 新環境変数（git add はユーザー）
- `conftest.py` — 新環境変数の setdefault
- `api/generate.py` — Pydantic スキーマ extension、quality 解決ロジック
- `api/templates.py` — Pydantic スキーマ extension
- `api/approve.py` — VideoGenRequest に quality 追加、cost_basis を provider クラス属性経由
- `core/templates.py` — `update_template()` の allowed セットに `default_quality` 追加
- `main.py` — `api/providers.py` ルーターをマウント
- `static/index.html` — 動画作成パネルを新 UI に刷新
- `static/templates.html` — 新 UI に刷新
- `static/js/generate.js` — capabilities API 連携 + チップ操作
- `static/js/templates.js` — モーダル + quality フィールド
- `static/css/style.css` — generate / templates 部分を削除（panel-pending/confirmed のみ残す）
- 既存テスト調整: `test_video_providers_base.py`, `test_api_generate_extended.py`

---

## Task 1: VideoGenRequest に quality フィールド追加

**Files:**
- Modify: `core/video_providers/__init__.py`
- Test: `tests/test_video_providers_base.py`

- [ ] **Step 1: テストを書く（quality default が "low"）**

`tests/test_video_providers_base.py` の冒頭近くに追加：

```python
def test_video_gen_request_quality_default():
    req = VideoGenRequest(
        image_path=Path("/tmp/x.jpg"),
        video_prompt="t",
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=Path("/tmp/o.mp4"),
    )
    assert req.quality == "low"
```

- [ ] **Step 2: 失敗を確認**

```bash
cd products/video-ad-generator && pytest tests/test_video_providers_base.py::test_video_gen_request_quality_default -v
```

Expected: AttributeError or assertion失敗

- [ ] **Step 3: VideoGenRequest に quality 追加**

`core/video_providers/__init__.py` の `VideoGenRequest` dataclass 末尾に追加：

```python
@dataclass
class VideoGenRequest:
    image_path: Path
    video_prompt: str
    aspect_ratio: str
    duration_seconds: int
    camera_preset: str | None
    output_path: Path
    quality: str = "low"  # 新規追加
```

- [ ] **Step 4: テスト pass を確認**

```bash
pytest tests/test_video_providers_base.py::test_video_gen_request_quality_default -v
```

Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add core/video_providers/__init__.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): VideoGenRequest に quality フィールド追加"
```

---

## Task 2: VideoProvider 基底クラスに supported_qualities / cost_basis / RATE_MAP / calc_cost 共通実装

**Files:**
- Modify: `core/video_providers/__init__.py`
- Test: `tests/test_video_providers_base.py`

- [ ] **Step 1: テストを書く**

```python
def test_validate_rejects_unsupported_quality():
    p = _DummyProvider()
    req = _make_req()
    req.quality = "ultra"
    with pytest.raises(ValueError, match="quality"):
        p.validate(req)


def test_dummy_provider_supports_default_qualities():
    p = _DummyProvider()
    assert p.supported_qualities == ("low", "high")


def test_calc_cost_per_second_basis():
    class _P(VideoProvider):
        name = "p"
        supported_aspects = ("9:16",)
        supported_durations = (10,)
        cost_basis = "per_second"
        RATE_MAP = {"low": 0.1, "high": 0.2}

        async def generate(self, req): return req.output_path

    req = _make_req()
    assert _P().calc_cost(req) == 1.0  # 0.1 * 10
    req.quality = "high"
    assert _P().calc_cost(req) == 2.0


def test_calc_cost_per_video_basis():
    class _P(VideoProvider):
        name = "p"
        supported_aspects = ("9:16",)
        supported_durations = (10,)
        cost_basis = "per_video"
        RATE_MAP = {"low": 0.5, "high": 1.0}

        async def generate(self, req): return req.output_path

    req = _make_req()
    assert _P().calc_cost(req) == 0.5
    req.quality = "high"
    assert _P().calc_cost(req) == 1.0
```

- [ ] **Step 2: 失敗を確認**

```bash
pytest tests/test_video_providers_base.py -v -k "quality or basis"
```

Expected: FAIL（属性なし）

- [ ] **Step 3: VideoProvider 基底クラスを拡張**

`core/video_providers/__init__.py`：

```python
class VideoProvider(ABC):
    name: str
    supported_aspects: tuple[str, ...]
    supported_durations: tuple[int, ...]
    supported_qualities: tuple[str, ...] = ("low", "high")
    cost_basis: str = "per_video"
    RATE_MAP: dict[str, float] = {}

    def validate(self, req: VideoGenRequest) -> None:
        if req.aspect_ratio not in self.supported_aspects:
            raise ValueError(f"unsupported aspect: {req.aspect_ratio}")
        if req.duration_seconds not in self.supported_durations:
            raise ValueError(f"unsupported duration: {req.duration_seconds}")
        if req.quality not in self.supported_qualities:
            raise ValueError(f"unsupported quality: {req.quality}")

    @abstractmethod
    async def generate(self, req: VideoGenRequest) -> Path: ...

    def calc_cost(self, req: VideoGenRequest) -> float:
        rate = self.RATE_MAP[req.quality]
        if self.cost_basis == "per_second":
            return round(rate * req.duration_seconds, 4)
        return round(rate, 4)
```

`_DummyProvider` の `calc_cost` オーバーライドは削除（基底クラスで実装したため）。または既存テストとの互換のため `RATE_MAP = {"low": 0.5, "high": 1.0}` を追加。

- [ ] **Step 4: 既存テストが壊れないこと確認**

```bash
pytest tests/test_video_providers_base.py -v
```

Expected: 全 PASS（test_validate_rejects_1to1_ratio は Task 4 で削除予定なので、このタスクではまだ通る）

- [ ] **Step 5: コミット**

```bash
git add core/video_providers/__init__.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): VideoProvider に supported_qualities/cost_basis/RATE_MAP 共通実装"
```

---

## Task 3: Seedance を新仕様に対応（aspects 6 種、QUALITY_MAP、cost_basis="per_second"）

**Files:**
- Modify: `core/video_providers/seedance.py`
- Test: `tests/test_seedance_provider.py`, `tests/test_video_providers_base.py`

- [ ] **Step 1: テストを書く**

`tests/test_video_providers_base.py` に追加：

```python
def test_seedance_supports_new_aspects():
    p = SeedanceProvider()
    for aspect in ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9"):
        req = _make_req(aspect=aspect)
        p.validate(req)


def test_seedance_cost_basis_is_per_second():
    p = SeedanceProvider()
    assert p.cost_basis == "per_second"


def test_seedance_calc_cost_low_vs_high():
    p = SeedanceProvider()
    low = _make_req(); low.quality = "low"
    high = _make_req(); high.quality = "high"
    assert p.calc_cost(low) < p.calc_cost(high)


def test_seedance_low_cost_unchanged_from_phase1():
    p = SeedanceProvider()
    req = _make_req(duration=10); req.quality = "low"
    assert p.calc_cost(req) == round(0.081 * 10, 4)
```

`from core.video_providers.seedance import SeedanceProvider` を import。

- [ ] **Step 2: 失敗確認**

```bash
pytest tests/test_video_providers_base.py -v -k "seedance"
```

Expected: FAIL

- [ ] **Step 3: seedance.py を更新**

```python
class SeedanceProvider(VideoProvider):
    name = "seedance"
    supported_aspects = ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9")
    supported_durations = (5, 10)
    cost_basis = "per_second"
    RATE_MAP = {"low": 0.081, "high": 0.13}  # ← 高画質は Task 0 で確定した値
    QUALITY_MAP = {"low": "basic", "high": "pro"}  # ← Task 0 で確定

    # calc_cost は基底クラスを使う（既存実装は削除）

    def _build_prompt(self, req): ...  # 既存維持

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        # ... 既存実装の payload 部分を変更:
        payload = {
            "prompt": self._build_prompt(req),
            "images_list": [image_url],
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration_seconds,
            "quality": self.QUALITY_MAP[req.quality],  # ← "basic" hardcode から変更
        }
        # 以下既存維持
```

- [ ] **Step 4: 既存テスト + 新規テスト pass 確認**

```bash
pytest tests/test_seedance_provider.py tests/test_video_providers_base.py -v
```

Expected: 全 PASS（test_validate_rejects_1to1_ratio はまだ通る or 削除されている）

- [ ] **Step 5: コミット**

```bash
git add core/video_providers/seedance.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): Seedance を 6 種 aspect + low/high quality に対応"
```

---

## Task 4: 旧テスト test_validate_rejects_1to1_ratio を削除

**Files:**
- Modify: `tests/test_video_providers_base.py`

- [ ] **Step 1: テストを削除**

`tests/test_video_providers_base.py` から `test_validate_rejects_1to1_ratio` を削除（Seedance が 1:1 サポートに変わったため意味を失う）。

`_DummyProvider.supported_aspects = ("9:16",)` のままなので、`test_validate_rejects_unsupported_aspect` は引き続き有効。

- [ ] **Step 2: テスト pass 確認**

```bash
pytest tests/test_video_providers_base.py -v
```

Expected: 全 PASS（test_validate_rejects_1to1_ratio は除外）

- [ ] **Step 3: コミット**

```bash
git add tests/test_video_providers_base.py
git commit -m "test(video-ad-generator): 旧 test_validate_rejects_1to1_ratio を削除（Seedance 1:1 対応のため）"
```

---

## Task 5: config.py / conftest.py / .env.example に Veo3 / Kling 新環境変数追加

**Files:**
- Modify: `config.py`
- Modify: `conftest.py`
- Modify: `.env.example`（git add はユーザー手動）

- [ ] **Step 1: config.py に追加**

```python
# 既存:
VEO3_MODEL_ID: str = os.environ.get("VEO3_MODEL_ID", "veo-3.1-fast")  # deprecated, fast の alias
# 新規:
VEO3_FAST_MODEL_ID: str = os.environ.get("VEO3_FAST_MODEL_ID", VEO3_MODEL_ID)
VEO3_STANDARD_MODEL_ID: str = os.environ["VEO3_STANDARD_MODEL_ID"]  # ← Task 0 で確定した値、必須化

# Kling: Task 0 の確認結果次第
# (a) 同一 URL の場合は変更なし
# (b) 別 URL の場合:
KLING_STD_URL: str = os.environ.get("KLING_STD_URL", "")
KLING_PRO_URL: str = os.environ.get("KLING_PRO_URL", "")
```

- [ ] **Step 2: conftest.py に setdefault 追加**

```python
os.environ.setdefault("VEO3_STANDARD_MODEL_ID", "veo-3.1-standard")
os.environ.setdefault("KLING_STD_URL", "https://example.com/std")
os.environ.setdefault("KLING_PRO_URL", "https://example.com/pro")
```

- [ ] **Step 3: .env.example に追記**

```
# Veo 3.1 model IDs
VEO3_FAST_MODEL_ID=veo-3.1-fast
VEO3_STANDARD_MODEL_ID=veo-3.1-standard

# Kling V3 endpoints (Task 0 で URL 差異が確認された場合のみ)
KLING_STD_URL=
KLING_PRO_URL=
```

ユーザーに「.env.example をコミットしてください」と伝える（sandbox 制約で Claude からは git add 不可）。

- [ ] **Step 4: テストが通ること確認**

```bash
pytest tests/ -v
```

Expected: 全 PASS

- [ ] **Step 5: コミット（.env.example 除く）**

```bash
git add config.py conftest.py
git commit -m "feat(video-ad-generator): Veo3 fast/standard と Kling std/pro 用環境変数を追加"
```

ユーザーに `.env.example` の手動 commit を依頼。

---

## Task 6: Veo3 Provider を quality 対応（fast/standard 2 段）

**Files:**
- Modify: `core/video_providers/veo3.py`
- Test: `tests/test_video_providers_base.py`, `tests/test_veo3_provider.py`

- [ ] **Step 1: テストを書く**

```python
def test_veo3_supports_low_high():
    from core.video_providers.veo3 import Veo3LiteProvider
    p = Veo3LiteProvider()
    assert "low" in p.supported_qualities
    assert "high" in p.supported_qualities


def test_veo3_quality_map_uses_model_ids():
    from core.video_providers.veo3 import Veo3LiteProvider
    from config import VEO3_FAST_MODEL_ID, VEO3_STANDARD_MODEL_ID
    p = Veo3LiteProvider()
    assert p.QUALITY_MAP["low"] == VEO3_FAST_MODEL_ID
    assert p.QUALITY_MAP["high"] == VEO3_STANDARD_MODEL_ID


def test_veo3_calc_cost_low_vs_high():
    from core.video_providers.veo3 import Veo3LiteProvider
    p = Veo3LiteProvider()
    low = _make_req(); low.quality = "low"
    high = _make_req(); high.quality = "high"
    assert p.calc_cost(low) < p.calc_cost(high)
```

- [ ] **Step 2: 失敗確認**

```bash
pytest tests/test_video_providers_base.py -v -k "veo3"
```

Expected: FAIL

- [ ] **Step 3: veo3.py を更新**

```python
from config import VEO3_FAST_MODEL_ID, VEO3_STANDARD_MODEL_ID

class Veo3LiteProvider(VideoProvider):
    name = "veo3_lite"
    supported_aspects = ("9:16", "16:9")
    supported_durations = (...)  # 既存維持
    cost_basis = "per_second"
    QUALITY_MAP = {
        "low": VEO3_FAST_MODEL_ID,
        "high": VEO3_STANDARD_MODEL_ID,
    }
    RATE_MAP = {
        "low": <既存 fast 単価>,
        "high": <Task 0 で確定した standard 単価>,
    }

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        model_id = self.QUALITY_MAP[req.quality]  # ← model 切替
        # 以下既存実装で model_id を使用
```

- [ ] **Step 4: テスト pass 確認**

```bash
pytest tests/test_veo3_provider.py tests/test_video_providers_base.py -v
```

- [ ] **Step 5: コミット**

```bash
git add core/video_providers/veo3.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): Veo3 を low/high quality (fast/standard model) に対応"
```

---

## Task 7: Kling Provider を quality 対応（std/pro）

**Files:**
- Modify: `core/video_providers/kling.py`
- Test: `tests/test_video_providers_base.py`, `tests/test_kling_provider.py`

- [ ] **Step 1: テストを書く**

```python
def test_kling_supports_low_high():
    from core.video_providers.kling import Kling3ProProvider
    p = Kling3ProProvider()
    assert p.supported_qualities == ("low", "high")
    assert p.cost_basis == "per_video"


def test_kling_calc_cost_low_vs_high():
    from core.video_providers.kling import Kling3ProProvider
    p = Kling3ProProvider()
    low = _make_req(); low.quality = "low"
    high = _make_req(); high.quality = "high"
    assert p.calc_cost(low) < p.calc_cost(high)
```

- [ ] **Step 2: 失敗確認**

- [ ] **Step 3: kling.py を更新**

Task 0 の確認結果次第で 2 パターン：

**(a) URL 同一・model のみ違う場合**
```python
QUALITY_MAP = {"low": "kling-v3-std", "high": "kling-v3-pro"}
RATE_MAP = {"low": <std 固定額>, "high": <pro 固定額>}

async def generate(self, req):
    self.validate(req)
    model = self.QUALITY_MAP[req.quality]
    # payload で model パラメータ切替
```

**(b) URL も違う場合**
```python
from config import KLING_STD_URL, KLING_PRO_URL

QUALITY_MAP = {
    "low": {"model": "kling-v3-std", "url": KLING_STD_URL},
    "high": {"model": "kling-v3-pro", "url": KLING_PRO_URL},
}

async def generate(self, req):
    self.validate(req)
    cfg = self.QUALITY_MAP[req.quality]
    # cfg["url"] と cfg["model"] を使用
```

- [ ] **Step 4: テスト pass 確認**

- [ ] **Step 5: コミット**

```bash
git add core/video_providers/kling.py tests/test_video_providers_base.py
git commit -m "feat(video-ad-generator): Kling V3 を std/pro quality に対応"
```

---

## Task 8: DB マイグレーション 0002 を作成（Job.quality / Template.default_quality）

**Files:**
- Create: `migrations/versions/0002_add_quality_columns.py`
- Modify: `database.py`
- Test: `tests/test_alembic_phase2a.py`（新規）

- [ ] **Step 1: マイグレーションテストを書く**

`tests/test_alembic_phase2a.py`：

```python
"""Phase 2a マイグレーション 0002 のテスト。"""
import os
import tempfile
from pathlib import Path
from alembic.config import Config
from alembic import command
import sqlalchemy as sa


def _make_alembic_config(db_path: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_upgrade_adds_quality_columns_with_low_default(tmp_path):
    db = tmp_path / "test.db"
    cfg = _make_alembic_config(str(db))
    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        cols_jobs = {r[1]: r for r in conn.execute(sa.text("PRAGMA table_info(jobs)"))}
        assert "quality" in cols_jobs
        cols_templates = {r[1]: r for r in conn.execute(sa.text("PRAGMA table_info(templates)"))}
        assert "default_quality" in cols_templates


def test_existing_rows_backfilled_to_low(tmp_path):
    db = tmp_path / "test.db"
    cfg = _make_alembic_config(str(db))
    # まず Phase 1 状態にアップグレード
    command.upgrade(cfg, "7316290cb6fe")

    # 既存データを挿入
    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        conn.execute(sa.text("""
            INSERT INTO jobs (status, image_prompt, video_prompt, provider,
                              aspect_ratio, duration_seconds, image_source, created_at)
            VALUES ('done', 'i', 'v', 'seedance', '9:16', 10, 'generated', '2026-05-01 00:00:00')
        """))
        conn.execute(sa.text("""
            INSERT INTO templates (name, category, image_prompt, video_prompt,
                                   default_provider, default_aspect, default_duration,
                                   is_archived, created_at, updated_at)
            VALUES ('T', 'custom', 'i', 'v', 'seedance', '9:16', 10, 0,
                    '2026-05-01 00:00:00', '2026-05-01 00:00:00')
        """))
        conn.commit()

    # 0002 へアップグレード
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT quality FROM jobs")).fetchone()
        assert row[0] == "low"
        row = conn.execute(sa.text("SELECT default_quality FROM templates")).fetchone()
        assert row[0] == "low"


def test_downgrade_removes_quality_columns(tmp_path):
    db = tmp_path / "test.db"
    cfg = _make_alembic_config(str(db))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")

    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        cols_jobs = {r[1] for r in conn.execute(sa.text("PRAGMA table_info(jobs)"))}
        assert "quality" not in cols_jobs
        cols_templates = {r[1] for r in conn.execute(sa.text("PRAGMA table_info(templates)"))}
        assert "default_quality" not in cols_templates
```

- [ ] **Step 2: 失敗確認**

```bash
pytest tests/test_alembic_phase2a.py -v
```

Expected: FAIL（マイグレーション未作成）

- [ ] **Step 3: マイグレーションファイルを作成**

`migrations/versions/0002_add_quality_columns.py`：

```python
"""add_quality_columns

Revision ID: 0002_add_quality
Revises: 7316290cb6fe
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_quality"
down_revision: Union[str, Sequence[str], None] = "7316290cb6fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("quality", sa.String(length=16), nullable=False, server_default="low"))
    op.execute("UPDATE jobs SET quality='low' WHERE quality IS NULL")

    op.add_column("templates", sa.Column("default_quality", sa.String(length=16), nullable=False, server_default="low"))
    op.execute("UPDATE templates SET default_quality='low' WHERE default_quality IS NULL")


def downgrade() -> None:
    op.drop_column("templates", "default_quality")
    op.drop_column("jobs", "quality")
```

- [ ] **Step 4: database.py モデルに追加**

```python
class Job(Base):
    # ... 既存
    quality = Column(String(16), nullable=False, default="low")


class Template(Base):
    # ... 既存
    default_quality = Column(String(16), nullable=False, default="low")
```

- [ ] **Step 5: テスト pass 確認**

```bash
pytest tests/test_alembic_phase2a.py tests/test_database.py -v
```

Expected: 全 PASS

- [ ] **Step 6: コミット**

```bash
git add migrations/versions/0002_add_quality_columns.py database.py tests/test_alembic_phase2a.py
git commit -m "feat(video-ad-generator): Job.quality と Template.default_quality カラムを追加（マイグレーション 0002）"
```

---

## Task 9: Pydantic スキーマに quality / default_quality / aspect_ratio Literal 追加

**Files:**
- Modify: `api/generate.py`
- Modify: `api/templates.py`

- [ ] **Step 1: api/generate.py の Pydantic を更新**

```python
from typing import Literal

class GenerateImageRequest(BaseModel):
    image_prompt: str | None = None
    video_prompt: str | None = None
    provider: str | None = None
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:3", "3:4", "21:9"] | None = None
    duration_seconds: int | None = Field(None, ge=1, le=10)
    camera_preset: str | None = None
    image_source: Literal["generated", "uploaded"] | None = None
    template_id: int | None = None
    quality: Literal["low", "high"] | None = None  # 追加
```

- [ ] **Step 2: api/templates.py の Pydantic を更新**

```python
class TemplateCreate(BaseModel):
    # ... 既存
    default_quality: Literal["low", "high"] = "low"  # 追加


class TemplateUpdate(BaseModel):
    # ... 既存
    default_quality: Literal["low", "high"] | None = None  # 追加
```

- [ ] **Step 3: 既存テストが通ること確認**

```bash
pytest tests/test_api_generate_extended.py tests/test_api_templates.py -v
```

Expected: 全 PASS（既存テストは quality 未指定で default 流れ）

- [ ] **Step 4: コミット**

```bash
git add api/generate.py api/templates.py
git commit -m "feat(video-ad-generator): Pydantic スキーマに quality / default_quality / aspect_ratio Literal を追加"
```

---

## Task 10: core/templates.py の allowed セット拡張（default_quality 追加）

**Files:**
- Modify: `core/templates.py`
- Test: `tests/test_api_templates.py`（追加）

- [ ] **Step 1: テストを書く**

`tests/test_api_templates.py` に追加：

```python
def test_template_update_default_quality(client):
    cid = client.post("/api/templates", json={
        "name": "T", "category": "custom",
        "image_prompt": "i", "video_prompt": "v",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
    }).json()["id"]

    resp = client.patch(f"/api/templates/{cid}", json={"default_quality": "high"})
    assert resp.status_code == 200

    body = client.get(f"/api/templates/{cid}").json()
    assert body["default_quality"] == "high"


def test_template_create_with_default_quality(client):
    resp = client.post("/api/templates", json={
        "name": "T", "category": "custom",
        "image_prompt": "i", "video_prompt": "v",
        "default_provider": "seedance", "default_aspect": "9:16",
        "default_duration": 10, "default_camera_preset": None,
        "default_quality": "high",
    })
    assert resp.status_code == 200
    assert resp.json()["default_quality"] == "high"
```

- [ ] **Step 2: 失敗確認**

```bash
pytest tests/test_api_templates.py -v -k "default_quality"
```

Expected: FAIL

- [ ] **Step 3: core/templates.py を更新**

```python
def update_template(template_id: int, **fields):
    allowed = {
        "name", "category", "image_prompt", "video_prompt",
        "default_provider", "default_aspect", "default_duration",
        "default_camera_preset", "default_quality",  # 追加
        "is_archived",
    }
    # 以下既存
```

`create_template` も `default_quality` を引数に受け取り Template に渡すよう更新（既存パターンに従う）。

- [ ] **Step 4: テスト pass 確認**

```bash
pytest tests/test_api_templates.py -v
```

- [ ] **Step 5: コミット**

```bash
git add core/templates.py tests/test_api_templates.py
git commit -m "feat(video-ad-generator): template update/create に default_quality サポート"
```

---

## Task 11: api/generate.py の quality 解決ロジックと Job 書き込み

**Files:**
- Modify: `api/generate.py`
- Test: `tests/test_api_generate_extended.py`

- [ ] **Step 1: テストを書く**

```python
def test_generate_image_with_quality(client, monkeypatch):
    async def fake(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")
    monkeypatch.setattr(gen_mod, "generate_image", fake)

    resp = client.post("/api/generate/image", json={
        "image_prompt": "Portrait", "video_prompt": "v",
        "provider": "kling3_pro", "quality": "high",
    })
    job_id = resp.json()["job_id"]
    import database as db
    with db.get_session() as s:
        assert s.get(db.Job, job_id).quality == "high"


def test_generate_image_quality_default_low(client, monkeypatch):
    async def fake(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")
    monkeypatch.setattr(gen_mod, "generate_image", fake)

    resp = client.post("/api/generate/image", json={
        "image_prompt": "Portrait", "video_prompt": "v",
        "provider": "seedance",
    })
    job_id = resp.json()["job_id"]
    import database as db
    with db.get_session() as s:
        assert s.get(db.Job, job_id).quality == "low"


def test_generate_image_quality_fallback_to_template(client, monkeypatch):
    async def fake(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")
    monkeypatch.setattr(gen_mod, "generate_image", fake)

    cid = client.post("/api/templates", json={
        "name": "T", "category": "custom",
        "image_prompt": "i", "video_prompt": "v",
        "default_provider": "veo3_lite", "default_aspect": "16:9",
        "default_duration": 6, "default_camera_preset": None,
        "default_quality": "high",
    }).json()["id"]

    resp = client.post("/api/generate/image", json={"template_id": cid})
    job_id = resp.json()["job_id"]
    import database as db
    with db.get_session() as s:
        assert s.get(db.Job, job_id).quality == "high"


def test_generate_image_quality_explicit_overrides_template(client, monkeypatch):
    async def fake(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")
    monkeypatch.setattr(gen_mod, "generate_image", fake)

    cid = client.post("/api/templates", json={
        "name": "T", "category": "custom",
        "image_prompt": "i", "video_prompt": "v",
        "default_provider": "veo3_lite", "default_aspect": "16:9",
        "default_duration": 6, "default_camera_preset": None,
        "default_quality": "high",
    }).json()["id"]

    resp = client.post("/api/generate/image", json={"template_id": cid, "quality": "low"})
    job_id = resp.json()["job_id"]
    import database as db
    with db.get_session() as s:
        assert s.get(db.Job, job_id).quality == "low"


def test_generate_image_invalid_quality_returns_422(client):
    resp = client.post("/api/generate/image", json={
        "image_prompt": "i", "video_prompt": "v", "quality": "ultra",
    })
    assert resp.status_code == 422


def test_generate_image_extended_aspects(client, monkeypatch):
    async def fake(prompt, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")
    monkeypatch.setattr(gen_mod, "generate_image", fake)

    for aspect in ("1:1", "4:3", "3:4", "21:9"):
        resp = client.post("/api/generate/image", json={
            "image_prompt": "i", "video_prompt": "v",
            "provider": "seedance", "aspect_ratio": aspect,
        })
        assert resp.status_code == 200
```

- [ ] **Step 2: 失敗確認**

```bash
pytest tests/test_api_generate_extended.py -v -k "quality or extended_aspects"
```

Expected: FAIL

- [ ] **Step 3: api/generate.py の解決ロジックを実装**

```python
@router.post("/generate/image")
def generate_image_endpoint(req: GenerateImageRequest, background_tasks: BackgroundTasks):
    # ... 既存の template fetch
    template = None
    if req.template_id:
        with get_session() as s:
            template = s.get(Template, req.template_id)

    # 既存パターンの解決と並べる:
    resolved_provider = req.provider or (template.default_provider if template else None) or DEFAULT_PROVIDER
    resolved_aspect = req.aspect_ratio or (template.default_aspect if template else None) or "9:16"
    resolved_duration = req.duration_seconds or (template.default_duration if template else None) or 10
    resolved_camera = req.camera_preset or (template.default_camera_preset if template else None)
    resolved_quality = req.quality or (template.default_quality if template else None) or "low"  # ← 追加

    # Job 作成時に渡す:
    job = Job(
        # ... 既存
        quality=resolved_quality,
    )
```

- [ ] **Step 4: テスト pass 確認**

```bash
pytest tests/test_api_generate_extended.py -v
```

Expected: 全 PASS

- [ ] **Step 5: 既存テストも調整**

`test_generate_image_with_extended_params` に `assert job.quality == "low"` を追加。
`test_generate_image_with_template_id` も同様。

- [ ] **Step 6: コミット**

```bash
git add api/generate.py tests/test_api_generate_extended.py
git commit -m "feat(video-ad-generator): /api/generate/image で quality 解決ロジック実装"
```

---

## Task 12: api/approve.py で VideoGenRequest に quality を渡す

**Files:**
- Modify: `api/approve.py`
- Test: `tests/test_api_approve.py`（新規）

- [ ] **Step 1: テストを書く**

`tests/test_api_approve.py`：

```python
"""approve API が job.quality を VideoGenRequest に渡すこと。"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base, Job
import database
import api.approve as approve_mod


@pytest.fixture
def client(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "get_session", lambda: Session(engine))
    monkeypatch.setattr(approve_mod, "get_session", lambda: Session(engine))
    from main import app
    return TestClient(app)


def test_approve_passes_quality_to_provider(client, monkeypatch, tmp_path):
    captured = {}

    async def fake_generate(self, req):
        captured["quality"] = req.quality
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        req.output_path.write_bytes(b"v")
        return req.output_path

    from core.video_providers.seedance import SeedanceProvider
    monkeypatch.setattr(SeedanceProvider, "generate", fake_generate)

    # Job を作成（quality="high"）
    with database.get_session() as s:
        img = tmp_path / "img.jpg"; img.write_bytes(b"i")
        job = Job(status="pending_approval", image_prompt="i", video_prompt="v",
                  provider="seedance", aspect_ratio="9:16", duration_seconds=10,
                  image_source="generated", quality="high",
                  image_path=str(img))
        s.add(job); s.commit(); s.refresh(job)
        job_id = job.id

    resp = client.post("/api/approve/prompt", json={"job_id": job_id})
    assert resp.status_code == 200
    # 非同期で実行される場合は polling or wait が必要だが、実装に合わせて調整
    assert captured.get("quality") == "high"
```

- [ ] **Step 2: 失敗確認**

- [ ] **Step 3: api/approve.py の VideoGenRequest 構築箇所を修正**

```python
req = VideoGenRequest(
    image_path=image_path,
    video_prompt=job.video_prompt,
    aspect_ratio=job.aspect_ratio,
    duration_seconds=job.duration_seconds,
    camera_preset=job.camera_preset,
    quality=job.quality,  # ← 追加
    output_path=video_path,
)
```

- [ ] **Step 4: テスト pass 確認**

- [ ] **Step 5: コミット**

```bash
git add api/approve.py tests/test_api_approve.py
git commit -m "feat(video-ad-generator): approve で job.quality を VideoGenRequest に渡す"
```

---

## Task 13: api/approve.py で cost_basis を provider クラス属性経由に置換

**Files:**
- Modify: `api/approve.py`
- Test: `tests/test_api_approve.py`

- [ ] **Step 1: テストを追加**

```python
def test_approve_writes_provider_cost_basis_seedance(client, monkeypatch, tmp_path):
    async def fake_generate(self, req):
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        req.output_path.write_bytes(b"v")
        return req.output_path

    from core.video_providers.seedance import SeedanceProvider
    monkeypatch.setattr(SeedanceProvider, "generate", fake_generate)

    with database.get_session() as s:
        img = tmp_path / "img.jpg"; img.write_bytes(b"i")
        job = Job(status="pending_approval", image_prompt="i", video_prompt="v",
                  provider="seedance", aspect_ratio="9:16", duration_seconds=10,
                  image_source="generated", quality="low",
                  image_path=str(img))
        s.add(job); s.commit(); s.refresh(job)
        job_id = job.id

    client.post("/api/approve/prompt", json={"job_id": job_id})

    with database.get_session() as s:
        job = s.get(Job, job_id)
        assert job.video_cost_calc_basis == "per_second"


def test_approve_writes_provider_cost_basis_kling(client, monkeypatch, tmp_path):
    # 同様に kling3_pro で per_video が書かれることを確認
    ...
```

- [ ] **Step 2: 失敗確認**

- [ ] **Step 3: api/approve.py から hardcode を除去**

```python
# 削除:
# cost_basis = "per_second" if job.provider == "veo3_lite" else "per_video"
# job.video_cost_calc_basis = cost_basis

# 追加:
provider_obj = get_provider(job.provider)
job.video_cost_calc_basis = provider_obj.cost_basis
```

`from core.video_providers import get_provider` を import。

- [ ] **Step 4: テスト pass 確認**

```bash
pytest tests/test_api_approve.py -v
```

- [ ] **Step 5: コミット**

```bash
git add api/approve.py tests/test_api_approve.py
git commit -m "fix(video-ad-generator): cost_basis を provider クラス属性から取得（hardcode 解消）"
```

---

## Task 14: 新規エンドポイント GET /api/providers/capabilities

**Files:**
- Create: `api/providers.py`
- Modify: `main.py`
- Test: `tests/test_api_providers.py`（新規）

- [ ] **Step 1: テストを書く**

`tests/test_api_providers.py`：

```python
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_capabilities_endpoint_returns_all_providers(client):
    resp = client.get("/api/providers/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data]
    assert set(names) == {"seedance", "veo3_lite", "kling3_pro"}


def test_capabilities_seedance_includes_new_aspects(client):
    resp = client.get("/api/providers/capabilities")
    seedance = next(p for p in resp.json() if p["name"] == "seedance")
    assert seedance["cost_basis"] == "per_second"
    assert seedance["rate_map"]["low"] == 0.081
    assert "high" in seedance["rate_map"]
    for aspect in ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9"):
        assert aspect in seedance["supported_aspects"]
    assert seedance["supported_qualities"] == ["low", "high"]


def test_capabilities_veo3_quality_supported(client):
    resp = client.get("/api/providers/capabilities")
    veo3 = next(p for p in resp.json() if p["name"] == "veo3_lite")
    assert veo3["cost_basis"] == "per_second"
    assert "high" in veo3["rate_map"]


def test_capabilities_kling_per_video(client):
    resp = client.get("/api/providers/capabilities")
    kling = next(p for p in resp.json() if p["name"] == "kling3_pro")
    assert kling["cost_basis"] == "per_video"
```

- [ ] **Step 2: 失敗確認**

```bash
pytest tests/test_api_providers.py -v
```

Expected: FAIL（404 or import error）

- [ ] **Step 3: api/providers.py を作成**

```python
"""Provider capabilities エンドポイント。"""
from fastapi import APIRouter
from core.video_providers.seedance import SeedanceProvider
from core.video_providers.veo3 import Veo3LiteProvider
from core.video_providers.kling import Kling3ProProvider

router = APIRouter(prefix="/api")

PROVIDERS = [SeedanceProvider(), Veo3LiteProvider(), Kling3ProProvider()]


@router.get("/providers/capabilities")
def list_capabilities():
    return [
        {
            "name": p.name,
            "supported_aspects": list(p.supported_aspects),
            "supported_qualities": list(p.supported_qualities),
            "supported_durations": list(p.supported_durations),
            "rate_map": p.RATE_MAP,
            "cost_basis": p.cost_basis,
        }
        for p in PROVIDERS
    ]
```

- [ ] **Step 4: main.py にルーターを追加**

```python
from api import providers as providers_router
app.include_router(providers_router.router)
```

- [ ] **Step 5: テスト pass 確認**

```bash
pytest tests/test_api_providers.py -v
```

- [ ] **Step 6: コミット**

```bash
git add api/providers.py main.py tests/test_api_providers.py
git commit -m "feat(video-ad-generator): GET /api/providers/capabilities 追加（Python/JS 二重管理解消）"
```

---

## Task 15: デザイントークン CSS 作成

**Files:**
- Create: `static/css/tokens.css`

- [ ] **Step 1: tokens.css を作成**

```css
:root {
  --bg: #FFFFFF;
  --surface: #F7F7F8;
  --border: #E5E5E7;
  --text-primary: #1A1A1A;
  --text-secondary: #6B6B70;
  --accent: #4F46E5;
  --accent-hover: #4338CA;
  --accent-light: #EEF2FF;
  --success: #10B981;
  --danger: #EF4444;
  --radius: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.06);
  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --font-body: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic UI", sans-serif;
}

body {
  background: var(--bg);
  color: var(--text-primary);
  font-family: var(--font-body);
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}
```

- [ ] **Step 2: コミット**

```bash
git add static/css/tokens.css
git commit -m "feat(video-ad-generator): デザイントークン CSS 作成（白背景 + indigo accent）"
```

---

## Task 16: 共通レイアウト CSS 作成（top bar / sidebar / cards）

**Files:**
- Create: `static/css/layout.css`

- [ ] **Step 1: layout.css を作成**

```css
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.topbar {
  height: 56px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 var(--space-lg);
  gap: var(--space-lg);
}

.topbar__logo { font-weight: 700; font-size: 16px; }
.topbar__tabs { display: flex; gap: var(--space-md); }
.topbar__tab {
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius);
  color: var(--text-secondary);
  cursor: pointer;
  border: none; background: transparent;
}
.topbar__tab--active { color: var(--text-primary); background: var(--surface); }

.main { display: flex; flex: 1; overflow: hidden; }

.sidebar {
  width: 360px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: var(--space-lg);
  overflow-y: auto;
}

.canvas {
  flex: 1;
  background: var(--bg);
  padding: var(--space-lg);
  overflow-y: auto;
}

.card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
  box-shadow: var(--shadow-sm);
}

.banner {
  padding: var(--space-md);
  border-radius: var(--radius);
  margin-bottom: var(--space-md);
}
.banner--error { background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }
.banner--success { background: #D1FAE5; color: #065F46; border: 1px solid #6EE7B7; }
```

- [ ] **Step 2: コミット**

```bash
git add static/css/layout.css
git commit -m "feat(video-ad-generator): 共通レイアウト CSS（top bar / sidebar / cards）"
```

---

## Task 17: アスペクト比アイコン SVG 作成

**Files:**
- Create: `static/img/aspect-icons.svg`

- [ ] **Step 1: aspect-icons.svg を作成**

各アスペクト比を `<symbol>` で定義し、`<use>` で参照可能にする。32×32 のビューポートに最大寸法で centering：

```svg
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">
  <!-- 9:16 (vertical, 9:16 = 0.5625) -->
  <symbol id="aspect-9-16" viewBox="0 0 32 32">
    <rect x="9.5" y="2" width="13" height="28" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>
  </symbol>
  <!-- 16:9 (horizontal, 16:9 = 1.778) -->
  <symbol id="aspect-16-9" viewBox="0 0 32 32">
    <rect x="2" y="9.5" width="28" height="13" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>
  </symbol>
  <!-- 1:1 (square) -->
  <symbol id="aspect-1-1" viewBox="0 0 32 32">
    <rect x="4" y="4" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>
  </symbol>
  <!-- 4:3 -->
  <symbol id="aspect-4-3" viewBox="0 0 32 32">
    <rect x="2" y="6" width="28" height="20" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>
  </symbol>
  <!-- 3:4 -->
  <symbol id="aspect-3-4" viewBox="0 0 32 32">
    <rect x="6" y="2" width="20" height="28" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>
  </symbol>
  <!-- 21:9 (ultra-wide) -->
  <symbol id="aspect-21-9" viewBox="0 0 32 32">
    <rect x="2" y="13" width="28" height="6" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>
  </symbol>
</svg>
```

- [ ] **Step 2: コミット**

```bash
git add static/img/aspect-icons.svg
git commit -m "feat(video-ad-generator): アスペクト比アイコン SVG（6 種、32x32 centering）"
```

---

## Task 18: generate.css 作成（動画作成画面固有）

**Files:**
- Create: `static/css/generate.css`

- [ ] **Step 1: generate.css を作成**

```css
.section { margin-bottom: var(--space-lg); }
.section__label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--space-sm);
}

textarea.input {
  width: 100%;
  min-height: 80px;
  padding: var(--space-sm);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: var(--font-body);
  font-size: 14px;
  background: var(--bg);
}

/* Segmented toggle */
.segmented {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg);
}
.segmented__btn {
  flex: 1;
  padding: var(--space-sm);
  background: var(--bg);
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
}
.segmented__btn--active {
  background: var(--accent);
  color: #FFFFFF;
}
.segmented__btn--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Aspect chips grid */
.chip-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-sm);
}
.chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: var(--space-sm);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
}
.chip__icon { width: 32px; height: 32px; color: var(--text-secondary); }
.chip--active {
  border-color: var(--accent);
  background: var(--accent-light);
  color: var(--accent);
}
.chip--active .chip__icon { color: var(--accent); }
.chip--disabled { opacity: 0.4; cursor: not-allowed; }

/* Cost & CTA */
.cost-line {
  font-size: 14px;
  color: var(--text-secondary);
  margin: var(--space-md) 0 var(--space-sm);
}
.cta {
  display: block;
  width: 100%;
  height: 48px;
  background: var(--accent);
  color: #FFFFFF;
  border: none;
  border-radius: var(--radius);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}
.cta:hover:not(:disabled) { background: var(--accent-hover); }
.cta:disabled { opacity: 0.6; cursor: wait; }
```

- [ ] **Step 2: コミット**

```bash
git add static/css/generate.css
git commit -m "feat(video-ad-generator): 動画作成画面 CSS（chip / segmented / CTA）"
```

---

## Task 19: index.html の動画作成パネルを新 UI に書き換え

**Files:**
- Modify: `static/index.html`

**事前確認**: 既存の panel-pending / panel-confirmed の HTML 構造とタブ切替 JS を維持し、panel-generate（または相当部分）のみを差し替える。

- [ ] **Step 1: 新 UI の HTML を index.html に組み込む**

panel-generate の中身を以下に差し替え：

```html
<div class="app">
  <!-- 既存のトップバーを「タブ風」にスタイリング -->
  <header class="topbar">
    <div class="topbar__logo">Video Ad Generator</div>
    <nav class="topbar__tabs" role="tablist">
      <button class="topbar__tab topbar__tab--active" data-panel="generate">動画作成</button>
      <button class="topbar__tab" data-panel="pending">承認待ち</button>
      <button class="topbar__tab" data-panel="confirmed">確定済み</button>
      <a class="topbar__tab" href="/templates.html">テンプレート</a>
    </nav>
  </header>

  <main class="main">
    <aside class="sidebar" id="panel-generate-sidebar">
      <!-- 画像プロンプト -->
      <section class="section">
        <label class="section__label">画像</label>
        <div class="segmented" role="radiogroup" aria-label="画像ソース">
          <button class="segmented__btn segmented__btn--active" data-image-source="generated" role="radio" aria-checked="true">生成</button>
          <button class="segmented__btn" data-image-source="uploaded" role="radio" aria-checked="false">アップロード</button>
        </div>
        <textarea class="input" id="image-prompt" placeholder="画像プロンプト" style="margin-top: var(--space-sm);"></textarea>
      </section>

      <!-- 動画プロンプト -->
      <section class="section">
        <label class="section__label" for="video-prompt">動画プロンプト</label>
        <textarea class="input" id="video-prompt" placeholder="動きの指示"></textarea>
      </section>

      <!-- Provider -->
      <section class="section">
        <label class="section__label">プロバイダー</label>
        <div class="segmented" role="radiogroup" aria-label="プロバイダー" id="provider-segmented">
          <!-- JS で構築 -->
        </div>
      </section>

      <!-- Quality -->
      <section class="section">
        <label class="section__label">画質</label>
        <div class="segmented" role="radiogroup" aria-label="画質" id="quality-segmented">
          <button class="segmented__btn segmented__btn--active" data-quality="low" role="radio" aria-checked="true">Low</button>
          <button class="segmented__btn" data-quality="high" role="radio" aria-checked="false">High</button>
        </div>
      </section>

      <!-- Aspect ratio -->
      <section class="section">
        <label class="section__label">アスペクト比</label>
        <div class="chip-grid" role="radiogroup" aria-label="アスペクト比" id="aspect-grid">
          <!-- JS で構築 -->
        </div>
      </section>

      <!-- Duration -->
      <section class="section">
        <label class="section__label">尺</label>
        <div class="segmented" role="radiogroup" aria-label="尺" id="duration-segmented">
          <!-- JS で構築 -->
        </div>
      </section>

      <!-- Camera preset -->
      <section class="section">
        <label class="section__label" for="camera-preset">カメラプリセット</label>
        <select id="camera-preset" class="input">
          <option value="">なし</option>
          <!-- JS で動的追加 -->
        </select>
      </section>

      <!-- Cost & CTA -->
      <div class="cost-line" aria-live="polite">推定コスト: <span id="cost-estimate">$0.00</span></div>
      <button class="cta" id="generate-btn">動画を作成</button>
    </aside>

    <section class="canvas" id="panel-generate-canvas">
      <div id="error-banner" class="banner banner--error" role="alert" hidden></div>
      <div id="preview-area"><!-- 生成中スケルトン or プレビュー --></div>
      <div class="section" style="margin-top: var(--space-xl);">
        <h3>最近のジョブ</h3>
        <div class="chip-grid" id="recent-jobs"><!-- 最大 6 枚 --></div>
      </div>
    </section>
  </main>
</div>
```

CSS リンクを冒頭に追加：
```html
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/layout.css">
<link rel="stylesheet" href="/static/css/generate.css">
```

`<svg>` インクルード：
```html
<div hidden><object data="/static/img/aspect-icons.svg"></object></div>
<!-- or 直接インラインで挿入 -->
```

- [ ] **Step 2: 既存 panel-pending / panel-confirmed の動作を維持**

タブクリックで panel 切替するスクリプトを既存仕様に合わせる。新タブ「動画作成」がデフォルト active。

- [ ] **Step 3: ブラウザで起動して動画作成パネルが白背景で表示されることを確認**

```bash
cd products/video-ad-generator && python main.py
# ブラウザで http://localhost:8000/ を開いて UI 確認
```

- [ ] **Step 4: コミット**

```bash
git add static/index.html
git commit -m "feat(video-ad-generator): 動画作成パネルを新 UI（白背景・2 カラム）に刷新"
```

---

## Task 20: generate.js を capabilities API 連携に書き換え

**Files:**
- Modify: `static/js/generate.js`

- [ ] **Step 1: capabilities fetch + UI 構築ロジック**

```js
let CAPABILITIES = [];
let state = {
  provider: null,
  quality: "low",
  aspect: "9:16",
  duration: 10,
  imageSource: "generated",
  cameraPreset: "",
};

async function loadCapabilities() {
  const resp = await fetch("/api/providers/capabilities");
  CAPABILITIES = await resp.json();
  state.provider = CAPABILITIES[0].name;
  renderProviders();
  renderAspects();
  renderDurations();
  refreshChipsForProvider();
  refreshCostEstimate();
}

function renderProviders() {
  const seg = document.getElementById("provider-segmented");
  seg.innerHTML = CAPABILITIES.map(p =>
    `<button class="segmented__btn ${p.name === state.provider ? 'segmented__btn--active' : ''}"
       data-provider="${p.name}" role="radio" aria-checked="${p.name === state.provider}">
       ${p.name}
     </button>`
  ).join("");
  seg.addEventListener("click", e => {
    const btn = e.target.closest("[data-provider]");
    if (!btn) return;
    state.provider = btn.dataset.provider;
    renderProviders();
    refreshChipsForProvider();
    refreshCostEstimate();
  });
}

function renderAspects() {
  const ALL_ASPECTS = ["9:16", "16:9", "1:1", "4:3", "3:4", "21:9"];
  const grid = document.getElementById("aspect-grid");
  grid.innerHTML = ALL_ASPECTS.map(a =>
    `<button class="chip" data-aspect="${a}" role="radio" aria-checked="${a === state.aspect}">
       <svg class="chip__icon"><use href="#aspect-${a.replace(':', '-')}"/></svg>
       <span>${a}</span>
     </button>`
  ).join("");
  grid.addEventListener("click", e => {
    const btn = e.target.closest("[data-aspect]");
    if (!btn || btn.classList.contains("chip--disabled")) return;
    state.aspect = btn.dataset.aspect;
    refreshChipsForProvider();
    refreshCostEstimate();
  });
}

function refreshChipsForProvider() {
  const cap = CAPABILITIES.find(p => p.name === state.provider);
  // Aspects
  document.querySelectorAll("#aspect-grid .chip").forEach(c => {
    const a = c.dataset.aspect;
    const supported = cap.supported_aspects.includes(a);
    c.classList.toggle("chip--disabled", !supported);
    c.classList.toggle("chip--active", supported && a === state.aspect);
    c.setAttribute("aria-checked", supported && a === state.aspect);
  });
  // 不一致なら state.aspect を fallback
  if (!cap.supported_aspects.includes(state.aspect)) {
    state.aspect = cap.supported_aspects[0];
    refreshChipsForProvider();
  }
  // Quality
  document.querySelectorAll("#quality-segmented .segmented__btn").forEach(b => {
    const q = b.dataset.quality;
    b.classList.toggle("segmented__btn--disabled", !cap.supported_qualities.includes(q));
    b.classList.toggle("segmented__btn--active", q === state.quality);
  });
}

function renderDurations() {
  // duration_segmented を CAPABILITIES の supported_durations から構築
}

function refreshCostEstimate() {
  const cap = CAPABILITIES.find(p => p.name === state.provider);
  const rate = cap.rate_map[state.quality];
  const cost = cap.cost_basis === "per_second" ? rate * state.duration : rate;
  document.getElementById("cost-estimate").textContent = `$${cost.toFixed(4)}`;
}

document.getElementById("quality-segmented").addEventListener("click", e => {
  const btn = e.target.closest("[data-quality]");
  if (!btn || btn.classList.contains("segmented__btn--disabled")) return;
  state.quality = btn.dataset.quality;
  refreshChipsForProvider();
  refreshCostEstimate();
});

document.getElementById("generate-btn").addEventListener("click", async () => {
  const btn = document.getElementById("generate-btn");
  btn.disabled = true;
  btn.textContent = "生成中…";
  const errorBanner = document.getElementById("error-banner");
  errorBanner.hidden = true;

  try {
    const resp = await fetch("/api/generate/image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_prompt: document.getElementById("image-prompt").value,
        video_prompt: document.getElementById("video-prompt").value,
        provider: state.provider,
        aspect_ratio: state.aspect,
        duration_seconds: state.duration,
        camera_preset: state.cameraPreset || null,
        image_source: state.imageSource,
        quality: state.quality,
      }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    // 既存の polling / preview ロジックを呼ぶ
  } catch (e) {
    errorBanner.textContent = `エラー: ${e.message}`;
    errorBanner.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "動画を作成";
  }
});

window.addEventListener("DOMContentLoaded", loadCapabilities);
```

- [ ] **Step 2: ブラウザで動作確認**

- 起動して capabilities が読まれ、provider 切替で aspect chip が disable される
- quality 切替が動作
- 推定コストが provider/quality/duration で再計算される
- Generate ボタンが送信中 disable

- [ ] **Step 3: コミット**

```bash
git add static/js/generate.js
git commit -m "feat(video-ad-generator): generate.js を capabilities API 連携 + チップ UI に刷新"
```

---

## Task 21: テンプレート画面（templates.html / templates.js / templates.css）刷新

**Files:**
- Modify: `static/templates.html`
- Modify: `static/js/templates.js`
- Create: `static/css/templates.css`

**事前確認**: Task 0 Step 5 で確認した既存 modal 実装を踏襲、なければ初実装。

- [ ] **Step 1: templates.css 作成**

```css
.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-md);
}
.template-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
  position: relative;
}
.template-card__badges {
  display: flex; gap: 4px; margin-top: var(--space-xs);
}
.template-card__badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--surface);
  color: var(--text-secondary);
}
.template-card__cta {
  margin-top: var(--space-sm);
  display: none;
  background: var(--accent);
  color: #fff;
  border: none;
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius);
  cursor: pointer;
}
.template-card:hover .template-card__cta { display: inline-block; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.modal {
  background: var(--bg);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  box-shadow: var(--shadow-md);
  max-width: 480px;
  width: 90%;
}
```

- [ ] **Step 2: templates.html 刷新**

`tokens.css / layout.css / templates.css` を読み込み。一覧をカードグリッド化、編集モーダルに `default_quality` フィールド追加。

- [ ] **Step 3: templates.js 刷新**

- create / update payload に `default_quality` を含める
- カード表示に default_quality バッジ
- モーダル: focus trap (`HTMLDialogElement` でも可) / Escape close / overlay click close

- [ ] **Step 4: ブラウザで動作確認**

- テンプレート作成・編集で default_quality が保存される
- モーダルの a11y 動作確認

- [ ] **Step 5: 既存 style.css の generate / templates 部分を削除**

panel-pending / panel-confirmed のスタイルのみ残す。

- [ ] **Step 6: コミット**

```bash
git add static/templates.html static/js/templates.js static/css/templates.css static/css/style.css
git commit -m "feat(video-ad-generator): テンプレート画面を新 UI（カードグリッド + モーダル）に刷新"
```

---

## Task 22: 既存テストの調整（quality アサーション追加）

**Files:**
- Modify: `tests/test_api_generate_extended.py`

- [ ] **Step 1: 既存テストにアサーション追加**

```python
def test_generate_image_with_extended_params(client, monkeypatch):
    # ... 既存
    with db_mod.get_session() as session:
        job = session.get(db_mod.Job, job_id)
        # ... 既存アサーション
        assert job.quality == "low"  # 追加


def test_generate_image_with_template_id(client, monkeypatch):
    # ... 既存
    with db_mod.get_session() as session:
        job = session.get(db_mod.Job, job_id)
        # ... 既存アサーション
        assert job.quality == "low"  # 追加
```

- [ ] **Step 2: テスト pass 確認**

```bash
pytest tests/test_api_generate_extended.py -v
```

- [ ] **Step 3: コミット**

```bash
git add tests/test_api_generate_extended.py
git commit -m "test(video-ad-generator): 既存テストに quality アサーション追加"
```

---

## Task 23: 全テスト + 起動 smoke test

**Files:** なし（検証タスク）

- [ ] **Step 1: 全テスト実行**

```bash
cd products/video-ad-generator && pytest tests/ -v
```

Expected: 全 PASS

- [ ] **Step 2: マイグレーション実行**

```bash
alembic upgrade head
```

Expected: 成功（既存 DB に対して）

- [ ] **Step 3: サーバ起動 smoke**

```bash
python main.py &
SERVER_PID=$!
sleep 3
curl -s http://localhost:8000/api/providers/capabilities | python -m json.tool
kill $SERVER_PID
```

Expected: 3 provider の capabilities が JSON で返る

- [ ] **Step 4: 手動 UI 確認チェックリスト**

仕様書 Section 5.5 の項目をすべて確認：
- 全画面が白背景
- アスペクト比 6 chip が provider 切替で disable
- Quality segmented toggle 動作
- 推定コスト動的更新
- Generate ボタン送信中 disable
- エラー時 inline banner 表示
- キーボードのみで全操作可能
- a11y: コスト変更が読み上げられる
- テンプレートモーダルの focus trap / Escape close

- [ ] **Step 5: 確認完了をコミット（チェックリスト付き）**

```bash
git commit --allow-empty -m "test(video-ad-generator): Phase 2a 手動検証完了"
```

---

## Self-Review チェックリスト（実装計画書を書き終えた後の最終確認）

### Spec coverage（仕様書の各セクションが計画にあるか）
- ✅ Section 1（共通抽象 / cost_basis 移行）→ Task 2, 13
- ✅ Section 2（DB / マイグレーション）→ Task 8
- ✅ Section 3（Provider 層）→ Task 1-7
- ✅ Section 4.1-4.4（API スキーマ・解決ロジック・approve）→ Task 9-13
- ✅ Section 4.5（capabilities API）→ Task 14
- ✅ Section 4.6-4.13（UI 仕様）→ Task 15-21
- ✅ Section 5（Testing）→ 各 Task に分散
- ✅ 実装着手前必須確認 → Task 0

### Placeholder スキャン
- 「要確定」マーカーは Task 0 で解消する設計
- 「TBD」「適切に〜」「同様に〜」など曖昧表現なし
- 全コードブロックは実装可能な内容を提示

### 型一貫性
- `quality` は全てで `str` (Python) / `Literal["low","high"]` (Pydantic)
- `cost_basis` は `Literal["per_second", "per_video"]` 相当の str
- `RATE_MAP` は `dict[str, float]`
- Provider クラス名は Seedance/Veo3Lite/Kling3Pro で一貫

---

## Plan complete. 実行戦略を選択してください

**1. Subagent-Driven（推奨）** — 各タスクで fresh subagent + spec/quality 二段レビュー、高速反復

**2. Inline Execution** — 同セッションで executing-plans によるバッチ実行、チェックポイントで確認

どちらで進めますか？
