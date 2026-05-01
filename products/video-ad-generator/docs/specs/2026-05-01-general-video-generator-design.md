# 汎用動画ジェネレーター拡張設計

**作成日**: 2026-05-01
**作成者**: Hiro + Claude
**ステータス**: 設計レビュー待ち
**前提**: Higgsfield 代替を自前で構築する

---

## 1. ゴール

現状の `video-ad-generator`（マッチングアプリ広告専用、固定5パターン、Seedance 2.0 のみ）を、**画像 + 自由プロンプトで任意の動画を生成できる汎用ツール**に拡張する。Higgsfield のサブスク（月$9〜$49）を不要にすることが商業的ゴール。

## 2. スコープ判断

**単一スペックで扱う範囲**: Phase 1（基本拡張）のみ。

Phase 2-4 は Phase 1 完成後に別スペックを書く。これは brainstorming スキルの「複数の独立したサブシステムは別スペックに分割する」に従う判断。Phase 1 だけでも単独で使える完成品として動く必要がある。

| Phase | 内容 | 本スペックの対象 |
|---|---|---|
| **Phase 1** | 自由入力 + テンプレ + カメラプリセット + Seedance/Veo3 Lite/Kling3 Pro 対応 | ✅ 本スペック |
| Phase 2 | Runway Gen-4 Turbo / Sora 2 等の追加モデル統合 | ❌ 別スペック |
| Phase 3 | キャラクター一貫性（参照画像 multi-shot） | ❌ 別スペック |
| Phase 4 | シーン連続性（last-frame 抽出 → 次シーン I2V） | ❌ 別スペック |

## 3. アーキテクチャ概要

**現状（変更前）:**
```
[固定5パターン] → NanoBanana PRO → 画像 → 承認 → Seedance 2.0 → 動画
```

**Phase 1（変更後）:**
```
[テンプレDB or 自由入力] ──┐
                          ├→ 画像生成 OR 既存画像アップロード
                          │   └→ NanoBanana PRO
                          │
                          └→ ジョブ作成 → 承認 →
                              └→ モデル選択 (Seedance / Veo3 Lite / Kling3 Pro)
                                  └→ Telegram 経由で画像URL取得
                                      └→ I2V API → 動画
```

**主要な構造変更:**
1. `core/patterns.py` の固定 dict → DB 駆動のテンプレ + 自由入力パス
2. `core/video_gen.py` 単一プロバイダー → `core/video_providers/` ディレクトリ + 抽象 `VideoProvider` クラス
3. UI: 「都度生成」タブ → 「動画作成」フォーム（プロンプト/aspect/duration/モデル/カメラ動作の自由選択）
4. 新タブ: 「テンプレ管理」（CRUD）

## 4. 技術スタック（変更点）

| 領域 | 現状 | Phase 1 |
|---|---|---|
| 画像生成 | NanoBanana PRO のみ | NanoBanana PRO + アップロード対応 |
| 動画生成 | Seedance 2.0（muapi.ai） | + Veo 3.1 Lite（Gemini API直）+ Kling V3.0 Pro（muapi.ai経由） |
| DB | SQLite + SQLAlchemy（変更なし） | + `templates` テーブル + `Job` の列追加 |
| UI | static/index.html 1枚 | + テンプレ管理画面 + 拡張フォーム |
| 認証 | なし | なし（個人利用前提を維持） |

## 5. データモデル

### 5.1 既存 `jobs` テーブルへの列追加

```python
class Job(Base):
    # ... 既存列 ...
    template_id: Mapped[int | None]            # NULL = 自由入力ジョブ、それ以外 = テンプレ参照
    provider: Mapped[str]                      # "seedance" / "veo3_lite" / "kling3_pro"
    aspect_ratio: Mapped[str]                  # "9:16" / "16:9" / "1:1"
    duration_seconds: Mapped[int]              # 4 / 5 / 6 / 8 / 10（モデル依存。 §7 の対応表参照）
    camera_preset: Mapped[str | None]          # "static" / "dolly_in" / "pan_left" / ... NULL = 指定なし
    image_source: Mapped[str]                  # "generated" (NanoBananaで生成) / "uploaded" (ユーザー手動)
    video_progress_stage: Mapped[str | None]   # 中間状態の可視化用（後述 §5.4）
    video_cost_calc_basis: Mapped[str | None]  # "per_second" / "per_video"（コスト計算根拠の保持）
    # 既存 pattern 列は段階的にdeprecate（NULL許容に変更、最終的にtemplate_idへ移行）
    # 既存 video_cost_usd は流用（プロバイダーごとに料金計算ロジックは §13.1 参照）
```

`pattern` 列は **NULL 許容に変更**するが削除はしない（既存データを壊さないため）。

### 5.2 新規 `templates` テーブル

```python
class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int]
    name: Mapped[str]                    # "ロマンティック女性@カフェ" 等
    category: Mapped[str]                # "matching_ad" / "sns_post" / "product_showcase" / "custom"
    image_prompt: Mapped[str]
    video_prompt: Mapped[str]
    default_provider: Mapped[str]        # "seedance" 等
    default_aspect: Mapped[str]          # "9:16" 等
    default_duration: Mapped[int]        # 10 等
    default_camera_preset: Mapped[str | None]
    is_archived: Mapped[bool]            # 廃止フラグ（履歴を残しつつ非表示）
    created_at / updated_at: Mapped[datetime]
```

**初期データ**: 既存 `PATTERNS` の5件を `category="matching_ad"` でシードする（既存運用を壊さない）。

### 5.3 カメラプリセット（コード内定義、DB保存しない）

`core/camera_presets.py` に定義。プロバイダーごとに「Klingは数値パラメータ／Seedance・Veo3はプロンプト埋め込み」を分岐する責務を持つ。

```python
CAMERA_PRESETS = {
    "static":     {"label": "固定", "kling": {}, "prompt_hint": ""},
    "dolly_in":   {"label": "ドリーイン",   "kling": {"zoom": 5},   "prompt_hint": "slow dolly-in toward subject"},
    "dolly_out":  {"label": "ドリーアウト", "kling": {"zoom": -5},  "prompt_hint": "slow dolly-out away from subject"},
    "pan_left":   {"label": "左パン",       "kling": {"pan": -5},   "prompt_hint": "smooth pan left"},
    "pan_right":  {"label": "右パン",       "kling": {"pan": 5},    "prompt_hint": "smooth pan right"},
    "tilt_up":    {"label": "上ティルト",   "kling": {"tilt": 5},   "prompt_hint": "tilt up gently"},
    "orbit_left": {"label": "左オービット", "kling": {"horizontal": -5}, "prompt_hint": "camera orbits left around subject"},
}
```

**判断**: Phase 1では**7プリセット**に絞る。Higgsfield の 50+ プリセットは Phase 2 以降で順次追加。

### 5.4 ジョブステータスの中間状態

既存の `JobStatus` enum（`PENDING / APPROVED / REJECTED / VIDEO_GENERATING / DONE / FAILED`）は変更せず、`Job.video_progress_stage: str | None` で **`VIDEO_GENERATING` 中の細分化**を表現する。

```python
# core/video_providers/__init__.py で定義
PROGRESS_STAGES = (
    "uploading_image",      # Telegramへの画像アップロード中
    "submitting",           # プロバイダーAPIへジョブ投入中
    "polling",              # ステータスポーリング中
    "downloading_video",    # 完成動画のダウンロード中
)
```

各プロバイダー実装は段階遷移時に `Job.video_progress_stage` を更新する。UI 側はジョブ一覧で `[VIDEO_GENERATING / polling] 残り 2分` のように合成表示。

**判断**: enum を増やすと既存マイグレーションへの影響が大きい。文字列カラムにすることでプロバイダー固有の段階追加にも柔軟に対応。

## 6. ファイル構造

### 新規作成
- `core/video_providers/__init__.py` — `VideoProvider` 抽象クラス + `get_provider(name)` ファクトリ
- `core/video_providers/seedance.py` — 既存 `video_gen.py` のロジック移植
- `core/video_providers/veo3.py` — Gemini API 経由の Veo 3.1 Lite 実装
- `core/video_providers/kling.py` — muapi.ai 経由の Kling V3.0 Pro 実装（カメラ数値パラメータ対応）
- `core/camera_presets.py` — 上記プリセット定義 + `apply_to_payload(provider, preset, payload)` ユーティリティ
- `core/templates.py` — テンプレ CRUD ロジック（DB アクセス）
- `api/templates.py` — `/api/templates` CRUD ルーター
- `api/upload.py` — `/api/upload-image` エンドポイント（既存画像をアップロードしてジョブ化）
- `static/templates.html` — テンプレ管理画面
- `tests/test_video_providers.py` — 各プロバイダーのモックテスト
- `tests/test_camera_presets.py`
- `tests/test_templates.py`
- `migrations/001_add_templates_and_job_fields.py` — Alembic マイグレーション（後述）

### 変更
- `core/video_gen.py` — `seedance.py` に移譲する thin wrapper にダウングレード（後方互換のため残すが、新規呼び出しは providers 経由）
- `core/patterns.py` — `PATTERNS` dict は残しつつ「シードデータの定義場所」と再位置付け、`get_batch_prompts()` は templates テーブル経由に変更
- `database.py` — `Template` モデル追加 + `Job` 列追加
- `api/generate.py` — 自由入力＋プロバイダー選択を受け付けるよう拡張
- `static/index.html` — フォーム拡張＋テンプレ管理リンク追加
- `requirements.txt` — `alembic`, `google-genai`（既存）追加確認、追加が必要なら明記
- `config.py` — `GEMINI_API_KEY`（既存）/ `MUAPI_KLING_MODEL_ID` 等の追加

### 削除
なし（既存資産はすべて Phase 1 段階で温存）。

## 7. プロバイダー抽象化

```python
# core/video_providers/__init__.py
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass

@dataclass
class VideoGenRequest:
    image_path: Path
    video_prompt: str
    aspect_ratio: str           # "9:16" / "16:9" / "1:1"
    duration_seconds: int       # 5 or 10
    camera_preset: str | None   # camera_presets.py のキー
    output_path: Path

class VideoProvider(ABC):
    name: str
    supported_aspects: tuple[str, ...]
    supported_durations: tuple[int, ...]

    @abstractmethod
    async def generate(self, req: VideoGenRequest) -> Path: ...

    def validate(self, req: VideoGenRequest) -> None:
        if req.aspect_ratio not in self.supported_aspects:
            raise ValueError(f"{self.name} does not support {req.aspect_ratio}")
        if req.duration_seconds not in self.supported_durations:
            raise ValueError(f"{self.name} does not support {req.duration_seconds}s")
```

各プロバイダー実装:

| プロバイダー | エンドポイント | アスペクト対応 | duration対応 | カメラ制御 |
|---|---|---|---|---|
| `seedance`   | muapi.ai I2V（既存） | 9:16, 16:9 | 5, 10 | プロンプト埋め込み |
| `veo3_lite`  | Gemini API `models/veo-3.1-fast-generate-001:generateVideo` | 16:9, 9:16 | 4, 6, 8 | プロンプト埋め込み |
| `kling3_pro` | muapi.ai Kling V3.0 Pro | 9:16, 16:9, 1:1 | 5, 10 | **数値パラメータ + プロンプト埋め込み**（pan/tilt/zoom等） |

**注**: Veo 3.1 は **8秒固定が referenceImage 使用時の制約**。Phase 1 では reference 未使用なので 4/6/8 秒選択可。UI 側で provider に応じた duration オプションを動的に出し分ける。

### 7.1 エラーハンドリング統一仕様

**全プロバイダー共通の規約**を `VideoProvider` 基底クラスで強制する:

| 項目 | 値 | 理由 |
|---|---|---|
| 投入リトライ回数 | **3回**（既存 `video_gen.py` 踏襲） | Atlas Cloud / Gemini / muapi.ai のいずれも瞬間障害が起きうる |
| リトライ間隔 | 10秒固定（指数バックオフは Phase 2） | 既存実装と整合 |
| ポーリング間隔 | 15秒固定 | 既存実装と整合 |
| ポーリング全体タイムアウト | **900秒（15分）** | Veo 3.1 は最大6分、Klingは最大3分が公称値 |
| ネットワークエラー扱い | リトライ対象 | `httpx.RequestError`、5xx |
| 認証/課金エラー扱い | **即時失敗**（リトライしない） | 401/402/403 |
| バリデーションエラー扱い | 即時失敗 | 4xx（402/429除く） |
| 429 (Rate Limit) | 30秒待機後リトライ × 3回 | プロバイダー側のクールダウン尊重 |

失敗時は `Job.status = FAILED`, `Job.error_message` に最後の例外文字列（最大1000文字）。`video_progress_stage` は失敗時の段階を保持（デバッグ用）。

**ユーザー通知**: 既存 `core/notifier.py` の Telegram 通知に「失敗時、どの段階で落ちたか」を含める（`uploading_image / submitting / polling / downloading_video`）。

### 7.2 環境変数 (.env) 追加項目

| キー | 必須 | 用途 | 既定値 |
|---|---|---|---|
| `GEMINI_API_KEY` | ✅（既存） | NanoBanana PRO + Veo 3.1 Lite 両用 | — |
| `ATLAS_CLOUD_API_KEY` | ✅（既存） | muapi.ai（Seedance + Kling 共通の API キー） | — |
| `MUAPI_KLING_MODEL_ID` | ✅（新規） | Kling V3.0 Pro のモデルID（muapi.ai の playground で確認） | — |
| `MUAPI_KLING_I2V_URL` | ✅（新規） | Kling 専用 endpoint（既存 `ATLAS_CLOUD_I2V_URL` とは別ルート） | `https://api.muapi.ai/api/v1/kling-v3-pro-i2v`（暫定。実装時に最終確認） |
| `VEO3_MODEL_ID` | ⚠️ | Veo 3.1 Lite モデルID（変更可能性あり） | `veo-3.1-fast-generate-001` |
| `VEO3_LOCATION` | ⚠️ | Vertex AI 経由の場合のリージョン | `us-central1`（Gemini API直の場合は不要） |
| `DEFAULT_PROVIDER` | ⚠️ | UI のデフォルト選択 | `seedance` |
| `MAX_UPLOAD_SIZE_MB` | ⚠️ | アップロード画像の最大サイズ | `20` |

`.env.example` を本番値ではなくダミー値で更新する（コミット対象）。

**判断**: muapi.ai の Kling endpoint URL は本実装時に muapi.ai の API ドキュメントで再確認する。暫定値を変更したらこのスペックの当該行も追記する。

## 8. UI 変更

### 8.1 メイン画面 `static/index.html`

新タブ構成:

| タブ | 役割 |
|---|---|
| バッチ生成 | 既存（5パターン×2本） — マッチングアプリ広告専用フローとして残す |
| **動画作成**（旧「都度生成」をリネーム） | **新フォーム**: テンプレ選択 / 自由入力 / 画像アップロード / モデル / アスペクト / duration / カメラプリセット |
| ジョブ一覧 | 既存（DB 列追加分を表示） |
| **テンプレ管理**（新規） | `templates.html` への遷移 |

「動画作成」フォームの項目:
1. **入力モード**: ラジオ「テンプレから」/「自由入力」
2. **テンプレ選択**（テンプレモード時）: カテゴリフィルタ + テンプレ一覧
3. **画像プロンプト**（自由入力時、編集可）
4. **動画プロンプト**（編集可）
5. **画像ソース**: ラジオ「NanoBanana で生成」/「アップロード」
6. **動画モデル**: セレクト（seedance / veo3_lite / kling3_pro）
7. **アスペクト**: セレクト（モデルに応じて動的）
8. **duration**: セレクト（モデルに応じて動的）
9. **カメラ動作**: セレクト（7プリセット + なし）

### 8.2 テンプレ管理 `static/templates.html`

- 一覧表示（カテゴリフィルタ、archived も表示切替可）
- 新規作成・編集モーダル（image_prompt / video_prompt / カテゴリ / デフォルト各種）
- 削除（実際は `is_archived=True` でソフトデリート、復元可能）
- **「このテンプレで動画作成」ボタン** → 「動画作成」タブに遷移して値を pre-fill

## 9. API エンドポイント変更

| メソッド | パス | 変更 | 用途 |
|---|---|---|---|
| POST | `/api/generate/batch` | 変更なし | 既存バッチ |
| POST | `/api/generate/image` | **拡張**: `provider`, `aspect_ratio`, `duration`, `camera_preset`, `image_source`, `template_id`, `custom_image_prompt`, `custom_video_prompt` を受け付ける | 単発生成 |
| **POST** | `/api/upload-image` | **新規**（仕様は §9.1） | 既存画像のアップロード→ジョブ作成（image_source=uploaded） |
| **GET** | `/api/templates` | **新規** | テンプレ一覧（カテゴリフィルタ・archived フィルタ） |
| **POST** | `/api/templates` | **新規** | テンプレ作成 |
| **PATCH** | `/api/templates/{id}` | **新規** | テンプレ更新 |
| **DELETE** | `/api/templates/{id}` | **新規**（ソフトデリート） | テンプレアーカイブ |
| POST | `/api/approve/{id}` | **拡張**: 承認時に `Job.provider` を見て対応するプロバイダーを呼ぶ | 承認 → 動画生成 |

### 9.1 `/api/upload-image` 仕様

**multipart/form-data**:
- `file`: 画像ファイル（必須）
- `video_prompt`: 動画プロンプト（必須）
- `provider`: モデル選択（必須）
- `aspect_ratio`, `duration_seconds`, `camera_preset`: 動画生成パラメータ
- `template_id`: 任意（テンプレ参照ジョブ化したい場合）

**バリデーション**:
| 項目 | ルール | 不適合時 |
|---|---|---|
| 拡張子 | `.jpg / .jpeg / .png` のみ | 400 `"対応形式は jpg/png のみ"` |
| MIME type | `image/jpeg / image/png` のみ（中身検証） | 400 `"画像ファイルではありません"` |
| サイズ上限 | `MAX_UPLOAD_SIZE_MB`（既定20MB） | 413 `"画像が大きすぎます（最大{N}MB）"` |
| 解像度 | 最小 256×256、最大 4096×4096 | 400 `"解像度は256〜4096pxの範囲"` |
| アスペクト | クライアント指定 `aspect_ratio` と画像実アスペクトが ±10% 以上ズレる場合 | 警告のみ（プロバイダー側でクロップ） |

**保存先**: `output/uploaded/{job_id}.{ext}` に保存後、`Job.image_path` にセット。NanoBanana 生成画像と同じ `PENDING_DIR` には置かない（後の cleanup 処理で区別するため）。

**判断**: 画像内容のセーフティチェック（NSFW検知等）は Phase 1 ではしない。個人利用のため。

## 10. マイグレーション戦略

SQLite + SQLAlchemy で稼働中の本番 DB（`video_ad.db`）を壊さないため、**Alembic を導入**する。

- 初回マイグレーション: 既存スキーマからの差分（`templates` テーブル新設 + `jobs` 列追加）
- `pattern` 列は NULL 許容に変更し、既存レコードは触らない
- 既存5パターンを `templates` テーブルにシード（マイグレーション内で行う）

**判断**: Alembic は overkill に見えるが、後の Phase で何度もスキーマが変わるため今のうちに導入。

### 10.1 ロールバック手順

マイグレーション失敗 or 動作不良時の復旧手順を明示:

```bash
# 1. 事前バックアップ（マイグレーション前に必ず実行）
cp video_ad.db video_ad.db.bak.$(date +%Y%m%d_%H%M%S)

# 2. マイグレーション失敗時 — Alembic で1段階戻す
alembic downgrade -1

# 3. Alembic だけでは復旧できない場合（テンプレシード途中で失敗等）
mv video_ad.db video_ad.db.broken
cp video_ad.db.bak.<タイムスタンプ> video_ad.db
# サーバー再起動

# 4. video_ad.db.bak が存在しない場合（最終手段）
rm video_ad.db
python -c "from database import init_db; init_db()"
# 既存ジョブは消えるが、新規スキーマで再開可能
```

`migrations/run.sh` に上記をスクリプト化（`backup` / `migrate` / `rollback` サブコマンド）。**マイグレーションは必ず `migrations/run.sh migrate` 経由で実行する**ルールにする（直接 `alembic upgrade head` を打たない）。

## 11. 認証 / セキュリティ

**変更なし。** 個人ローカル利用前提（`localhost:8004`）。本番VPSデプロイは Phase 2 以降の判断とする。

ブロックワード（実在人物名）は既存の `_BLOCK_WORDS` を `core/patterns.py` から `core/safety.py` に移して、テンプレ作成時にも適用。

## 12. テスト戦略

**新規テスト:**
- `tests/test_video_providers.py` — 各プロバイダーの `validate()` と `generate()`（HTTPレイヤーは monkeypatch でモック）
- `tests/test_camera_presets.py` — `apply_to_payload()` がプロバイダーごとに正しく分岐するか
- `tests/test_templates.py` — CRUD ロジック（DB は in-memory SQLite）
- `tests/test_api_templates.py` — エンドポイント動作（FastAPI TestClient）

**統合テスト**: 既存の `test_api.py` を拡張して、新しい `/api/generate/image` の引数バリエーションをカバー。

**E2E（手動）**: 各プロバイダーで実際に1本ずつ動画生成して目視確認（Veo3 Lite、Kling3 Pro はAPIキー未取得のため初回手動）。

## 13. コスト見積（Phase 1完了時）

開発時のテストコスト（10秒動画ベース）:
- Seedance 2.0: 既知（muapi.ai）
- Veo 3.1 Lite: $0.05/秒 × 8秒 = **$0.40/本**
- Kling V3.0 Pro: 約 **$0.46/本**（muapi.ai 経由）

開発全体で各プロバイダー10本程度試すと仮定 → **約 $10〜15** で完了見込み。

### 13.1 コスト追跡実装

`Job.video_cost_usd`（既存）に**毎ジョブの実コストを記録**する。各プロバイダーの料金体系が異なるため、`VideoProvider.calc_cost(req: VideoGenRequest) -> float` を抽象メソッドとして実装させる:

| プロバイダー | 計算ロジック | `video_cost_calc_basis` |
|---|---|---|
| `seedance` | 動画単価（muapi.ai 表示の単価×1） | `"per_video"` |
| `veo3_lite` | `$0.05 × duration_seconds` | `"per_second"` |
| `kling3_pro` | 動画単価（V3.0 Pro 固定単価） | `"per_video"` |

**集計エンドポイント**:
- `GET /api/jobs/cost-summary?from=YYYY-MM-DD&to=YYYY-MM-DD` — 期間内の合計と provider 別内訳を返す
- UI のジョブ一覧画面下部に「今月: $X.XX（seedance: $A / veo3_lite: $B / kling3_pro: $C）」を表示

**判断**: muapi.ai 上の実際の課金額と乖離する可能性があるため、表示時に「概算（muapi.ai ダッシュボード参照）」と明記する。Phase 2 で muapi.ai の billing API を統合できれば実額に置き換え。

## 14. リスクと懸念点

| リスク | 影響 | 緩和策 |
|---|---|---|
| Gemini API の Veo 3.1 が日本リージョンで利用制限される可能性 | 中 | 利用不可と判明した時点で muapi.ai 経由の Veo に切替え（Phase 1 では自動 fallback ロジックは実装しない。手動切替で十分） |
| Kling のカメラ数値パラメータの仕様が変わる | 中 | muapi.ai のドキュメントを定期確認、エラー時にプロンプト埋め込みへフォールバック |
| Alembic 導入時の既存 DB との不整合 | 低-中 | 初回マイグレーション前に `video_ad.db` を `video_ad.db.bak` にバックアップする手順をスクリプト化 |
| 既存ユーザー（Hiro自身）のフローが壊れる | 高 | 既存「バッチ生成」タブと固定5パターンのバッチ動作は touched しない。新タブのみで開発 |
| Higgsfield特有の「Bullet Time」等が再現できない | 中 | Phase 1では割り切り。Phase 2-3 でモデル追加時に再評価 |

## 15. 受け入れ基準（Phase 1 完成の定義）

以下すべてが満たされた時点で Phase 1 完了:

- [ ] 既存「バッチ生成」が引き続き動く（回帰なし）
- [ ] 「動画作成」タブで自由プロンプト + 自由パラメータで動画を生成できる
- [ ] 既存画像のアップロード→動画生成パスが動く
- [ ] テンプレを作成・編集・アーカイブできる
- [ ] テンプレから「動画作成」へ pre-fill 遷移できる
- [ ] Seedance / Veo 3.1 Lite / Kling V3.0 Pro の3モデルすべてで動画生成成功
- [ ] カメラプリセット 7種が Kling では数値パラメータで、他はプロンプト埋め込みで動作する
- [ ] pytest 全パス、新規追加テストが書かれている
- [ ] エラーハンドリング統一仕様（§7.1）が全プロバイダーで実装され、認証/課金エラーで即時失敗・ネットワークエラーでリトライすることをテストで検証
- [ ] アップロード API（§9.1）のバリデーションが全パターン実装済み
- [ ] `Job.video_progress_stage` がジョブ一覧 UI に表示される
- [ ] `GET /api/jobs/cost-summary` が動作し、UI で月次コストが見える
- [ ] `migrations/run.sh` の backup/migrate/rollback が手元で動作確認済み
- [ ] `.env.example` が新キー（§7.2）で更新されている

## 16. 非ゴール（明示的にやらないこと）

- VPS デプロイ
- ユーザー認証
- 課金機能
- 公開サービス化
- キャラクター一貫性（Phase 3）
- シーン連続性（Phase 4）
- Higgsfield 特殊カメラ（Bullet Time等）の完全再現
- バッチ生成の汎用化（既存マッチング広告専用バッチは温存）
