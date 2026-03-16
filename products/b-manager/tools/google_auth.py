"""Shared Google OAuth — single token.json with all scopes.

Supports two modes:
- Local: token.json file (with browser-based initial auth)
- Server (Railway etc): GOOGLE_TOKEN_JSON env var (base64 or raw JSON)
"""

import json
import os
import base64

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH

ALL_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

_creds = None


def get_credentials() -> Credentials:
    global _creds
    if _creds and _creds.valid:
        return _creds

    creds = None

    # Priority 1: env var (for Railway / serverless)
    token_env = os.getenv("GOOGLE_TOKEN_JSON", "")
    if token_env:
        try:
            # Try base64 decode first
            token_data = json.loads(base64.b64decode(token_env))
        except Exception:
            token_data = json.loads(token_env)
        creds = Credentials.from_authorized_user_info(token_data, ALL_SCOPES)

    # Priority 2: token.json file (local dev)
    if not creds and os.path.exists(GOOGLE_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, ALL_SCOPES)

    if not creds:
        # Fallback: browser-based auth (local only)
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_PATH, ALL_SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(GOOGLE_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        except Exception:
            raise RuntimeError("Google OAuth not configured. Set GOOGLE_TOKEN_JSON env var or run locally first.")

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token locally if possible
        try:
            with open(GOOGLE_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        except Exception:
            pass

    _creds = creds
    return _creds
