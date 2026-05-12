"""knowledge.db の内容を .company/secretary/knowledge/ 配下に Markdown で書き出す（人が読む/Obsidian/grep 用）。

SQLite が正データ。ここで書く Markdown はビューなので、.company/.gitignore で secretary/knowledge/ は除外する。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_UNSAFE = re.compile(r"[^0-9A-Za-z぀-ヿ一-鿿_-]+")


def _safe(s: str) -> str:
    return _UNSAFE.sub("-", (s or "").strip()).strip("-") or "channel"


def _bullets(
    items: Optional[list], key: Optional[str] = None, owner_key: Optional[str] = None
) -> str:
    if not items:
        return "_（なし）_\n"
    out = []
    for it in items:
        if isinstance(it, dict):
            text = it.get(key or "text") or ""
            who = it.get(owner_key or "owner") or it.get("by") or ""
            out.append(f"- {text}" + (f" — {who}" if who else ""))
        else:
            out.append(f"- {it}")
    return "\n".join(out) + "\n"


def write_digest_md(
    *,
    view_dir: Path,
    channel_name: str,
    department: str,
    date: str,
    source_kind: str,
    summary_md: str,
    topics: Optional[list],
    decisions: Optional[list],
    open_items: Optional[list],
    next_actions: Optional[list],
    facts: Optional[list],
) -> Path:
    out_dir = Path(view_dir) / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date}-{_safe(department)}-{_safe(channel_name)}.md"
    path = out_dir / fname
    body = (
        f"---\n"
        f"date: {date}\n"
        f"department: {department}\n"
        f"channel: {channel_name}\n"
        f"source_kind: {source_kind}\n"
        f"---\n\n"
        f"# {channel_name} — {date}\n\n"
        f"{summary_md.strip()}\n\n"
        f"## トピック\n{_bullets(topics)}\n"
        f"## 決定事項\n{_bullets(decisions, key='text', owner_key='by')}\n"
        f"## 未決事項\n{_bullets(open_items)}\n"
        f"## 次アクション\n{_bullets(next_actions, key='text', owner_key='owner')}\n"
        f"## 出てきた数字・事実\n{_bullets(facts)}"
    )
    path.write_text(body, encoding="utf-8")
    return path
