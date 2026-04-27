from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _credentials_path() -> Path:
    return Path(os.getenv("GSC_CREDENTIALS_PATH", "/app/credentials/gsc_oauth.json"))


def _token_path() -> Path:
    return Path(os.getenv("GSC_TOKEN_PATH", "/app/credentials/gsc_token.json"))


def load_credentials() -> Credentials:
    token_path = _token_path()
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        return creds

    cred_path = _credentials_path()
    if not cred_path.exists():
        raise RuntimeError(
            f"GSC OAuth credentials not found at {cred_path}. "
            "Run `python -m core.gsc_auth` locally to bootstrap."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
    creds = flow.run_local_server(port=8080)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    return creds


def build_service():
    creds = load_credentials()
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def query_search_analytics(
    gsc_property: str,
    start_date: date,
    end_date: date,
    *,
    dimensions: list[str] | None = None,
    row_limit: int = 5000,
) -> list[dict[str, Any]]:
    service = build_service()
    body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": dimensions or ["query", "page"],
        "rowLimit": row_limit,
    }
    response = (
        service.searchanalytics()
        .query(siteUrl=gsc_property, body=body)
        .execute()
    )
    rows = response.get("rows", [])
    out: list[dict[str, Any]] = []
    for row in rows:
        keys = row.get("keys", [])
        out.append(
            {
                "keyword": keys[0] if len(keys) > 0 else "",
                "page": keys[1] if len(keys) > 1 else "",
                "impressions": row.get("impressions", 0),
                "clicks": row.get("clicks", 0),
                "ctr": row.get("ctr", 0.0),
                "position": row.get("position", 0.0),
            }
        )
    return out


def fetch_window(gsc_property: str, end_day: date, lookback_days: int) -> list[dict[str, Any]]:
    start = end_day - timedelta(days=lookback_days)
    return query_search_analytics(gsc_property, start, end_day)
