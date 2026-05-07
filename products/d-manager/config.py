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
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # API mode
CLAUDE_MODEL_CLI = os.getenv("CLAUDE_MODEL_CLI", "claude-sonnet-4-20250514")  # CLI mode

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
    "決裁-decisions": "secretary",
    "アラート-alerts": "secretary",
    "日報-daily-digest": "research",
}
