"""d-manager Dashboard — チケット・メモリー・フローの可視化 Web UI。

起動:
    python dashboard.py        # http://localhost:5189

d-manager Bot とは独立プロセス。`.company/tickets/` と
`.company/secretary/memory/` を読み取り専用で表示する。
"""

import logging
import re
from pathlib import Path

from flask import Flask, abort, redirect, render_template, url_for

import config
from flows import FLOWS, list_flows
from tools import tickets, memory

logger = logging.getLogger(__name__)
app = Flask(__name__, template_folder="templates/dashboard")

PORT = 5189


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _all_tickets() -> list[dict]:
    """active + done を結合（archive は別画面）。"""
    out = []
    for base, status_dir in (
        (tickets.ACTIVE_DIR, "active"),
        (tickets.DONE_DIR, "done"),
    ):
        if not base.exists():
            continue
        for p in sorted(base.glob("t-*.md"), reverse=True):
            info = tickets.get_ticket(p.stem) or {}
            info["dir"] = status_dir
            out.append(info)
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    actives = tickets.list_active()
    by_owner: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for t in actives:
        by_owner[t.get("owner", "?")] = by_owner.get(t.get("owner", "?"), 0) + 1
        by_status[t.get("status", "?")] = by_status.get(t.get("status", "?"), 0) + 1
    topics = memory.list_topics()
    return render_template(
        "index.html",
        active_count=len(actives),
        by_owner=by_owner,
        by_status=by_status,
        topics=topics,
        flows=list_flows(),
    )


@app.route("/tickets")
def tickets_index():
    return render_template("tickets.html", tickets=_all_tickets())


@app.route("/tickets/<ticket_id>")
def ticket_detail(ticket_id: str):
    if not re.match(r"^t-\d+$", ticket_id):
        abort(400)
    info = tickets.get_ticket(ticket_id)
    if not info:
        abort(404)
    body = _read_file(Path(info["path"]))
    return render_template("ticket.html", t=info, body=body)


@app.route("/memory")
def memory_index():
    topics = memory.list_topics()
    recent_raw = memory.list_recent_raw(days=7)
    return render_template("memory.html", topics=topics, recent_raw=recent_raw)


@app.route("/memory/<kind>/<topic>")
def memory_topic(kind: str, topic: str):
    if kind not in ("facts", "digest"):
        abort(404)
    safe_topic = re.sub(r"[^\w\-ぁ-んァ-ヶー一-龯]", "_", topic)
    base = memory.FACTS_DIR if kind == "facts" else memory.DIGEST_DIR
    path = base / f"{safe_topic}.md"
    if not path.exists():
        abort(404)
    return render_template(
        "memory_topic.html",
        kind=kind,
        topic=topic,
        body=_read_file(path),
    )


@app.route("/memory/raw/<date>")
def memory_raw(date: str):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        abort(400)
    path = memory.RAW_DIR / f"{date}.md"
    if not path.exists():
        abort(404)
    return render_template(
        "memory_topic.html", kind="raw", topic=date, body=_read_file(path)
    )


@app.route("/flows")
def flows_index():
    flows_with_meta = []
    for name, info in FLOWS.items():
        flows_with_meta.append(
            {
                "name": name,
                "description": info.get("description", ""),
                "mode": info.get("mode", "sequential"),
                "args": info.get("args", []),
                "steps": [a for a, _ in info.get("steps", [])],
                "post": [a for a, _ in info.get("post", [])],
            }
        )
    return render_template("flows.html", flows=flows_with_meta)


@app.route("/healthz")
def healthz():
    return {"ok": True}


def main():
    logging.basicConfig(level=logging.INFO)
    logger.info(f"Dashboard starting on http://localhost:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
