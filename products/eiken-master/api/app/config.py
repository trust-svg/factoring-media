import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]
JWT_SECRET: str = os.environ["JWT_SECRET"]
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30日
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL: str = os.getenv("VAPID_CLAIMS_EMAIL", "admin@example.com")
