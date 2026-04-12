"""eBay Agent Hub — 統合設定"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ── eBay API ──────────────────────────────────────────────
EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")
EBAY_REDIRECT_URI = os.getenv("EBAY_REDIRECT_URI", "")
EBAY_TOKEN_FILE = BASE_DIR / "tokens" / "ebay_token.json"
EBAY_API_BASE = "https://api.ebay.com"
EBAY_AUTH_BASE = "https://auth.ebay.com"

EBAY_OAUTH_SCOPES = " ".join([
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
    "https://api.ebay.com/oauth/api_scope/buy.browse",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
])

# ── AI ────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Database ──────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'agent.db'}")

# ── Server ────────────────────────────────────────────────
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# ── Rate Limits ───────────────────────────────────────────
EBAY_API_CALLS_PER_SECOND = float(os.getenv("EBAY_API_CALLS_PER_SECOND", "2.0"))
CLAUDE_MAX_CONCURRENT = int(os.getenv("CLAUDE_MAX_CONCURRENT", "3"))

# ── Listing Defaults ─────────────────────────────────────
EBAY_TITLE_MAX_LENGTH = 80
RECOMMENDED_PHOTO_COUNT = 5
MIN_DESCRIPTION_LENGTH = 200
EBAY_PAGE_SIZE = 200

# ── Paths ─────────────────────────────────────────────────
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
LOGS_DIR = BASE_DIR / "logs"
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", str(BASE_DIR / "screenshots")))

# ── Notifications ─────────────────────────────────────────
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO", "")

# ── Instagram / Meta Graph API ────────────────────────────
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "")

# ── Scraper ───────────────────────────────────────────────
# ジャンク品キーワード
JUNK_KEYWORDS = [
    "ジャンク", "junk", "現状品", "現状渡し", "動作未確認",
    "動作不良", "故障", "部品取り", "訳あり", "難あり",
    "as is", "for parts", "not working", "broken",
]

WORKING_KEYWORDS = [
    "動作確認済", "動作確認済み", "動作品", "動作良好",
    "正常動作", "完動品", "動作OK", "動作ok", "tested",
]

# スクレイピング設定（ebay-inventory-tool 互換）
REQUEST_DELAY_SEC = 2.0
MAX_RESULTS_PER_PLATFORM = 10

# ── Deal Watcher ──────────────────────────────────────────
DEAL_WATCHER_DB = os.getenv(
    "DEAL_WATCHER_DB",
    str(Path.home() / "Services" / "deal-watcher" / "deal_watcher.db"),
)
ESHIP_EMAIL = os.getenv("ESHIP_EMAIL", "")
ESHIP_PASSWORD = os.getenv("ESHIP_PASSWORD", "")

# ── Pricing ───────────────────────────────────────────────
EBAY_FEE_RATE = 0.129  # eBay final value fee (12.9%)
PAYONEER_FEE_RATE = 0.02  # Payoneer為替手数料 (2%)
PRICE_CHECK_INTERVAL_HOURS = 6
COMPETITOR_CACHE_TTL_HOURS = int(os.getenv("COMPETITOR_CACHE_TTL_HOURS", "24"))

# ── Shopify ───────────────────────────────────────────────
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
SHOPIFY_DISCOUNT_RATE = float(os.getenv("SHOPIFY_DISCOUNT_RATE", "0.05"))

# ── Monthly Targets ───────────────────────────────────────
MONTHLY_REVENUE_TARGET_JPY = 5_000_000   # ¥5,000,000
MONTHLY_MARGIN_TARGET_PCT  = 20.0        # 20%
MONTHLY_PROFIT_TARGET_JPY  = 1_000_000   # ¥1,000,000
