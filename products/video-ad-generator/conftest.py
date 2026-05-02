import os

# テスト用ダミー環境変数（実APIは呼ばない）
os.environ.setdefault("GEMINI_API_KEY", "test_key")
os.environ.setdefault("ATLAS_CLOUD_API_KEY", "test_key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("MUAPI_KLING_MODEL_ID", "test-kling")
os.environ.setdefault("MUAPI_KLING_I2V_URL", "https://example.test/kling")
os.environ.setdefault("VEO3_MODEL_ID", "test-veo3")
os.environ.setdefault("VEO3_FAST_MODEL_ID", "test-veo3-fast")
os.environ.setdefault("VEO3_STANDARD_MODEL_ID", "test-veo3-standard")
os.environ.setdefault("KLING_STD_URL", "https://example.test/kling-std")
os.environ.setdefault("KLING_PRO_URL", "https://example.test/kling-pro")
os.environ.setdefault("KLING_STD_MODEL_ID", "test-kling-std")
os.environ.setdefault("KLING_PRO_MODEL_ID", "test-kling-pro")
os.environ.setdefault("SEEDANCE_LOW_URL", "https://example.test/seedance-low")
os.environ.setdefault("SEEDANCE_HIGH_URL", "https://example.test/seedance-high")

collect_ignore = [".env", ".env.example"]
