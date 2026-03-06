import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from config import GOOGLE_SCOPES, GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE


def get_credentials() -> Credentials:
    """Google OAuth 2.0認証を行い、有効なCredentialsを返す。"""
    creds = None

    # 既存トークンを読み込む
    if os.path.exists(GOOGLE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, GOOGLE_SCOPES)

    # トークンが無効または期限切れの場合はリフレッシュ or 再認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"{GOOGLE_CREDENTIALS_FILE} が見つかりません。\n"
                    "Google Cloud Console から credentials.json をダウンロードして\n"
                    "このフォルダに配置してください。（readme.md を参照）"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_FILE, GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)

        # トークンを保存
        with open(GOOGLE_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds
