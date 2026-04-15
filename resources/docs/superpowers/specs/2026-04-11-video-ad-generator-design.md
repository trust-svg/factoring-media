# Video Ad Generator — 設計仕様書

**作成日:** 2026-04-11  
**保存先:** `products/video-ad-generator/`  
**目的:** 50代以上向けマッチングアプリのFacebook動画広告を自動生成するツール

---

## 概要

NanoBanana PRO（画像生成）→ Atlas Cloud Seedance 2.0 I2V（動画生成）のパイプラインを FastAPI + Web UIで管理する。初期は手動承認モードで品質を確認し、安定したら `AUTO_APPROVE` フラグで全自動化へ移行する。

---

## 仕様

### 生成パラメータ
- **フォーマット:** 9:16（1080×1920）縦型
- **動画尺:** 10秒
- **本数:** 月10本（バッチ）+ 都度生成（任意）
- **月額コスト目安:** ~$8.30（画像 $0.02×10 + 動画 $0.81×10）

### ABパターン5種
| パターン | テーマ | シチュエーション |
|---|---|---|
| A | ロマンティック系 | 雨の日、カフェ |
| B | 楽しさ系 | 公園、笑顔 |
| C | 信頼感系 | オフィス、落ち着き |
| D | ユーモア系 | おしゃれカフェ、カジュアル |
| E | 真面目系 | 図書館、知性的 |

バッチ生成時はA〜Eから2本ずつ（10本）を生成する。

---

## アーキテクチャ

```
products/video-ad-generator/
├── main.py              # FastAPIエントリーポイント
├── config.py            # 設定（APIキー・AUTO_APPROVE・Bot Token等）
├── requirements.txt
├── .env
│
├── core/
│   ├── image_gen.py     # NanoBanana PRO呼び出し（既存スキルのプロンプトパターンを参照）
│   ├── video_gen.py     # Atlas Cloud Seedance 2.0 I2V呼び出し
│   ├── patterns.py      # ABパターン5種のプロンプト定義
│   └── notifier.py      # Telegram Bot通知（専用Bot）
│
├── api/
│   ├── generate.py      # POST /generate/image, /generate/video
│   ├── approve.py       # POST /approve/{id}, /reject/{id}
│   └── jobs.py          # GET /jobs（一覧・進捗）
│
├── static/              # HTML + CSS + JS（Vanilla、軽量シングルページ）
│
└── output/
    ├── pending/         # 承認待ち画像
    ├── approved/        # 承認済み画像
    ├── rejected/        # 却下済み
    └── videos/          # 完成動画
```

**データストア:** SQLite（ジョブID・ステータス・コスト・プロンプト・パターン・タイムスタンプ）

---

## データフロー

### バッチ生成（月10本）
1. UIで「バッチ生成」ボタン押下 or cronで自動起動
2. `patterns.py` からABパターン×2本ずつプロンプトをピック
3. NanoBanana PRO → 画像生成 → `output/pending/` に保存
4. Telegramに「画像10枚生成完了、承認してください」通知
5. UIで画像一覧を確認 → 承認 or 却下
6. 承認済み画像 → Atlas Cloud Seedance 2.0 I2V → 動画生成
7. 完成動画 → `output/videos/` に保存
8. Telegramに「動画生成完了」通知

### 都度生成（UIから手動）
1. UIでパターン選択 or プロンプト直接入力
2. 「画像生成」ボタン → NanoBanana PRO → `pending/` に保存
3. UIで即座にプレビュー表示
4. 「この画像で動画化」ボタン → Seedance 2.0 I2V
5. 完成 → Telegram通知

### AUTO_APPROVEモード（自動化後）
1. 画像生成まで同じ
2. Claude Vision APIが画像を評価（50代向けマッチングアプリ広告として適切か）
3. スコア閾値以上 → 自動で動画化
4. 閾値以下 → `pending/` に保留 → Telegram通知（手動確認を促す）

### ジョブステータス遷移
```
PENDING → APPROVED / REJECTED → VIDEO_GENERATING → DONE / FAILED
```

---

## Web UI

シングルページ構成（Vanilla JS、タブ切り替え）。

### 画面構成
| エリア | 内容 |
|---|---|
| ダッシュボード | 今月の生成数・コスト・残り枠 |
| 承認待ちグリッド | 画像プレビュー・承認/却下ボタン・プロンプト表示 |
| 都度生成フォーム | パターン選択 + プロンプト編集 + 即時生成 |
| 完成動画一覧 | サムネイル・パターン名・ダウンロード・コスト |
| 設定 | AUTO_APPROVE切り替え・APIキー確認・スコア閾値 |

---

## 外部API

| サービス | 用途 | 認証 |
|---|---|---|
| NanoBanana PRO | 画像生成（9:16、日本人女性） | `NANOBANANA_API_KEY` |
| Atlas Cloud | Seedance 2.0 I2V 動画生成 | `ATLAS_CLOUD_API_KEY` |
| Telegram Bot API | 生成完了通知（専用Bot新規作成） | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` |
| Anthropic API | AUTO_APPROVEモードの画像スコアリング（Claude Vision） | `ANTHROPIC_API_KEY` |

---

## 設定（config.py / .env）

```python
AUTO_APPROVE = False           # True で全自動化モード
AUTO_APPROVE_SCORE_THRESHOLD = 0.75  # Claude自動スコアリング閾値
VIDEO_DURATION = 10            # 秒
VIDEO_ASPECT_RATIO = "9:16"
BATCH_SIZE = 10                # 月バッチ本数
BATCH_CRON = "0 3 * * *"      # 毎日朝3時（手動実行しない場合）
```

---

## エラーハンドリング

- APIエラー（画像・動画）: 最大3回自動リトライ、失敗時はジョブを `FAILED` ステータスに更新 + Telegram通知
- 動画生成タイムアウト: 5分でタイムアウト → リトライキューへ
- 実在人物参照プロンプト: `patterns.py` でブロックワードフィルタ

---

## 将来の拡張（スコープ外・メモ）
- Facebook Ads APIとの連携（CTR自動追跡・成績下位パターン自動淘汰）
- 複数媒体対応（Instagram Reels、TikTok）
- VPSデプロイ（Contabo東京）
