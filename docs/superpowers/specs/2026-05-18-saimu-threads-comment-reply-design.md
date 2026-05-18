# 設計書: 債務整理タイムズ Threads コメント自動返信システム

**作成日**: 2026-05-18
**ステータス**: 承認済み

## 概要

@saimutimes の Threads 投稿に届いたコメントを30分ごとに検知し、Claude Haiku でケイ視点の返信草案を生成。Telegram inline keyboard で承認後に自動投稿するシステム。

弁護士法72条対応のため、完全自動投稿は行わず必ず人間の承認を挟む。

---

## アーキテクチャ

### 配置

```
products/saimu-media/comment-bot/   ← 新規ディレクトリ
  main.py          # エントリーポイント / APScheduler
  fetcher.py       # Threads API でリプライ取得
  generator.py     # Claude Haiku で返信草案生成
  approver.py      # Telegram Bot 送信 + inline keyboard 処理
  poster.py        # 承認後に Threads API で返信投稿
  state.py         # 返信済みID / pending 管理
  config.py        # 環境変数読み込み
  requirements.txt
  Dockerfile
  docker-compose.yml
```

既存の `sns-engine` コンテナとは分離した独立コンテナとして VPS に追加する。

### データフロー

```
[APScheduler: 30分ごと]
         │
         ▼
    fetcher.py
    直近7日の投稿IDを state から取得
    → Threads API GET /{post_id}/replies
    → 返信済みIDと照合してスキップ
    → pending に未返信コメントを追加
         │
         ▼
    generator.py
    Claude Haiku でケイ視点の返信草案を生成
    → ng_expressions コンプラチェック
    → チェックNGなら破棄（Telegramに警告通知）
         │
         ▼
    approver.py
    Telegram にコメント本文 + 草案 + inline keyboard を送信
    → [✅ 承認して投稿] [❌ 却下] の2ボタン
    → Telegram polling で callback_query を受信
         │
    承認  │  却下
    ───┤├───
    ▼       ▼
poster.py  state.py
Threads    pending から削除
API で     （24時間で自動破棄）
返信投稿
    │
    ▼
state.py
replied_comments.json に ID を記録
```

---

## コンポーネント詳細

### fetcher.py

- Threads API エンドポイント: `GET /{post_id}/replies`
  - 必要な権限: `threads_manage_replies`（既に取得済み）
  - フィールド: `id, text, username, timestamp`
- 監視対象: Threads API `GET /{user_id}/threads` で直近7日分の投稿IDを取得
- 取得後は `state/replied_comments.json` と照合してスキップ

### generator.py

- モデル: `claude-haiku-4-5-20251001`
- `knowledge/persona.json` のケイの人物像・トーン・コンプライアンスルールを参照
- プロンプト方針:
  - 一般論として答える（個別相談にならないよう）
  - 断定表現禁止（「必ず」「絶対に」NG）
  - 不安を煽らない
  - 80〜120字以内
  - 専門家への相談を促す文で締める
- 生成後に `ng_expressions.json` でコンプラチェック
- NG の場合は投稿せず Telegram に警告のみ送信

### approver.py

- 既存の `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` を流用
- Telegram `sendMessage` + `inline_keyboard` で送信:
  ```
  💬 新コメント @{username}
  「{comment_text}」

  📝 返信草案:
  {reply_draft}

  [✅ 承認して投稿]  [❌ 却下]
  ```
- `callback_data` に `approve:{comment_id}` / `reject:{comment_id}` を埋め込む
- Telegram polling (`getUpdates`) で callback_query を受信
- pending は `state/pending_approvals.json` でファイル永続化（コンテナ再起動対応）
- 24時間経過した pending は自動破棄

### poster.py

- `threads_client.py` の `reply_to_thread(reply_to_id, text)` を呼び出す
- 投稿成功後に Telegram へ完了通知
  ```
  ✅ 返信投稿しました
  @{username} への返信: {reply_text[:50]}...
  ```

### state.py

```json
// replied_comments.json
{
  "replied": ["comment_id_1", "comment_id_2", ...]
}

// pending_approvals.json
{
  "pending": [
    {
      "comment_id": "xxx",
      "post_id": "yyy",
      "comment_text": "...",
      "reply_draft": "...",
      "telegram_message_id": 12345,
      "created_at": "2026-05-18T10:00:00+09:00"
    }
  ]
}
```

---

## スケジュール

| ジョブ | 実行タイミング | 説明 |
|--------|--------------|------|
| `job_check_comments` | 30分ごと | コメント取得 → 生成 → Telegram通知 |
| `job_cleanup_pending` | 1時間ごと | 24時間超の pending を自動破棄 |
| `telegram_polling` | 常時（バックグラウンド） | callback_query の受信ループ |

---

## 環境変数

既存の `saimu-media/.env` に追記:

```
# Threads（既存）
THREADS_ACCESS_TOKEN=...
THREADS_USER_ID=...

# Telegram（既存）
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Anthropic（既存）
ANTHROPIC_API_KEY=...
```

新規追加なし。既存の `.env` を参照する。

---

## Docker 構成

```yaml
# docker-compose.yml に追加
services:
  saimu-comment-bot:
    build: ./comment-bot
    container_name: saimu-comment-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - TZ=Asia/Tokyo
    volumes:
      - ./comment-bot/state:/app/state
      - ./knowledge:/app/knowledge:ro
```

---

## エラーハンドリング

| ケース | 対応 |
|--------|------|
| Threads API エラー | ログ記録、次回ポーリングで再試行 |
| Claude API エラー | ログ記録、当該コメントをスキップ |
| コンプラ NG | Telegram に警告通知、投稿しない |
| Telegram 送信失敗 | pending に保持、次回再送試み |
| 24時間 pending 期限切れ | 自動破棄、Telegram に期限切れ通知 |

---

## 制約・注意事項

- 弁護士法72条対応: 個別相談に踏み込む草案はコンプラチェックで除外
- Threads トークン期限: 2026-07-08 ごろ切れる（要 refresh_access_token 実装）
- ネストしたコメント（返信への返信）は対象外とする（直接リプライのみ）
- 1コメントに対して1返信のみ（重複投稿防止）
