#!/usr/bin/env python3
"""
GSC OAuth初期設定（初回のみ実行）
ブラウザが開いてGoogleアカウントで認証後、.gsc_token.json が生成される。

実行方法:
  cd products/factoring-media/reports
  python setup_gsc_auth.py
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
CREDENTIALS_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "resources/docs/client_secret_931763215316-btpcnubjmuenkvjacgrjje9fs3p9jsjc.apps.googleusercontent.com.json"
)
TOKEN_PATH = Path(__file__).parent / ".gsc_token.json"

if not CREDENTIALS_PATH.exists():
    raise FileNotFoundError(f"client_secret が見つかりません: {CREDENTIALS_PATH}")

flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
creds = flow.run_local_server(port=0)
TOKEN_PATH.write_text(creds.to_json())
print(f"✅ GSC token saved to {TOKEN_PATH}")
