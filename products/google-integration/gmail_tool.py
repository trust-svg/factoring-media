import base64
import email as email_lib
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from auth import get_credentials


def _service():
    return build("gmail", "v1", credentials=get_credentials())


def list_emails(max_results: int = 5, query: str = "") -> list[dict]:
    """受信トレイの最新メールを取得する。

    Args:
        max_results: 取得件数（デフォルト5件）
        query: Gmailの検索クエリ（例: "from:example@gmail.com"）
    """
    params = {"userId": "me", "maxResults": max_results, "labelIds": ["INBOX"]}
    if query:
        params["q"] = query

    result = _service().users().messages().list(**params).execute()
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        detail = (
            _service()
            .users()
            .messages()
            .get(userId="me", id=msg["id"], format="metadata",
                 metadataHeaders=["Subject", "From", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        emails.append({
            "id": msg["id"],
            "subject": headers.get("Subject", "（件名なし）"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": detail.get("snippet", ""),
        })
    return emails


def get_email(message_id: str) -> dict:
    """メールの本文を取得する。

    Args:
        message_id: メールID（list_emails で取得した id）
    """
    detail = (
        _service()
        .users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
    body = _extract_body(detail.get("payload", {}))
    return {
        "id": message_id,
        "subject": headers.get("Subject", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    """メールのペイロードからテキスト本文を抽出する。"""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            result = _extract_body(part)
            if result:
                return result
    return ""


def create_draft_reply(message_id: str, body: str) -> dict:
    """メールの返信下書きを作成する。

    Args:
        message_id: 返信元メールID
        body: 返信本文
    """
    original = get_email(message_id)
    reply_to = original["from"]
    subject = original["subject"]
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"

    mime = MIMEText(body, "plain", "utf-8")
    mime["To"] = reply_to
    mime["Subject"] = subject
    mime["In-Reply-To"] = message_id
    mime["References"] = message_id

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    draft = (
        _service()
        .users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw, "threadId": _get_thread_id(message_id)}})
        .execute()
    )
    return {
        "draft_id": draft.get("id"),
        "to": reply_to,
        "subject": subject,
    }


def _get_thread_id(message_id: str) -> str:
    detail = (
        _service()
        .users()
        .messages()
        .get(userId="me", id=message_id, format="minimal")
        .execute()
    )
    return detail.get("threadId", "")


def send_draft(draft_id: str) -> dict:
    """作成した下書きを送信する。

    Args:
        draft_id: create_draft_reply で取得した draft_id
    """
    result = (
        _service()
        .users()
        .drafts()
        .send(userId="me", body={"id": draft_id})
        .execute()
    )
    return {"message_id": result.get("id"), "status": "sent"}
