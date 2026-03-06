from datetime import datetime, timezone
from googleapiclient.discovery import build
from auth import get_credentials


def _service():
    return build("calendar", "v3", credentials=get_credentials())


def list_calendar_events(max_results: int = 10) -> list[dict]:
    """直近のカレンダーイベントを取得する。"""
    now = datetime.now(timezone.utc).isoformat()
    result = (
        _service()
        .events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = result.get("items", [])
    return [
        {
            "id": e.get("id"),
            "title": e.get("summary", "（タイトルなし）"),
            "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        }
        for e in events
    ]


def create_calendar_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    location: str = "",
    description: str = "",
) -> dict:
    """カレンダーにイベントを作成する。

    Args:
        title: イベントタイトル
        start_datetime: 開始日時（ISO 8601形式、例: "2025-03-05T15:00:00+09:00"）
        end_datetime: 終了日時（ISO 8601形式）
        location: 場所（省略可）
        description: 説明（省略可）
    """
    event = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"dateTime": start_datetime, "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_datetime, "timeZone": "Asia/Tokyo"},
    }
    created = _service().events().insert(calendarId="primary", body=event).execute()
    return {
        "id": created.get("id"),
        "title": created.get("summary"),
        "start": created.get("start", {}).get("dateTime"),
        "end": created.get("end", {}).get("dateTime"),
        "link": created.get("htmlLink"),
    }
