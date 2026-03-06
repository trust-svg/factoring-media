"""設定読み込み・定数定義"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# eBay API
EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")
EBAY_REDIRECT_URI = os.getenv("EBAY_REDIRECT_URI", "")
EBAY_TOKEN_FILE = BASE_DIR / "tokens" / "ebay_token.json"

# eBay API エンドポイント (本番)
EBAY_API_BASE = "https://api.ebay.com"
EBAY_AUTH_BASE = "https://auth.ebay.com"

# Anthropic Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# データベース
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./optimizer.db")

# サーバー
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8080"))

# レート制限
EBAY_API_CALLS_PER_SECOND = float(os.getenv("EBAY_API_CALLS_PER_SECOND", "2.0"))
CLAUDE_MAX_CONCURRENT = int(os.getenv("CLAUDE_MAX_CONCURRENT", "3"))
COMPETITOR_CACHE_TTL_HOURS = int(os.getenv("COMPETITOR_CACHE_TTL_HOURS", "24"))

# 各種パス
LOGS_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# OAuth スコープ（読み書き + Browse API）
EBAY_OAUTH_SCOPES = " ".join([
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
    "https://api.ebay.com/oauth/api_scope/buy.browse",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
])

# SEO スコアリング重み
SEO_WEIGHTS = {
    "title": 0.35,
    "description": 0.25,
    "specifics": 0.25,
    "photos": 0.15,
}

# タイトル最大文字数
EBAY_TITLE_MAX_LENGTH = 80

# 推奨写真枚数
RECOMMENDED_PHOTO_COUNT = 5

# 説明文最小文字数
MIN_DESCRIPTION_LENGTH = 200

# API ページネーション
EBAY_PAGE_SIZE = 200
