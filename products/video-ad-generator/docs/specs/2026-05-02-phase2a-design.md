---
name: Phase 2a Design — アスペクト比拡張 + 画質セレクタ + UI リデザイン
date: 2026-05-02
status: approved
---

# Phase 2a Design — アスペクト比拡張 + 画質セレクタ + UI リデザイン

## ゴール

video-ad-generator に以下を追加する：

1. **アスペクト比の拡張**（Seedance: 9:16/16:9 → 全 6 種、Veo3/Kling は既存維持）
2. **画質セレクタ**（low / high の共通抽象 + provider 別 QUALITY_MAP）
3. **コスト基準の正規化**（`cost_basis` を Provider クラス属性化、approve.py の hardcode 解消）
4. **UI リデザイン**（Adobe Firefly / GoEnhance / DomoAI を参考にした白背景 2 カラムレイアウト）

複数クリップ連結機能は **Phase 2b** として別仕様で扱う。

---

## Section 1: アーキテクチャ概要

### 共通抽象「low / high」モデル

全 provider が `("low", "high")` の 2 段階画質をサポートする共通抽象を採用。Provider 内部の `QUALITY_MAP` で API 固有の文字列・モデル ID にマッピングする。

```
Job.quality (str: "low"|"high")
  → VideoGenRequest.quality
  → provider.QUALITY_MAP[quality]
  → API リクエストパラメータ
```

### `cost_basis` の Provider クラス属性化

Phase 1 では `api/approve.py` で `"per_second" if veo3_lite else "per_video"` とハードコードされていた。Phase 2a でこれを `Provider.cost_basis` クラス属性に移し、`approve.py` から `provider.cost_basis` を読むように変更。

### Phase 1 final review 残課題

- ✅ #1 cost_basis hardcode → Phase 2a で解消
- ❌ #2 upload+template モードの空 video_prompt → スコープ外
- ❌ #3 pending grid `/output/pending/` ハードコード → スコープ外

### 既知のリスク（実装前に解消必須）

1. Seedance "pro" quality 文字列の正式名と料金 → 要 Atlas Cloud 確認
2. Veo 3.1 standard model ID と料金 → 要 Google AI 確認
3. Kling std/pro が同一 URL+model だけの差か、別エンドポイントか → 要 MuAPI 確認

---

## Section 2: DB / マイグレーション

### Job テーブル変更
- `quality VARCHAR(16) NOT NULL DEFAULT 'low'` 追加
- 既存行は backfill で `'low'` に更新

### Template テーブル変更
- `default_quality VARCHAR(16) NOT NULL DEFAULT 'low'` 追加
- 既存行は backfill で `'low'` に更新

### Alembic マイグレーション

```python
def upgrade():
    op.add_column("jobs", sa.Column("quality", sa.String(16), nullable=False, server_default="low"))
    op.execute("UPDATE jobs SET quality='low' WHERE quality IS NULL")  # 安全策

    op.add_column("templates", sa.Column("default_quality", sa.String(16), nullable=False, server_default="low"))
    op.execute("UPDATE templates SET default_quality='low' WHERE default_quality IS NULL")

def downgrade():
    op.drop_column("templates", "default_quality")
    op.drop_column("jobs", "quality")
```

### 互換性メモ
- SQLite ≥ 3.35 で `ADD COLUMN NOT NULL DEFAULT` を単一文で実行可能
- 既存運用 DB のバージョンを実装前に確認

---

## Section 3: Provider 層

### VideoProvider 基底クラス追加

```python
class VideoProvider:
    name: str
    supported_aspects: tuple[str, ...]
    supported_durations: tuple[int, ...]
    supported_qualities: tuple[str, ...] = ("low", "high")  # 追加
    cost_basis: str = "per_video"  # "per_second" or "per_video" (追加)
    RATE_MAP: dict[str, float] = {}  # quality -> rate (追加)

    def validate(self, req: VideoGenRequest):
        if req.aspect_ratio not in self.supported_aspects:
            raise ValueError(f"unsupported aspect: {req.aspect_ratio}")
        if req.duration_seconds not in self.supported_durations:
            raise ValueError(f"unsupported duration: {req.duration_seconds}")
        if req.quality not in self.supported_qualities:
            raise ValueError(f"unsupported quality: {req.quality}")

    def calc_cost(self, req: VideoGenRequest) -> float:
        rate = self.RATE_MAP[req.quality]
        if self.cost_basis == "per_second":
            return round(rate * req.duration_seconds, 4)
        return round(rate, 4)
```

### VideoGenRequest

```python
@dataclass
class VideoGenRequest:
    image_path: Path
    video_prompt: str
    aspect_ratio: str
    duration_seconds: int
    camera_preset: str | None
    output_path: Path
    quality: str = "low"  # 末尾に追加（既存 kwargs 呼び出しと互換）
```

### Per-provider 確定値

| Provider | aspects | QUALITY_MAP | cost_basis | RATE_MAP |
|---|---|---|---|---|
| Seedance | 9:16, 16:9, **1:1, 4:3, 3:4, 21:9** | `{"low":"basic","high":"pro"}` ※pro要確定 | **per_second**（修正） | `{"low":0.081,"high":0.13}` ※高画質要確定 |
| Veo 3.1 Lite | 9:16, 16:9 | `{"low":VEO3_FAST_MODEL_ID,"high":VEO3_STANDARD_MODEL_ID}` ※要確定 | per_second | `{"low":<既存>,"high":<要確定>}` |
| Kling V3 | 9:16, 16:9, 1:1 | `{"low":{"model":"kling-v3-std","url":KLING_STD_URL},"high":{"model":"kling-v3-pro","url":KLING_PRO_URL}}` ※URL差異要MuAPI確認 | per_video | `{"low":<std固定額>,"high":<pro固定額>}` |

### config.py / .env.example マイグレーション

- `VEO3_MODEL_ID` を deprecate（一定期間 fast の fallback として残す or 即削除は実装時判断）
- 新規追加: `VEO3_FAST_MODEL_ID`, `VEO3_STANDARD_MODEL_ID`, `KLING_STD_URL`（必要なら）, `KLING_PRO_URL`（必要なら）
- `.env.example` 更新（git add はユーザーが手動）

### API 層との二重防御

- Pydantic 側で `quality: Literal["low","high"] = "low"`（Section 4 で扱う）
- Provider 側 `validate()` は二重防御として残す

### Phase 2a で全 provider が low/high をフラットサポート

将来 provider 別の値域が必要になった時点で API 層の Literal を見直す。

---

## Section 4: API / UI 層

### 4.1 Pydantic スキーマ

```python
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

class TemplateCreate(BaseModel):
    # ... 既存フィールド
    default_quality: Literal["low", "high"] = "low"  # 追加

class TemplateUpdate(BaseModel):
    # ... 既存フィールド
    default_quality: Literal["low", "high"] | None = None  # 追加
```

`aspect_ratio` を `Literal` に厳格化することで未対応値は 422 を返す（Phase 1 では `str | None` で受け入れていた）。UI 側はラジオ・チップなので影響なし。

### 4.2 quality 解決ロジック（POST /api/generate/image）

明示優先 → template default → "low" の 3 段フォールバック：

```python
resolved_quality = (
    req.quality
    or (template.default_quality if template else None)
    or "low"
)
job.quality = resolved_quality
```

既存の `aspect_ratio` / `duration_seconds` / `camera_preset` と完全同パターン。明示的な quality は template.default_quality を上書きする。

### 4.3 core/templates.py の allowed set 拡張

```python
allowed = {
    "name", "category", "image_prompt", "video_prompt",
    "default_provider", "default_aspect", "default_duration",
    "default_camera_preset", "default_quality",  # 追加
    "is_archived",
}
```

### 4.4 api/approve.py の改修（独立した 2 ステップ）

**ステップ A: VideoGenRequest に quality を渡す**

```python
req = VideoGenRequest(
    image_path=...,
    video_prompt=...,
    aspect_ratio=job.aspect_ratio,
    duration_seconds=job.duration_seconds,
    camera_preset=job.camera_preset,
    quality=job.quality,  # 追加
    output_path=...,
)
```

**ステップ B: cost_basis を provider クラス属性から取る**

```python
# 削除:
# cost_basis = "per_second" if veo3_lite else "per_video"

# 追加:
provider = get_provider(job.provider)
job.video_cost_calc_basis = provider.cost_basis
```

`job.video_cost_calc_basis` は approve 時点で書き込まれる。video 生成失敗時に basis のみ残る挙動は許容（既存と同じ）。

### 4.5 新規エンドポイント `GET /api/providers/capabilities`

**目的**: rate / aspect / quality / duration を Python 単一ソースから JS に流す（二重管理解消）

```python
# api/providers.py（新規）
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
        for p in [SeedanceProvider(), Veo3LiteProvider(), Kling3ProProvider()]
    ]
```

フロントは初期ロード時に fetch して `PROVIDER_SUPPORT` を構築。

### 4.6 既存 panel 切替との関係

- 既存 panel-pending / panel-confirmed は別タブ風 UI として残し、新 UI は **「動画作成」タブのみ刷新**
- マルチページ化 / 履歴タブ新規実装は Phase 2b 以降
- pending grid の `/output/pending/` ハードコード解消は Phase 2a スコープ外

### 4.7 デザイントークン（`static/css/tokens.css` 新規）

```css
:root {
  --bg: #FFFFFF;
  --surface: #F7F7F8;
  --border: #E5E5E7;
  --text-primary: #1A1A1A;
  --text-secondary: #6B6B70;
  --accent: #4F46E5;
  --accent-hover: #4338CA;
  --success: #10B981;
  --danger: #EF4444;
  --radius: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.06);
  --space-xs: 8px; --space-sm: 12px; --space-md: 16px;
  --space-lg: 24px; --space-xl: 32px;
  --font-body: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic UI", sans-serif;
}
```

### 4.8 動画作成画面レイアウト

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo] 動画作成 / テンプレート / 履歴             [API残高] │
├──────────────────────┬──────────────────────────────────────┤
│ サイドバー (360px)   │ メインキャンバス                      │
│                      │                                      │
│ [画像] ─────────     │  ┌────────────────────────────┐     │
│  ○ アップロード      │  │   生成中... 45%            │     │
│  ● 生成              │  │   [スケルトン or プレビュー]│     │
│  [画像 prompt]       │  └────────────────────────────┘     │
│                      │                                      │
│ [動画 prompt]        │  最近のジョブ                          │
│                      │  [card] [card] [card]                │
│ [プロバイダー]       │                                      │
│  [Seedance|Veo3|Kling] (segmented toggle)                   │
│                      │                                      │
│ [画質]               │                                      │
│  [Low | High]        │                                      │
│                      │                                      │
│ [アスペクト比]       │                                      │
│  □ 9:16 □ 16:9 □ 1:1 │                                      │
│  □ 4:3  □ 3:4  □ 21:9│                                      │
│                      │                                      │
│ [尺] [5s] [10s]      │                                      │
│ [カメラプリセット] ▾ │                                      │
│                      │                                      │
│ [推定コスト: $0.81]   │                                      │
│ [ 動画を作成 ]        │                                      │
└──────────────────────┴──────────────────────────────────────┘
```

### 4.9 コンポーネント仕様

- **サイドバー**: 360px 固定、`background: var(--surface)`、内側 padding 24px
- **トップバー**: 56px、白背景、既存 panel 切替を「タブ風」に再スタイリング（マルチページ化はしない）
- **Provider**: segmented toggle（card 化はしない、YAGNI。card 化は将来 provider が増えた時）
- **Quality**: segmented toggle（Low / High）
- **Aspect ratio**: 6 chip グリッド（3 列 × 2 行）
  - **アイコン領域は 32×32px 固定枠**、各比率の矩形を最大寸法で centering
  - SVG 1 ファイル（`static/img/aspect-icons.svg`）にまとめる
  - 未対応 provider 時は `opacity: 0.4 + cursor: not-allowed`
- **Duration**: chip（5s / 10s）
- **推定コスト**: provider/quality/duration 変更時に capabilities API のデータから計算、CTA 直上表示
- **Generate CTA**:
  - フル幅、高さ 48px、`background: var(--accent)`
  - 送信中 `disabled` + spinner（二重送信防止）
  - 完了/エラー時に enable 復帰
- **メインキャンバス**: 白背景、生成前は空状態メッセージ、生成中はスケルトン + 進捗 %、完了時は動画 player + ダウンロード/承認ボタン
- **エラー表示**: メインキャンバス上部に inline banner（toast ではない）、`role="alert"` 付与
- **最近のジョブ**: メインキャンバス下部に最大 6 枚のサムネイルカード

### 4.10 テンプレート画面（`static/templates.html` 刷新）

- 既存スタイルを破棄して tokens.css ベースに刷新
- 一覧はカードグリッド（各カードに小さなアスペクトプレビュー + provider/quality バッジ）
- 「→ 動画作成」CTA はカード hover 時に表示
- 作成・編集モーダル：
  - **Phase 1 既存 modal 実装の確認タスクを実装計画に含める**
  - 既存無ければ focus trap / Escape close / overlay click close を Phase 2a で初実装
  - 白背景、shadow-md、radius-lg

### 4.11 CSS / JS 構造

- **CSS**: `tokens.css` → `layout.css` → ページ固有 CSS の順で読み込み（全 HTML に 3 行 import）
  - `static/css/tokens.css`（新規）
  - `static/css/layout.css`（新規、共通 top bar / sidebar / cards）
  - `static/css/generate.css`（新規、動画作成画面固有）
  - `static/css/templates.css`（新規、テンプレート画面固有）
  - 既存 `style.css` は panel-pending / panel-confirmed 部分のみ残し、generate / templates 部分は削除
- **JS**:
  - `static/js/generate.js`（既存リファクタ）
    - 起動時 `GET /api/providers/capabilities` で `PROVIDER_SUPPORT` 構築
    - チップ / segmented toggle 操作 → state 更新 → `refreshCostEstimate()`
    - チップ disable は CSS class `.chip--disabled` で制御
    - `?template_id=N` prefill に `default_quality` も含める
  - `static/js/templates.js`（新規 or 既存改修）

### 4.12 アクセシビリティ

- フォームラベルは `<label>` 関連付け
- segmented toggle / chip は `role="radiogroup"` / `role="radio"`
- 推定コスト変更時は `aria-live="polite"`
- エラー banner は `role="alert"`
- キーボードのみで全操作可能

### 4.13 命名コスメティック債務として記録

- Phase 2a では provider 名 `veo3_lite` を維持（後方互換）
- 高品質選択時に内部で veo-3.1-standard を呼ぶため名前と挙動が乖離
- Phase 2b 以降で `veo3` への rename を検討

### 4.14 スコープ外（Phase 2a では含めない）

- ダークモード切替（白基調のみ）
- ロゴ・ブランディング（プレースホルダーで OK）
- 多言語対応（日本語のみ）
- レスポンシブ（PC ブラウザ前提）
- マルチページ化 / 履歴タブ新規実装
- pending grid の `/output/pending/` ハードコード解消
- upload+template モードの空 video_prompt 修正
- 複数クリップ連結（Phase 2b で扱う）

---

## Section 5: Testing strategy

### 5.1 削除するテスト

- `tests/test_video_providers_base.py::test_validate_rejects_1to1_ratio`

### 5.2 追加するテスト

#### Provider 層 (`tests/test_video_providers_base.py`)

```python
def test_validate_rejects_unsupported_quality():
    p = _DummyProvider()
    req = _make_req()
    req.quality = "ultra"
    with pytest.raises(ValueError, match="quality"):
        p.validate(req)

def test_seedance_supports_new_aspects():
    p = SeedanceProvider()
    for aspect in ("1:1", "4:3", "3:4", "21:9"):
        req = _make_req(aspect=aspect)
        p.validate(req)

def test_seedance_calc_cost_low_vs_high():
    p = SeedanceProvider()
    low = _make_req(); low.quality = "low"
    high = _make_req(); high.quality = "high"
    assert p.calc_cost(low) < p.calc_cost(high)
# Veo3 / Kling も同パターン
```

#### API 層 — capabilities エンドポイント

```python
def test_capabilities_endpoint_returns_all_providers():
    resp = client.get("/api/providers/capabilities")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert set(names) == {"seedance", "veo3_lite", "kling3_pro"}

def test_capabilities_includes_rate_map_and_cost_basis():
    resp = client.get("/api/providers/capabilities")
    seedance = next(p for p in resp.json() if p["name"] == "seedance")
    assert seedance["cost_basis"] == "per_second"
    assert "low" in seedance["rate_map"]
    assert "high" in seedance["rate_map"]
    assert "1:1" in seedance["supported_aspects"]
```

#### API 層 — quality (`tests/test_api_generate_extended.py`)

```python
def test_generate_image_with_quality():
    resp = client.post("/api/generate/image", json={
        "image_prompt": "...", "video_prompt": "...",
        "provider": "kling3_pro", "quality": "high",
    })
    job_id = resp.json()["job_id"]
    with db_mod.get_session() as s:
        job = s.get(db_mod.Job, job_id)
        assert job.quality == "high"

def test_generate_image_quality_fallback_to_template():
    cid = client.post("/api/templates", json={
        "name": "T", "category": "custom",
        "image_prompt": "i", "video_prompt": "v",
        "default_provider": "veo3_lite", "default_aspect": "16:9",
        "default_duration": 6, "default_camera_preset": None,
        "default_quality": "high",
    }).json()["id"]
    resp = client.post("/api/generate/image", json={"template_id": cid})
    job_id = resp.json()["job_id"]
    with db_mod.get_session() as s:
        assert s.get(db_mod.Job, job_id).quality == "high"

def test_generate_image_quality_default_low():
    resp = client.post("/api/generate/image", json={
        "image_prompt": "...", "video_prompt": "...",
        "provider": "seedance",
    })
    job_id = resp.json()["job_id"]
    with db_mod.get_session() as s:
        assert s.get(db_mod.Job, job_id).quality == "low"

def test_generate_image_quality_explicit_overrides_template():
    # 明示 quality が template default を上書き
    ...

def test_generate_image_invalid_quality_returns_422():
    resp = client.post("/api/generate/image", json={
        "image_prompt": "...", "video_prompt": "...", "quality": "ultra",
    })
    assert resp.status_code == 422

def test_generate_image_extended_aspects():
    for aspect in ("1:1", "4:3", "3:4", "21:9"):
        resp = client.post("/api/generate/image", json={
            "image_prompt": "...", "video_prompt": "...",
            "provider": "seedance", "aspect_ratio": aspect,
        })
        assert resp.status_code == 200
```

#### Template 層 (`tests/test_api_templates.py`)

```python
def test_template_create_with_default_quality():
    ...

def test_template_update_default_quality():
    # update_template の allowed セットに含まれることを保証
    ...
```

#### approve.py 統合 (`tests/test_api_approve.py`)

```python
def test_approve_writes_provider_cost_basis():
    # Seedance: per_second / Kling: per_video が provider クラス属性経由で書かれる
    ...

def test_approve_passes_quality_to_provider():
    # job.quality が VideoGenRequest.quality として provider に渡る
    ...
```

### 5.3 既存テストの調整

- `test_generate_image_with_extended_params`: 既存アサーションは維持、`assert job.quality == "low"` を追加
- `test_generate_image_with_template_id`: `default_quality` 省略 → default "low" → `Job.quality == "low"` を assert 追加

### 5.4 マイグレーションテスト (`tests/test_alembic_phase2a.py`)

- 空 DB で `alembic upgrade head` → quality / default_quality カラムが NOT NULL で存在
- Phase 1 状態の DB に既存 Job/Template を入れて upgrade → backfill で "low"
- downgrade → 列が消える

### 5.5 手動検証チェックリスト

#### 機能検証

- 6 種アスペクト比すべてで動画生成成功
- low/high 切り替えで Job.quality / video_cost_calc_basis / 内部 model_id が正しい
- Template の default_quality が UI に反映
- 既存 Phase 1 Job が壊れていない（一覧表示・コストサマリー）

#### UI 検証

- 全画面が白背景で表示される
- アスペクト比チップ 6 個が provider 切替に応じて disable される
- Quality segmented toggle が正しく動作
- 推定コストが provider/quality/duration 変更で更新される
- Generate ボタンが送信中 disable + spinner 表示
- エラー時 inline banner が表示される
- a11y: キーボードのみで全操作可能
- a11y: スクリーンリーダーで cost 変更がアナウンスされる
- テンプレート編集モーダルの focus trap / Escape close / overlay click close

---

## 実装着手前の必須確認事項

1. **Seedance "pro" quality**: Atlas Cloud API ドキュメントで正式名と料金を確認
2. **Veo 3.1 standard model ID と料金**: Google AI ドキュメントで確認
3. **Kling V3 std/pro の URL 差異**: MuAPI ドキュメントで確認（QUALITY_MAP の構造が変わる）
4. **既存運用 DB の SQLite バージョン**: ≥ 3.35 必須（`ADD COLUMN NOT NULL DEFAULT` 対応）
5. **Phase 1 modal 実装の有無**: テンプレート編集モーダルの既存資産を調査

---

## Phase 2b 予告（本仕様書のスコープ外）

- 複数クリップの連結機能（FFmpeg 統合 + UI のタイムライン）
- マルチページ化（動画作成 / テンプレート / 履歴の独立ページ）
- pending grid の `/output/pending/` ハードコード解消
- provider 名 `veo3_lite` → `veo3` の rename
