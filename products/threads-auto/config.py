"""設定管理 — 環境変数から読み込み"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Threads API ---
THREADS_ACCESS_TOKEN: str = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID: str = os.getenv("THREADS_USER_ID", "")
THREADS_APP_ID: str = os.getenv("THREADS_APP_ID", "")
THREADS_APP_SECRET: str = os.getenv("THREADS_APP_SECRET", "")

# --- Anthropic ---
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

# --- Telegram通知 ---
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "323107833")

# --- YouTube Data API ---
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

# --- 投稿設定 ---
MAX_POSTS_PER_DAY: int = int(os.getenv("MAX_POSTS_PER_DAY", "10"))
MIN_POST_INTERVAL_MINUTES: int = int(os.getenv("MIN_POST_INTERVAL_MINUTES", "60"))
QUALITY_THRESHOLD: float = float(os.getenv("QUALITY_THRESHOLD", "7.0"))
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))

# --- タイムスロット（JST） ---
POST_TIMESLOTS: list[str] = [
    "08:00", "10:00", "12:00", "13:30",
    "15:00", "17:00", "19:00", "20:30",
    "22:00", "24:00",
]

# --- パス ---
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
STATE_DIR = BASE_DIR / "state"

# --- DRY RUN ---
DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"

# --- KILL SWITCH ---
KILL_SWITCH_FILE = STATE_DIR / "KILL_SWITCH"

# --- Notion連携（コンテンツカレンダー） ---
NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
NOTION_CALENDAR_DB_ID: str = os.getenv("NOTION_CALENDAR_DB_ID", "")

# --- サーバー ---
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8001"))
PUBLIC_URL: str = os.getenv("PUBLIC_URL", "")
