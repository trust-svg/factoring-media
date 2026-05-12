"""フェーズ1: チャット→議事録化。

learning/store.py の turns/sessions を読み、セッション（チャンネル×日付）ごとに claude -p で
構造化議事録を作って knowledge/store.py に保存し、knowledge/views.py で Markdown も書き出す。
council スレッドの .md（.company/meetings/）はインデックスのみ。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from learning import store as lstore
from learning.cli_runner import run_claude
from learning.reviewer import format_conversation_log
from knowledge import store as kstore, views

logger = logging.getLogger(__name__)

_PERSONA = (
    "あなたは TrustLink の議事録ライターです。AI社員のような人格は持ちません。"
    "1日分の1チャンネルの会話ログを読み、何が議論され何が決まったかを構造化して書き出す単機能エージェントです。"
    "ファイル操作・外部コマンド・API 呼び出しは一切しません。出力は指定フォーマットのテキストのみです。"
    "APIキー・パスワード・トークンなど秘密情報が会話に出てきても、要約・JSON のどこにも書かず `***` でマスクしてください。"
)

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _build_prompt(conversation_log: str) -> str:
    return f"""以下は d-manager（AI組織Bot）の1チャンネルでの1日分の会話ログです。
これを「あとで読み返して資産になる議事録」に要約してください。雑談・挨拶・コマンド出力は落とし、意味のある中身だけ残します。

出力フォーマット（厳守）:
1) まず Markdown 本文を書く（見出し `## 議事録` から始め、要点を箇条書きで。長くても300字程度）。
2) 本文の後に、機械可読の JSON を ```json フェンスで1つだけ付ける。キーは:
   - "topics": string[]（話題のラベル）
   - "decisions": {{"text": string, "by": string}}[]（決まったこと・誰が）
   - "open_items": string[]（未決・宿題）
   - "next_actions": {{"text": string, "owner": string}}[]（次にやること・担当）
   - "facts": string[]（出てきた数字・固有名詞・確定事実のメモ）
   該当が無いキーは空配列 [] にする。

会話に意味のある中身がほとんど無ければ、本文は `## 議事録\\n（特筆事項なし）` だけにし、JSON は全キー空配列にしてください。

---
{conversation_log}
"""


def _parse_output(
    stdout: str,
) -> tuple[
    str, Optional[list], Optional[list], Optional[list], Optional[list], Optional[list]
]:
    text = (stdout or "").strip()
    m = _JSON_FENCE_RE.search(text)
    if not m:
        return text or "## 議事録\n（出力なし）", None, None, None, None, None
    summary = text[: m.start()].strip() or "## 議事録\n（本文なし）"
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return summary, None, None, None, None, None

    def _list(key):
        v = data.get(key)
        return v if isinstance(v, list) and v else None

    return (
        summary,
        _list("topics"),
        _list("decisions"),
        _list("open_items"),
        _list("next_actions"),
        _list("facts"),
    )


def _is_command_only(turns: list[dict]) -> bool:
    """ユーザー発言がすべて短い `!` コマンドだけなら True（中身のないオペレーション）。"""
    user_msgs = [t["content"].strip() for t in turns if t["role"] == "user"]
    if not user_msgs:
        return True
    return all(m.startswith("!") and len(m) < 40 for m in user_msgs)


@dataclass
class DigestRun:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    council_indexed: int = 0
    notes: list[str] = field(default_factory=list)


def index_council_meetings(*, date: str, knowledge_db: Path, meetings_dir: Path) -> int:
    """`.company/meetings/<date>_*.md` を knowledge.db に source_kind='council' で索引登録。返り値=件数。"""
    mdir = Path(meetings_dir)
    if not mdir.exists():
        return 0
    n = 0
    for f in sorted(mdir.glob(f"{date}_*.md")):
        try:
            head = f.read_text(encoding="utf-8")[:500].strip()
        except OSError:
            continue
        kstore.upsert_digest(
            knowledge_db,
            channel_id=f"council:{f.name}",
            channel_name=f.stem,
            department="strategy",
            date=date,
            source_kind="council",
            turn_count=0,
            summary_md=f"council 議事録（索引）: `meetings/{f.name}`\n\n{head}",
            topics=None,
            decisions=None,
            open_items=None,
            next_actions=None,
            facts=None,
        )
        n += 1
    return n


def build_daily_digests(
    *,
    date: str,
    learning_db: Path,
    knowledge_db: Path,
    view_dir: Path,
    company_dir: Path,
    meetings_dir: Path,
    model: str,
    min_turns: int,
    notification_channel_ids: tuple,
    timeout_sec: int,
    max_sessions: int,
) -> DigestRun:
    kstore.init_db(knowledge_db)
    run = DigestRun()
    sessions = lstore.list_sessions_for_date(learning_db, date, min_turns=min_turns)
    notif = set(notification_channel_ids)

    for sess in sessions[:max_sessions]:
        cid = sess["channel_id"]
        if cid in notif:
            run.skipped += 1
            continue
        turns = lstore.get_session_turns(learning_db, cid, date)
        if len(turns) < min_turns or _is_command_only(turns):
            run.skipped += 1
            continue
        cname = sess.get("channel_name") or cid
        dept = sess.get("department") or "secretary"
        conv = format_conversation_log(cname, dept, date, turns)
        try:
            res = run_claude(
                prompt=_build_prompt(conv),
                cwd=Path(company_dir),
                model=model,
                # 議事録化は純粋なテキスト変換。ツールは一切不要なので allowed は空、
                # 念のため副作用系・外部アクセス系を disallowed にも明示する。
                allowed_tools="",
                disallowed_tools="Bash Edit Write WebFetch WebSearch Task",
                system_prompt_append=_PERSONA,
                max_turns=1,
                timeout_sec=timeout_sec,
            )
        except Exception:  # noqa: BLE001
            logger.exception("knowledge.digest: run_claude raised for %s/%s", cid, date)
            run.failed += 1
            continue
        if not res.ok or not (res.stdout or "").strip():
            logger.warning(
                "knowledge.digest: claude -p failed for %s/%s (rc=%s)",
                cid,
                date,
                res.returncode,
            )
            run.failed += 1
            continue
        summary, topics, decisions, open_items, next_actions, facts = _parse_output(
            res.stdout
        )
        kstore.upsert_digest(
            knowledge_db,
            channel_id=cid,
            channel_name=cname,
            department=dept,
            date=date,
            source_kind="chat",
            turn_count=len(turns),
            summary_md=summary,
            topics=topics,
            decisions=decisions,
            open_items=open_items,
            next_actions=next_actions,
            facts=facts,
        )
        try:
            views.write_digest_md(
                view_dir=Path(view_dir),
                channel_name=cname,
                department=dept,
                date=date,
                source_kind="chat",
                summary_md=summary,
                topics=topics,
                decisions=decisions,
                open_items=open_items,
                next_actions=next_actions,
                facts=facts,
            )
        except OSError:
            logger.exception(
                "knowledge.digest: write_digest_md failed for %s/%s", cid, date
            )
            run.notes.append(f"{cname}: Markdown書き出し失敗（DBには保存済み）")
        run.processed += 1

    try:
        run.council_indexed = index_council_meetings(
            date=date, knowledge_db=knowledge_db, meetings_dir=meetings_dir
        )
    except Exception:  # noqa: BLE001
        logger.exception("knowledge.digest: index_council_meetings failed")
    return run
