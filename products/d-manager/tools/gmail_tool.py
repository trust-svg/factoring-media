"""Gmail integration."""

import base64
from email.mime.text import MIMEText
from typing import Optional, List

from googleapiclient.discovery import build
from tools.google_auth import get_credentials

_service = None


def _get_service():
    global _service
    if _service:
        return _service
    _service = build("gmail", "v1", credentials=get_credentials())
    return _service


def get_unread_emails(max_results: int = 10) -> List[dict]:
    service = _get_service()
    result = (
        service.users()
        .messages()
        .list(userId="me", q="is:unread", maxResults=max_results)
        .execute()
    )
    messages = result.get("messages", [])
    emails = []

    for msg in messages:
        detail = (
            service.users().messages().get(userId="me", id=msg["id"]).execute()
        )
        headers = detail.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(無題)")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "不明")
        snippet = detail.get("snippet", "")

        emails.append({
            "id": msg["id"],
            "from": sender,
            "subject": subject,
            "snippet": snippet,
        })

    return emails


def create_draft(to: str, subject: str, body: str) -> dict:
    service = _get_service()
    message = MIMEText(body, "plain", "utf-8")
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return {"id": draft["id"], "status": "ドラフト作成完了"}
