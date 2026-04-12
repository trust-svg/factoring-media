from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
ATLAS_CLOUD_API_KEY: str = os.environ["ATLAS_CLOUD_API_KEY"]
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

AUTO_APPROVE: bool = os.environ.get("AUTO_APPROVE", "false").lower() == "true"
AUTO_APPROVE_SCORE_THRESHOLD: float = float(os.environ.get("AUTO_APPROVE_SCORE_THRESHOLD", "0.75"))

APP_PORT: int = int(os.environ.get("APP_PORT", "8004"))
APP_HOST: str = "0.0.0.0"

VIDEO_DURATION: int = 10
VIDEO_ASPECT_RATIO: str = "9:16"
BATCH_SIZE: int = 10

OUTPUT_DIR = BASE_DIR / "output"
PENDING_DIR = OUTPUT_DIR / "pending"
APPROVED_DIR = OUTPUT_DIR / "approved"
REJECTED_DIR = OUTPUT_DIR / "rejected"
VIDEOS_DIR = OUTPUT_DIR / "videos"
DB_PATH = BASE_DIR / "video_ad.db"

# Atlas Cloud Seedance 2.0 I2V
ATLAS_CLOUD_I2V_URL = "https://api.muapi.ai/api/v1/seedance-v2.0-i2v"
ATLAS_CLOUD_STATUS_URL = "https://api.muapi.ai/api/v1/status/{request_id}"

# NanoBanana PRO (Google Gemini 3 Pro Image)
NANOBANANA_MODEL = "gemini-3-pro-image-preview"
