import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# LINE
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Google
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Company directory
COMPANY_DIR = Path(os.getenv("COMPANY_DIR", str(Path.home() / ".company")))
SECRETARY_DIR = COMPANY_DIR / "secretary"
TODOS_DIR = SECRETARY_DIR / "todos"
INBOX_DIR = SECRETARY_DIR / "inbox"
NOTES_DIR = SECRETARY_DIR / "notes"
RULES_FILE = SECRETARY_DIR / "rules.md"

# Scheduler
MORNING_BRIEFING_HOUR = int(os.getenv("MORNING_BRIEFING_HOUR", "7"))
MORNING_BRIEFING_MINUTE = int(os.getenv("MORNING_BRIEFING_MINUTE", "30"))
EVENING_REVIEW_HOUR = int(os.getenv("EVENING_REVIEW_HOUR", "21"))
EVENING_REVIEW_MINUTE = int(os.getenv("EVENING_REVIEW_MINUTE", "0"))
