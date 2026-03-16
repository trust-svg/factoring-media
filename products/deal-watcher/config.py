import os
from dotenv import load_dotenv

load_dotenv()

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "3"))
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "deal_watcher.db")
PORT = int(os.getenv("PORT", "8001"))

ESHIP_EMAIL = os.getenv("ESHIP_EMAIL", "")
ESHIP_PASSWORD = os.getenv("ESHIP_PASSWORD", "")

# Auto-sourcing settings
AUTO_SOURCE_MODE = os.getenv("AUTO_SOURCE_MODE", "notify")  # "notify" | "auto" | "off"
AUTO_SOURCE_MIN_PROFIT = int(os.getenv("AUTO_SOURCE_MIN_PROFIT", "15000"))  # 最低利益 ¥
AUTO_SOURCE_MAX_PRICE = int(os.getenv("AUTO_SOURCE_MAX_PRICE", "100000"))  # 仕入れ上限 ¥
MIN_PROFIT_MARGIN = float(os.getenv("MIN_PROFIT_MARGIN", "0.20"))  # 最低利益率 20%

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
