"""3階層メモリーシステム — `.company/secretary/memory/` を読み書きする。

- raw/    : 行動ログ（時系列、生データ）
- facts/  : トピック別の事実リスト
- digest/ : 学び・気づきの要約

エージェントは raw に書き込み、夕レビューで facts/digest に昇格させる。
"""

import logging
import re
from datetime import date, datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)
MEMORY_DIR = config.COMPANY_DIR / "secretary" / "memory"
RAW_DIR = MEMORY_DIR / "raw"
FACTS_DIR = MEMORY_DIR / "facts"
DIGEST_DIR = MEMORY_DIR / "digest"


def _ensure_dirs() -> None:
    for d in (RAW_DIR, FACTS_DIR, DIGEST_DIR):
        d.mkdir(parents=True, exist_ok=True)


def append_raw(agent: str, action: str, target_date: Optional[date] = None) -> str:
    """行動ログを raw/<YYYY-MM-DD>.md に追記。"""
    _ensure_dirs()
    d = (target_date or date.today()).isoformat()
    path = RAW_DIR / f"{d}.md"
    timestamp = datetime.now().strftime("%H:%M")

    if not path.exists():
        path.write_text(f"# {d} 行動ログ\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as f:
        f.write(f"- {timestamp} [{agent}] {action.strip()}\n")
    return str(path)


def upsert_fact(topic: str, fact: str) -> str:
    """事実リスト facts/<topic>.md にエントリを追記（重複チェックあり）。"""
    _ensure_dirs()
    safe_topic = re.sub(r"[^\w\-ぁ-んァ-ヶー一-龯]", "_", topic.strip())
    path = FACTS_DIR / f"{safe_topic}.md"
    today = date.today().isoformat()
    entry = f"- [{today}] {fact.strip()}"

    if not path.exists():
        content = f"# {topic}\n\n{entry}\n"
        path.write_text(content, encoding="utf-8")
        return str(path)

    existing = path.read_text(encoding="utf-8")
    if fact.strip() in existing:
        return str(path)

    with path.open("a", encoding="utf-8") as f:
        f.write(f"{entry}\n")
    return str(path)


def upsert_digest(topic: str, learning: str) -> str:
    """学び・気づきを digest/<topic>.md に追記。"""
    _ensure_dirs()
    safe_topic = re.sub(r"[^\w\-ぁ-んァ-ヶー一-龯]", "_", topic.strip())
    path = DIGEST_DIR / f"{safe_topic}.md"
    today = date.today().isoformat()
    entry = f"## {today}\n\n{learning.strip()}\n"

    if not path.exists():
        content = f"# {topic} — 学び\n\n{entry}\n"
        path.write_text(content, encoding="utf-8")
        return str(path)

    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n{entry}")
    return str(path)


def list_recent_raw(days: int = 7) -> list[str]:
    """直近 days 日分の raw ログのパスリスト（新しい順）。"""
    if not RAW_DIR.exists():
        return []
    files = sorted(RAW_DIR.glob("*.md"), reverse=True)
    return [str(p) for p in files[:days]]


def list_topics() -> dict[str, list[str]]:
    """facts と digest のトピック一覧。"""
    out = {"facts": [], "digest": []}
    if FACTS_DIR.exists():
        out["facts"] = sorted(p.stem for p in FACTS_DIR.glob("*.md"))
    if DIGEST_DIR.exists():
        out["digest"] = sorted(p.stem for p in DIGEST_DIR.glob("*.md"))
    return out
