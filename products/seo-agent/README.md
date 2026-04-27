# SEO Agent — 横断SEO司令塔

Hiroさんが運営する複数アフィリエイト媒体（FACCEL / 債務整理タイムズ）のSEOを横断管理する週次自動エージェント。

- GSC API から過去28日のクエリ別パフォーマンス取得
- 順位5〜20位の「あと一歩」KWを抽出 → 上昇 / 停滞 / 下落の3カテゴリに分類
- Markdown レポートを `reports/YYYY-MM-DD/{site}.md` に出力
- Telegram に要約通知
- **Claude API は呼ばない** — Hiroさんが手動でClaude Codeを開いてレポートを食わせる運用

## 仕組み

```
weekly cron (Mon 8:00 JST, VPS)
   ↓
weekly_report.py
   ↓
GSC API → SQLite → Markdown report → Telegram notify
   ↓
Hiroさんが手動で claude を起動して @reports/.../faccel.md を食わせる
```

## セットアップ

### 1. Phase 0: GSC とOAuthの準備（Hiroさん作業）

- GSC で `sc-domain:faccel.jp` と `sc-domain:saimu-times.com` を登録（DNS TXT認証）
- Google Cloud Console で OAuth Client (Desktop App) 作成、Webmasters scope を有効化
- `client_secret_*.json` をダウンロードして `credentials/gsc_oauth.json` にリネーム保存

### 2. ローカルで OAuth bootstrap

```bash
cd products/seo-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example.txt .env  # TELEGRAM_BOT_TOKEN を設定
python -m core.gsc_auth   # ブラウザが開く → 承認
# → credentials/gsc_token.json が生成される
```

### 3. ローカルで dry-run

```bash
FACCEL_CONTENT_DIR=$PWD/../factoring-media/content/articles \
SAIMU_CONTENT_DIR=$PWD/../saimu-media/site/content \
GSC_CREDENTIALS_PATH=$PWD/credentials/gsc_oauth.json \
GSC_TOKEN_PATH=$PWD/credentials/gsc_token.json \
DB_PATH=$PWD/data/seo.db \
REPORTS_DIR=$PWD/reports \
python jobs/weekly_report.py --dry-run
```

→ `reports/dry-run/{faccel,saimu_times}.md` が生成される（Telegram通知なし）

### 4. VPS デプロイ

```bash
# VPS に同期
rsync -avz --exclude=venv --exclude=.env products/seo-agent/ vps:/opt/seo-agent/
scp .env credentials/gsc_oauth.json credentials/gsc_token.json vps:/opt/seo-agent/credentials/

# VPS 上で起動
ssh vps
cd /opt/seo-agent
docker compose build
docker compose up -d
docker compose run --rm seo-agent python jobs/weekly_report.py  # 初回手動実行
```

### 5. レポート同期（毎週月曜の朝）

```bash
# Mac 側
scp -r vps:/opt/seo-agent/reports/$(date +%F) ~/seo/reports/
claude  # → @~/seo/reports/2026-04-27/faccel.md を食わせてリライト依頼
```

## ファイル構成

```
seo-agent/
├── core/
│   ├── sites.py        # Site Protocol + Article dataclass
│   ├── gsc_client.py   # GSC API + OAuth
│   ├── gsc_auth.py     # 初回 OAuth bootstrap CLI
│   ├── db.py           # SQLite (rank_history, report_runs)
│   ├── analyzer.py     # 5〜20位 KW 抽出 + 3カテゴリ分類
│   ├── report.py       # Markdown / Telegram フォーマッタ
│   └── notifier.py     # Telegram POST
├── sites/
│   ├── faccel.py       # FACCEL アダプタ (Next.js + MD)
│   └── saimu_times.py  # 債務整理タイムズ アダプタ (Hugo + MD)
├── jobs/
│   └── weekly_report.py
├── tests/
│   ├── test_analyzer.py
│   └── test_sites.py
├── docker/
│   ├── crontab
│   └── entrypoint.sh
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## チューニング

`.env` の以下で挙動調整可能:

- `MIN_IMPRESSIONS=50` — ノイズ除外
- `POSITION_MIN=5.0` / `POSITION_MAX=20.0` — 「あと一歩」レンジ
- `LOOKBACK_DAYS=28` — GSC データ取得期間

## トークン消費

cron 自体は **Claude API を一切呼ばない**（Python のみ）。Claude を消費するのは:

- Hiroさんが Mac で `claude @reports/.../faccel.md` を食わせた時のみ
- 記事リライトを依頼した時のみ

## テスト

```bash
pytest tests/ -q
```

## Phase 2 以降

- AEO最適化チェッカー (FAQPage / HowTo 構造化データ自動チェック)
- ChatGPT/Perplexity 引用最適化スコアリング
- 競合スクレイピング (Phase 4 で慎重に)
