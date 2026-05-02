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
AUTO_APPROVE_SCORE_THRESHOLD: float = float(
    os.environ.get("AUTO_APPROVE_SCORE_THRESHOLD", "0.75")
)

APP_PORT: int = int(os.environ.get("APP_PORT", "8004"))
APP_HOST: str = "0.0.0.0"
PUBLIC_BASE_URL: str = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

VIDEO_DURATION: int = 10
VIDEO_ASPECT_RATIO: str = "9:16"
BATCH_SIZE: int = 10

OUTPUT_DIR = BASE_DIR / "output"
PENDING_DIR = OUTPUT_DIR / "pending"
APPROVED_DIR = OUTPUT_DIR / "approved"
REJECTED_DIR = OUTPUT_DIR / "rejected"
VIDEOS_DIR = OUTPUT_DIR / "videos"
UPLOADED_DIR = OUTPUT_DIR / "uploaded"
MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "20"))
DB_PATH = BASE_DIR / "video_ad.db"

# Atlas Cloud Seedance Pro I2V (MuApi.ai)
SEEDANCE_LOW_URL: str = os.environ.get(
    "SEEDANCE_LOW_URL",
    "https://api.muapi.ai/api/v1/seedance-pro-i2v-fast",
)
SEEDANCE_HIGH_URL: str = os.environ.get(
    "SEEDANCE_HIGH_URL",
    "https://api.muapi.ai/api/v1/seedance-pro-i2v",
)
ATLAS_CLOUD_STATUS_URL = "https://api.muapi.ai/api/v1/predictions/{request_id}/result"

# NanoBanana PRO (Google Gemini 3 Pro Image)
NANOBANANA_MODEL = "gemini-3-pro-image-preview"

# Veo 3.1 (Gemini API): fast = low quality, standard = high quality
VEO3_FAST_MODEL_ID: str = os.environ.get(
    "VEO3_FAST_MODEL_ID",
    os.environ.get("VEO3_MODEL_ID", "veo-3.1-fast-generate-001"),
)
VEO3_STANDARD_MODEL_ID: str = os.environ.get(
    "VEO3_STANDARD_MODEL_ID", "veo-3.1-standard-generate-001"
)

# Kling V3 (muapi.ai): std = low quality, pro = high quality
KLING_STD_URL: str = os.environ.get(
    "KLING_STD_URL",
    "https://api.muapi.ai/api/v1/kling-v3.0-standard-image-to-video",
)
KLING_PRO_URL: str = os.environ.get(
    "KLING_PRO_URL",
    "https://api.muapi.ai/api/v1/kling-v3.0-pro-image-to-video",
)

# UI/Defaults
DEFAULT_PROVIDER: str = os.environ.get("DEFAULT_PROVIDER", "seedance")
