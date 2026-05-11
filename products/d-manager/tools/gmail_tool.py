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
        detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = detail.get("payload", {}).get("headers", [])
        subject = next(
            (h["value"] for h in headers if h["name"] == "Subject"), "(無題)"
        )
        sender = next((h["value"] for h in headers if h["name"] == "From"), "不明")
        message_id = next(
            (
                h["value"]
                for h in headers
                if h["name"] == "Message-ID" or h["name"] == "Message-Id"
            ),
            "",
        )
        snippet = detail.get("snippet", "")

        emails.append(
            {
                "id": msg["id"],
                "threadId": detail.get("threadId", msg["id"]),
                "from": sender,
                "subject": subject,
                "snippet": snippet,
                "messageId": message_id,
            }
        )

    return emails


def get_existing_draft_thread_ids(max_results: int = 100) -> set:
    """Return set of threadIds that already have a draft.

    Used to avoid creating duplicate drafts for the same conversation.
    """
    service = _get_service()
    thread_ids = set()
    page_token = None
    while True:
        params = {"userId": "me", "maxResults": min(max_results, 100)}
        if page_token:
            params["pageToken"] = page_token
        result = service.users().drafts().list(**params).execute()
        for d in result.get("drafts", []):
            msg = d.get("message") or {}
            tid = msg.get("threadId")
            if tid:
                thread_ids.add(tid)
        page_token = result.get("nextPageToken")
        if not page_token or len(thread_ids) >= max_results:
            break
    return thread_ids


def delete_draft(draft_id: str) -> dict:
    """Delete a Gmail draft by ID."""
    service = _get_service()
    service.users().drafts().delete(userId="me", id=draft_id).execute()
    return {"id": draft_id, "status": "削除完了"}


def create_draft(
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> dict:
    """Create a Gmail draft.

    If thread_id is given, the draft becomes a reply within that thread.
    If in_reply_to (the original Message-ID header) is given, In-Reply-To /
    References headers are set so Gmail threads it correctly.
    """
    service = _get_service()
    message = MIMEText(body, "plain", "utf-8")
    message["to"] = to
    message["subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft_body = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id
    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return {"id": draft["id"], "status": "ドラフト作成完了"}
