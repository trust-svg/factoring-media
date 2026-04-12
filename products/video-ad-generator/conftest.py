import os

# テスト用ダミー環境変数（実APIは呼ばない）
os.environ.setdefault("GEMINI_API_KEY", "test_key")
os.environ.setdefault("ATLAS_CLOUD_API_KEY", "test_key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")

collect_ignore = [".env", ".env.example"]
