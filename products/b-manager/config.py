import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "b-manager-webhook-secret")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Google
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")

# Company directory
COMPANY_DIR = Path(os.getenv("COMPANY_DIR", str(Path.home() / ".company")))
SECRETARY_DIR = COMPANY_DIR / "secretary"
TODOS_DIR = SECRETARY_DIR / "todos"
INBOX_DIR = SECRETARY_DIR / "inbox"
NOTES_DIR = SECRETARY_DIR / "notes"
RULES_FILE = SECRETARY_DIR / "rules.md"

# Auto-create directories
for _d in [TODOS_DIR, INBOX_DIR, NOTES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Scheduler
MORNING_BRIEFING_HOUR = int(os.getenv("MORNING_BRIEFING_HOUR", "7"))
MORNING_BRIEFING_MINUTE = int(os.getenv("MORNING_BRIEFING_MINUTE", "30"))
EVENING_REVIEW_HOUR = int(os.getenv("EVENING_REVIEW_HOUR", "21"))
EVENING_REVIEW_MINUTE = int(os.getenv("EVENING_REVIEW_MINUTE", "0"))
