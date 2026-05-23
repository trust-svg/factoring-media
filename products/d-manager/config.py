"""D-Manager configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

_dir = Path(__file__).parent
load_dotenv(_dir / ".env.local")  # Local overrides (if exists)
load_dotenv(_dir / ".env")  # Default .env

# Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
if not DISCORD_BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN must be set")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"  # API mode
# `or` で空文字を default に倒す（os.getenv は env が "" のとき "" を返す Python の罠への対策）
CLAUDE_MODEL_CLI = os.getenv("CLAUDE_MODEL_CLI") or "claude-sonnet-4-6"  # CLI mode
CODE_ENGINE: str = os.getenv("CODE_ENGINE") or "claude"  # "claude" or "codex"

# Google
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

# GitHub (Obsidian sync)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "trust-svg/obsidian-company")

# Company directory
COMPANY_DIR = Path(os.getenv("COMPANY_DIR", str(Path.home() / ".company")))
SECRETARY_DIR = COMPANY_DIR / "secretary"
TODOS_DIR = SECRETARY_DIR / "todos"
INBOX_DIR = SECRETARY_DIR / "inbox"
NOTES_DIR = SECRETARY_DIR / "notes"
DECISIONS_DIR = SECRETARY_DIR / "decisions"
DREAMS_DIR = SECRETARY_DIR / "dreams"
RULES_FILE = SECRETARY_DIR / "rules.md"

# Auto-create directories
for _d in [TODOS_DIR, INBOX_DIR, NOTES_DIR, DECISIONS_DIR, DREAMS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Scheduler
MORNING_BRIEFING_HOUR = int(os.getenv("MORNING_BRIEFING_HOUR", "7"))
MORNING_BRIEFING_MINUTE = int(os.getenv("MORNING_BRIEFING_MINUTE", "30"))
EVENING_REVIEW_HOUR = int(os.getenv("EVENING_REVIEW_HOUR", "21"))
EVENING_REVIEW_MINUTE = int(os.getenv("EVENING_REVIEW_MINUTE", "0"))

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "5225110150")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "1099749992")

# External service URLs (for KPI collection)
EBAY_AGENT_URL = os.getenv("EBAY_AGENT_URL", "")  # https://ebay.trustlink-tk.com
THREADS_AUTO_URL = os.getenv(
    "THREADS_AUTO_URL", ""
)  # https://threads-sho.trustlink-tk.com

# Video Analyzer service (動画分析-video-research チャンネル用)
VIDEO_ANALYZER_URL = os.getenv(
    "VIDEO_ANALYZER_URL", ""
)  # https://video.trustlink-tk.com
VIDEO_ANALYZER_API_KEY = os.getenv("VIDEO_ANALYZER_API_KEY", "")

# Channel-to-department mapping (set after bot connects)
CHANNEL_MAP = {
    # New names (after rename)
    "ceo-steve-general": "secretary",
    "運営-jack-operations": "operations",
    "開発-larry-product": "product",
    "マーケティング-mark-marketing": "marketing",
    "経理-warren-finance": "finance",
    "調査-elon-research": "research",
    "戦略-reid-strategy": "strategy",
    "動画分析-video-research": "research",
    # Old names (fallback until Discord channels are manually renamed)
    "秘書-アイ-general": "secretary",
    "秘書-steve-general": "secretary",
    "運営-リク-operations": "operations",
    "開発-レン-product": "product",
    "マーケティング-ユウ-marketing": "marketing",
    "経理-ケイ-finance": "finance",
    "調査-アキラ-research": "research",
    "戦略-ナオ-strategy": "strategy",
    "アイディア-ideas": "strategy",
    "決裁-decisions": "secretary",
    "アラート-alerts": "secretary",
    "日報-daily-digest": "research",
}

# ── Learning loop ─────────────────────────────────────────────────────────
LEARNING_DIR = Path(__file__).parent / "learning"
LEARNING_DB_PATH = Path(
    os.getenv("LEARNING_DB_PATH", str(LEARNING_DIR / "conversations.db"))
)
SKILL_HITS_PATH = LEARNING_DIR / "skill_hits.jsonl"

# Phase 1=観測のみ: ENABLED=false。Phase 2=ドライラン: ENABLED=true & DRYRUN=true。Phase 3=本番: 両方解除。
LEARNING_REVIEW_ENABLED = (
    os.getenv("LEARNING_REVIEW_ENABLED", "false").lower() == "true"
)
LEARNING_REVIEW_DRYRUN = os.getenv("LEARNING_REVIEW_DRYRUN", "true").lower() == "true"

# 週次キュレーター（weekly_review から呼ばれる）の独立ガード。Reviewer と同じ Phase 設計。
LEARNING_CURATOR_ENABLED = (
    os.getenv("LEARNING_CURATOR_ENABLED", "false").lower() == "true"
)
LEARNING_CURATOR_DRYRUN = os.getenv("LEARNING_CURATOR_DRYRUN", "true").lower() == "true"

LEARNING_REVIEW_HOUR = int(os.getenv("LEARNING_REVIEW_HOUR", "23"))
LEARNING_MIN_TURNS = int(os.getenv("LEARNING_MIN_TURNS", "2"))
LEARNING_MAX_PER_RUN = int(os.getenv("LEARNING_MAX_PER_RUN", "3"))
LEARNING_REVIEW_MAX_AGE_DAYS = int(os.getenv("LEARNING_REVIEW_MAX_AGE_DAYS", "2"))
LEARNING_CONTEXT_CHAR_LIMIT = int(os.getenv("LEARNING_CONTEXT_CHAR_LIMIT", "40000"))
LEARNING_REVIEW_TIMEOUT_SEC = int(os.getenv("LEARNING_REVIEW_TIMEOUT_SEC", "300"))
LEARNING_CURATOR_TIMEOUT_SEC = int(os.getenv("LEARNING_CURATOR_TIMEOUT_SEC", "600"))
LEARNING_STUCK_MINUTES = int(os.getenv("LEARNING_STUCK_MINUTES", "30"))
TURNS_RETENTION_DAYS = int(os.getenv("TURNS_RETENTION_DAYS", "180"))

# レビュー/キュレーター用モデル（CLIモードの --model に渡す）。既定は日次=現行CLIモデル、週次=Opus。
REVIEW_MODEL_CLI = os.getenv("REVIEW_MODEL_CLI") or CLAUDE_MODEL_CLI
CURATOR_MODEL_CLI = os.getenv("CURATOR_MODEL_CLI") or "claude-opus-4-7"

# 学習ループの通知先 Discord チャンネル名（既定: 開発チャンネル）
LEARNING_NOTIFY_CHANNEL = os.getenv("LEARNING_NOTIFY_CHANNEL", "開発-larry-product")

# スキル肥大アラートの閾値
SKILL_BLOAT_CHAR_THRESHOLD = int(os.getenv("SKILL_BLOAT_CHAR_THRESHOLD", "60000"))
SKILL_BLOAT_COUNT_THRESHOLD = int(os.getenv("SKILL_BLOAT_COUNT_THRESHOLD", "25"))

# レビュアー/キュレーターに渡すツール許可リスト（claude -p の --allowedTools / --disallowedTools）
LEARNING_ALLOWED_TOOLS = "Read Write Edit Glob Grep"
LEARNING_DRYRUN_ALLOWED_TOOLS = "Read Glob Grep"
LEARNING_DISALLOWED_TOOLS = "Bash WebFetch WebSearch Task"

# ── Remote Ops ────────────────────────────────────────────────────────────
# Discord の user ID（整数）をカンマ区切りで設定。このIDからのみ ops コマンドを受け付ける。
# 設定例: OWNER_DISCORD_USER_IDS=123456789012345678
OWNER_DISCORD_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in os.getenv("OWNER_DISCORD_USER_IDS", "").split(",")
    if uid.strip().isdigit()
}

# 操作可能なサービス: サービス名 → pkill パターン
OPS_SERVICES: dict[str, str] = {
    "deal-watcher": "Services/deal-watcher/app.py",
}

# ── Knowledge engine（フェーズ1: 議事録化）─────────────────────────────────
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
KNOWLEDGE_DB_PATH = Path(
    os.getenv("KNOWLEDGE_DB_PATH", str(KNOWLEDGE_DIR / "knowledge.db"))
)
# Markdownビューの出力先（.company 配下・別gitリポ。.company/.gitignore で secretary/knowledge/ を除外）
KNOWLEDGE_VIEW_DIR = COMPANY_DIR / "secretary" / "knowledge"

# 安全弁: デフォルト無効。テスト後に KNOWLEDGE_DIGEST_ENABLED=true で本番化。
KNOWLEDGE_DIGEST_ENABLED = (
    os.getenv("KNOWLEDGE_DIGEST_ENABLED", "false").lower() == "true"
)
KNOWLEDGE_DIGEST_HOUR = int(os.getenv("KNOWLEDGE_DIGEST_HOUR", "23"))
KNOWLEDGE_DIGEST_MINUTE = int(os.getenv("KNOWLEDGE_DIGEST_MINUTE", "30"))
KNOWLEDGE_MIN_DIGEST_TURNS = int(os.getenv("KNOWLEDGE_MIN_DIGEST_TURNS", "4"))
KNOWLEDGE_DIGEST_TIMEOUT_SEC = int(os.getenv("KNOWLEDGE_DIGEST_TIMEOUT_SEC", "180"))
KNOWLEDGE_DIGEST_MAX_SESSIONS = int(os.getenv("KNOWLEDGE_DIGEST_MAX_SESSIONS", "20"))
KNOWLEDGE_NOTIFY_CHANNEL = os.getenv("KNOWLEDGE_NOTIFY_CHANNEL", "日報-daily-digest")

# 議事録化の対象から外す通知専用チャンネル。channel_id ベースで除外する。
# 環境変数 KNOWLEDGE_NOTIFICATION_CHANNEL_IDS にカンマ区切りの Discord channel_id を入れる。未設定なら空。
KNOWLEDGE_NOTIFICATION_CHANNEL_IDS = tuple(
    cid.strip()
    for cid in os.getenv("KNOWLEDGE_NOTIFICATION_CHANNEL_IDS", "").split(",")
    if cid.strip()
)
