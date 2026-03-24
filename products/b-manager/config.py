import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
if not TELEGRAM_WEBHOOK_SECRET:
    raise ValueError("TELEGRAM_WEBHOOK_SECRET must be set in environment")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# eBay Agent API (same VPS, internal network)
EBAY_AGENT_URL = os.getenv("EBAY_AGENT_URL", "http://127.0.0.1:8000")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
