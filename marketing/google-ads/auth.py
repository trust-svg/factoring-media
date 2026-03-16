"""
Google Ads API — OAuth2 リフレッシュトークン取得スクリプト
初回のみ実行。ブラウザでGoogleログイン→認証コードをコピペ→リフレッシュトークンを取得。
"""

import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main():
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    credentials = flow.run_local_server(port=8080)

    print("\n" + "=" * 60)
    print("認証成功！以下のリフレッシュトークンを .env に貼り付けてください：")
    print("=" * 60)
    print(f"\nGOOGLE_ADS_REFRESH_TOKEN={credentials.refresh_token}\n")
    print("=" * 60)


if __name__ == "__main__":
    main()
