"""Google Search Console API wrapper for faccel.jp."""

import os
from datetime import date, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SITE_URL = "https://faccel.jp/"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
TOKEN_PATH = Path(__file__).parent / ".gsc_token.json"


def get_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise RuntimeError("GSC token not found. Run `python setup_gsc_auth.py` first.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def get_service():
    return build("searchconsole", "v1", credentials=get_credentials())


def query_gsc(
    service, start_date: str, end_date: str, dimensions: list, row_limit: int = 25
) -> list:
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    response = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
    return response.get("rows", [])


def get_summary(service, start_date: str, end_date: str) -> dict:
    rows = query_gsc(service, start_date, end_date, dimensions=["date"])
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    clicks = sum(int(r["clicks"]) for r in rows)
    impressions = sum(int(r["impressions"]) for r in rows)
    ctr = sum(r["ctr"] for r in rows) / len(rows)
    position = sum(r["position"] for r in rows) / len(rows)
    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "position": position,
    }


def get_top_pages(service, start_date: str, end_date: str, limit: int = 5) -> list:
    rows = query_gsc(
        service, start_date, end_date, dimensions=["page"], row_limit=limit
    )
    return [
        {
            "page": r["keys"][0].replace("https://faccel.jp", ""),
            "clicks": int(r["clicks"]),
            "impressions": int(r["impressions"]),
            "ctr": r["ctr"],
            "position": r["position"],
        }
        for r in rows
    ]


def get_top_queries(service, start_date: str, end_date: str, limit: int = 10) -> list:
    rows = query_gsc(
        service, start_date, end_date, dimensions=["query"], row_limit=limit
    )
    return [
        {
            "query": r["keys"][0],
            "clicks": int(r["clicks"]),
            "impressions": int(r["impressions"]),
            "ctr": r["ctr"],
            "position": r["position"],
        }
        for r in rows
    ]


def get_opportunity_queries(service, start_date: str, end_date: str) -> list:
    """順位11-30かつ表示数50以上のクエリ（2ページ目チャンス）"""
    rows = query_gsc(service, start_date, end_date, dimensions=["query"], row_limit=50)
    opps = [r for r in rows if 11 <= r["position"] <= 30 and r["impressions"] >= 50]
    opps.sort(key=lambda x: x["impressions"], reverse=True)
    return [
        {
            "query": r["keys"][0],
            "clicks": int(r["clicks"]),
            "impressions": int(r["impressions"]),
            "position": r["position"],
        }
        for r in opps[:10]
    ]
