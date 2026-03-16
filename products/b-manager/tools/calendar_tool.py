"""Google Calendar integration."""

from datetime import datetime, timedelta
from typing import Optional, List

from googleapiclient.discovery import build
from tools.google_auth import get_credentials

_service = None


def _get_service():
    global _service
    if _service:
        return _service
    _service = build("calendar", "v3", credentials=get_credentials())
    return _service


def get_today_events() -> List[dict]:
    service = _get_service()
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    end = (now.replace(hour=23, minute=59, second=59)).isoformat() + "Z"

    result = (
        service.events()
        .list(calendarId="primary", timeMin=start, timeMax=end,
              singleEvents=True, orderBy="startTime")
        .execute()
    )
    events = result.get("items", [])
    return [
        {
            "summary": e.get("summary", "(無題)"),
            "start": e["start"].get("dateTime", e["start"].get("date", "")),
            "end": e["end"].get("dateTime", e["end"].get("date", "")),
            "location": e.get("location", ""),
        }
        for e in events
    ]


def get_free_slots(target_date: Optional[str] = None) -> List[dict]:
    service = _get_service()
    if target_date:
        day = datetime.fromisoformat(target_date)
    else:
        day = datetime.now()

    start = day.replace(hour=9, minute=0, second=0)
    end = day.replace(hour=21, minute=0, second=0)

    events = get_today_events()
    busy = []
    for e in events:
        s = e["start"]
        en = e["end"]
        if "T" in s:
            busy.append((datetime.fromisoformat(s), datetime.fromisoformat(en)))

    busy.sort(key=lambda x: x[0])
    free = []
    cursor = start
    for bs, be in busy:
        if cursor < bs:
            free.append({"start": cursor.isoformat(), "end": bs.isoformat()})
        cursor = max(cursor, be)
    if cursor < end:
        free.append({"start": cursor.isoformat(), "end": end.isoformat()})

    return free


def create_event(summary: str, start_time: str, end_time: str,
                 description: str = "", color_id: Optional[str] = None) -> dict:
    service = _get_service()
    event = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Tokyo"},
    }
    if description:
        event["description"] = description
    if color_id:
        event["colorId"] = color_id

    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created["id"], "summary": summary, "link": created.get("htmlLink", "")}
