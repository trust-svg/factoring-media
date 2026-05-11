"""エージェントチケットシステム — `.company/tickets/` を管理。

ディレクトリ構成:
  .company/tickets/
    ├ active/<id>.md      # 進行中
    ├ done/<id>.md        # 完了（30日後にarchiveへ）
    └ archive/<YYYY-MM>/  # 月次アーカイブ

人間TODO（secretary/todos/）とは分離:
  - TODO   = ロキ自身が手を動かす作業
  - チケット = AI社員が実行する作業
"""

import logging
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)
TICKETS_DIR = config.COMPANY_DIR / "tickets"
ACTIVE_DIR = TICKETS_DIR / "active"
DONE_DIR = TICKETS_DIR / "done"
ARCHIVE_DIR = TICKETS_DIR / "archive"

VALID_STATUSES = {"open", "in_progress", "blocked", "done"}


def _ensure_dirs() -> None:
    for d in (ACTIVE_DIR, DONE_DIR, ARCHIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _next_id() -> str:
    """連番ID `t-NNNN` を採番（active + done + 全archive を見て次を決める）。"""
    _ensure_dirs()
    nums = []
    for base in (ACTIVE_DIR, DONE_DIR):
        for p in base.glob("t-*.md"):
            m = re.match(r"t-(\d+)", p.stem)
            if m:
                nums.append(int(m.group(1)))
    for sub in ARCHIVE_DIR.glob("*"):
        if sub.is_dir():
            for p in sub.glob("t-*.md"):
                m = re.match(r"t-(\d+)", p.stem)
                if m:
                    nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    return f"t-{next_n:04d}"


def _ticket_path(ticket_id: str) -> Optional[Path]:
    """active/done を順に探して返す。なければ None。"""
    for base in (ACTIVE_DIR, DONE_DIR):
        p = base / f"{ticket_id}.md"
        if p.exists():
            return p
    return None


def create_ticket(
    title: str,
    owner: str,
    detail: str = "",
    parent_id: Optional[str] = None,
) -> str:
    """新規チケットを起票し、ID を返す。"""
    _ensure_dirs()
    tid = _next_id()
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    path = ACTIVE_DIR / f"{tid}.md"

    parent_line = f"parent: {parent_id}\n" if parent_id else ""
    content = (
        f"---\n"
        f"id: {tid}\n"
        f"title: {title}\n"
        f"owner: {owner}\n"
        f"status: open\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"{parent_line}"
        f"---\n\n"
        f"# {title}\n\n"
        f"## 詳細\n{detail}\n\n"
        f"## 進捗ログ\n"
        f"- {today} {now} — 起票（owner: {owner}）\n"
    )
    path.write_text(content, encoding="utf-8")
    logger.info(f"Ticket created: {tid} ({title}) → {owner}")
    return tid


def update_status(ticket_id: str, status: str, note: str = "") -> bool:
    """ステータス更新 + 進捗ログ追記。"""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status} (must be one of {VALID_STATUSES})")
    path = _ticket_path(ticket_id)
    if not path:
        logger.warning(f"Ticket not found: {ticket_id}")
        return False

    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"^status:\s*.+$", f"status: {status}", text, count=1, flags=re.MULTILINE
    )
    text = re.sub(
        r"^updated:\s*.+$", f"updated: {today}", text, count=1, flags=re.MULTILINE
    )

    log_entry = f"- {today} {now} — status: {status}"
    if note:
        log_entry += f" / {note.strip()}"
    text = text.rstrip() + f"\n{log_entry}\n"
    path.write_text(text, encoding="utf-8")

    if status == "done" and path.parent == ACTIVE_DIR:
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        new_path = DONE_DIR / path.name
        shutil.move(str(path), str(new_path))
        logger.info(f"Ticket {ticket_id} moved to done/")
    return True


def append_log(ticket_id: str, note: str) -> bool:
    """進捗ログのみ追記（ステータス変更なし）。"""
    path = _ticket_path(ticket_id)
    if not path:
        return False
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    text = path.read_text(encoding="utf-8").rstrip()
    text += f"\n- {today} {now} — {note.strip()}\n"
    path.write_text(text, encoding="utf-8")
    return True


def get_ticket(ticket_id: str) -> Optional[dict]:
    """チケット情報を返す（frontmatter の主要項目）。"""
    path = _ticket_path(ticket_id)
    if not path:
        return None
    text = path.read_text(encoding="utf-8")
    fields = {}
    for key in ("id", "title", "owner", "status", "created", "updated", "parent"):
        m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        if m:
            fields[key] = m.group(1).strip()
    fields["path"] = str(path)
    return fields


def list_active() -> list[dict]:
    """アクティブチケット一覧。"""
    _ensure_dirs()
    out = []
    for p in sorted(ACTIVE_DIR.glob("t-*.md")):
        info = get_ticket(p.stem)
        if info:
            out.append(info)
    return out


def list_by_owner(owner: str) -> list[dict]:
    """特定オーナーのアクティブチケット。"""
    return [t for t in list_active() if t.get("owner", "").lower() == owner.lower()]


def archive_old_done(days: int = 30) -> int:
    """done/ 配下で `updated` が days 日より古いチケットを archive/<YYYY-MM>/ に移動。

    戻り値: 移動した件数。
    """
    _ensure_dirs()
    if not DONE_DIR.exists():
        return 0
    threshold = date.today() - timedelta(days=days)
    moved = 0
    for p in list(DONE_DIR.glob("t-*.md")):
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
        if not m:
            continue
        try:
            updated = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if updated >= threshold:
            continue
        ym = updated.strftime("%Y-%m")
        target_dir = ARCHIVE_DIR / ym
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(target_dir / p.name))
        moved += 1
    if moved:
        logger.info(f"Archived {moved} old done tickets (older than {days} days)")
    return moved
