"""D-Manager configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
if not DISCORD_BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN must be set")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

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
RULES_FILE = SECRETARY_DIR / "rules.md"

# Auto-create directories
for _d in [TODOS_DIR, INBOX_DIR, NOTES_DIR, DECISIONS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Scheduler
MORNING_BRIEFING_HOUR = int(os.getenv("MORNING_BRIEFING_HOUR", "7"))
MORNING_BRIEFING_MINUTE = int(os.getenv("MORNING_BRIEFING_MINUTE", "30"))
EVENING_REVIEW_HOUR = int(os.getenv("EVENING_REVIEW_HOUR", "21"))
EVENING_REVIEW_MINUTE = int(os.getenv("EVENING_REVIEW_MINUTE", "0"))

# Channel-to-department mapping (set after bot connects)
CHANNEL_MAP = {
    "general": "secretary",
    "operations": "operations",
    "product": "product",
    "marketing": "marketing",
    "finance": "finance",
    "research": "research",
    "strategy": "strategy",
    "decisions": "secretary",
    "alerts": "secretary",
    "daily-digest": "research",
}
