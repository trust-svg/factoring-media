import os

# テスト用ダミー環境変数（実APIは呼ばない）
os.environ.setdefault("GEMINI_API_KEY", "test_key")
os.environ.setdefault("ATLAS_CLOUD_API_KEY", "test_key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("MUAPI_KLING_MODEL_ID", "test-kling")
os.environ.setdefault("MUAPI_KLING_I2V_URL", "https://example.test/kling")
os.environ.setdefault("VEO3_MODEL_ID", "test-veo3")

collect_ignore = [".env", ".env.example"]
