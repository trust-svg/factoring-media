"""Secretary engine — Claude Code CLI or API for Discord integration.

Modes (set via ENGINE_MODE env var):
  "cli"  — Use `claude -p` (subscription, no API cost) [default]
  "api"  — Use Anthropic API (pay-per-use, fallback)
"""

import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import config
from departments import load_department_prompt

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# Per-channel session continuity for `claude -p` (CLI mode).
# Maps channel_id -> {"session_id": uuid_str, "last_used": epoch_seconds}
# Persisted to disk so restarts don't drop context. Idle TTL is long enough
# to span a natural Discord workday (morning -> afternoon -> evening).
_cli_sessions: dict[str, dict] = {}
_CLI_SESSION_TTL_SEC = 12 * 60 * 60  # 12 hours idle = reset
_CLI_SESSIONS_FILE = config.COMPANY_DIR / "secretary" / ".cli_sessions.json"


def _load_cli_sessions() -> None:
    """Load persisted sessions from disk (called once on import)."""
    global _cli_sessions
    if not _CLI_SESSIONS_FILE.exists():
        return
    try:
        data = json.loads(_CLI_SESSIONS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _cli_sessions = data
            logger.info(f"Loaded {len(_cli_sessions)} CLI sessions from disk")
    except Exception as e:
        logger.warning(f"Failed to load CLI sessions: {e}")


def _save_cli_sessions() -> None:
    """Persist sessions to disk."""
    try:
        _CLI_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CLI_SESSIONS_FILE.write_text(
            json.dumps(_cli_sessions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"Failed to save CLI sessions: {e}")


def reset_cli_session(channel_id: str) -> bool:
    """Manually clear a channel's session (for !session reset). Returns True if existed."""
    existed = channel_id in _cli_sessions
    _cli_sessions.pop(channel_id, None)
    _save_cli_sessions()
    return existed


def get_cli_session_info(channel_id: str) -> Optional[dict]:
    """Return current session info for a channel, or None."""
    entry = _cli_sessions.get(channel_id)
    if not entry:
        return None
    age = time.time() - entry["last_used"]
    return {
        "session_id": entry["session_id"],
        "age_minutes": int(age / 60),
        "expires_in_minutes": max(0, int((_CLI_SESSION_TTL_SEC - age) / 60)),
    }


# Load persisted sessions at import time so bot restarts retain context
_load_cli_sessions()


# Engine mode: "cli" (subscription) or "api" (pay-per-use fallback)
ENGINE_MODE = os.getenv("ENGINE_MODE", "cli")

# Company data directory for CLI mode file access instructions
COMPANY_DIR = config.COMPANY_DIR

# Workspace root (for coding agents: Larry, Tim, Mary)
WORKSPACE_DIR = Path(
    __file__
).parent.parent.parent  # products/d-manager/../../.. = Claude-Workspace

# ---------------------------------------------------------------------------
# Shared: system prompt builder
# ---------------------------------------------------------------------------

IDENTITY_PREFIX = """## 最重要ルール
あなたはTrustLinkのAI社員です。以下のCLAUDE.mdで定義された人格として振る舞ってください。
- あなたは「外部のAIアシスタント」ではありません。TrustLinkの組織の一員です。
- 社内の組織構成・メンバー・担当範囲はすべて把握しています（下記CLAUDE.mdに記載）。
- 「分かりません」「社内の連絡先を確認してください」などの汎用的回答は禁止です。
- 質問には組織図・振り分けルールに基づいて具体的なメンバー名と部門で回答してください。
- 話し相手は社長（ロキ）です。敬語は使いますが、堅すぎず親しみのあるトーンで。

## ⚡ 作業前の必須手順（絶対遵守）
1. **rules.md を最初に読む**: `{company_dir}/secretary/rules.md` を Read で読み、全ルールを必ず確認・適用すること。読まずに作業を始めるのは社訓7違反。
2. **絶対日付で処理する**: メール・予定・TODO等で「本日」「明日」「来週」等の相対表現を見たら、必ず受信日時から絶対日付（YYYY-MM-DD）に変換してから処理する。
3. **情報不足時は報告のみ**: 必要なデータが1つでも取得失敗（API失敗・接続失敗・空応答等）したら、そのままレポートを書かず「○○が取得できませんでした。どうしますか？」と人間の判断を仰ぐこと。データを推測・捏造して埋めるのは社訓1違反。
4. **承認なしのファイル/フォルダ作成禁止**: 既存のディレクトリ構成を変更（新フォルダ作成・ファイル移動・リネーム）する場合は、必ず社長の明示的な承認を取ってから実行する。

## 🔧 ミス指導フロー（社長から指摘されたとき）
社長から「違う」「ミスしてる」「おかしい」等の指摘を受けたら、**修正前に必ず以下の順序で対応**:
1. **修正を即座に実行しない**。「直します」と言って手を動かす前に止まる。
2. **原因分析を実行**: 「なぜミスしたのか」を3行以内で分析し、社長に報告。
3. **再発防止策を提案**: 同じミスを繰り返さないための具体的なルールを1〜2個提示。
4. **ルール化して保存**: 社長が承認したら、`{company_dir}/secretary/rules.md` に「## カテゴリ名」セクションでルールを追記する（既存セクションがあればそこに追加）。
5. **保存後に修正**: ルール保存が完了してから、元の作業を修正する。

## 📢 進捗報告ルール（無言禁止）
重い処理（30秒以上かかる作業）では必ず以下を守る:
1. **作業着手の宣言**: 「○○を確認します（30秒ほど）」のように何をやるか先に宣言。
2. **段階表示**: 複数ステップは「[1/3] ○○完了 / [2/3] ○○実行中」と進行状況を示す。
3. **API/外部待ちの明示**: 「Gmail応答待ち」「Calendar取得中」など待機内容を伝える。
4. **無言禁止**: 30秒以上アクションログを出さない場合は社訓8違反。

## 🧠 メモリーシステム（3階層）
作業の記録と学びは `{company_dir}/secretary/memory/` に蓄積する:
- **raw/<YYYY-MM-DD>.md**: その日の行動ログ（時系列の生データ）。重要なアクション後に追記。
- **facts/<topic>.md**: トピック別の事実リスト（例: facts/ロキ_好み.md）。確定事実のみ。
- **digest/<topic>.md**: 学び・気づきの要約（例: digest/メール返信.md）。再利用可能な知見。

**使い方**:
- 作業中: 重要な発見・実行結果を `raw/` に追記（時刻付き）
- 夕レビュー: その日の `raw/` を読み、facts/digest に昇格
- タスク開始時: 関連する `digest/<topic>.md` を Read で確認（あれば過去の学びを反映）

## 🤝 オーケストレーター（他エージェント呼び出し）
**Steve / Reid のみ使用可**。他部門の知見が必要なときは、`tools/agent_call.py` を Bash で呼び出す:

```
cd products/d-manager && python3 -c "from tools.agent_call import call_agent; print(call_agent('marketing', '今朝のCPA異常を3行で要約'))"
```

- 結果を**批評・統合・追加質問**してから最終回答を作ること
- 自分（呼び出し元）と同じ部門は呼ばない（無限ループ防止）
- 再帰呼び出しは深度2まで（自動的に RecursionError）
- 通常の dispatch（Discord 経由）と違い、**同期で応答が返る**

## 🛠️ スキル（再現性のある手順書）
特定タスクには事前定義された手順書がある。`{company_dir}/skills/` を確認:
- `article-writing.md` — 記事執筆（Sheryl）
- `meeting-prep.md` — 商談前リサーチ（Steve）
- `ad-report.md` — 広告レポート要約（Mark）

タスクが該当する場合は **必ず該当スキルを Read してから手順通りに実行**。
スキル一覧は `{company_dir}/skills/README.md` で随時確認。

## 🎫 チケットシステム（AI社員のタスク管理）
複数ステップ・複数日にまたがる作業は **必ず**チケット起票する。`{company_dir}/tickets/` で管理:
- **active/<id>.md**: 進行中チケット
- **done/<id>.md**: 完了チケット
- **archive/<YYYY-MM>/**: 月次アーカイブ

**TODO とチケットの違い（混同禁止）**:
- TODO（{company_dir}/secretary/todos/）= ロキ自身が手を動かす作業
- チケット（{company_dir}/tickets/）= AI社員（自分たち）が実行する作業

**使い方**:
- dispatch で作業を受けたら、即チケット起票（tools/tickets.py の create_ticket を Bash で）
- 進捗が変わるたびに append_log / update_status で更新
- 完了時は update_status(id, "done", note) で done/ に自動移動
- ID 参照（"ticket-XXXX を読んで…"）で他エージェントに引き継ぎ可能

## 社訓（行動憲章 — 絶対遵守）
1. 嘘をつくな 捏造するな
2. 出来ぬなら出来ぬと言え
3. 正確は完遂に勝る
4. 古い情報を使い回すな（必ず最新データを取得せよ）
5. 全ての仕事はチケットにせよ
6. 計画なき実行は暴走なり
7. 学びを記録せよ
8. 待機するな 即動け
9. 遅延は即報告
10. 違反は即退場

## 回答スタイル（厳守）
- 必ず実データを確認し、具体的な数値・件数・日付で回答すること。
- 「確認してください」ではなく、自分で確認して結果を報告すること。
- TODOは件数・放置日数・期限を明示。メールは差出人・件名・日時を明示。予定は時間を明示。
- 曖昧な回答は禁止（「いくつか」「たくさん」→ 具体的な数値）。データがなければ「該当データなし」と明確に伝える。

## 書式ルール（厳守）
- **太字**で重要な数値・固有名詞を強調
- 絵文字を見出しに使い、セクションを視覚的に分離（📊📋💡🎯⚡🔴🟡🟢）
- 箇条書きは階層化して情報密度を高める
- 1セクション3-5行以内。長文禁止。
- 提案は選択肢形式で提示（A案/B案/C案 → 推奨を明示）
- **禁止**: コードブロック（```）・インラインコード（`）・ブロッククォート（>）は絶対に使わない（Discordでグレーボックスになるため）
- **禁止**: ━━罫線でメッセージ全体を囲まない（前後に1本ずつ入れるのみOK）

## データファイルの場所
以下のファイルを直接読み書きしてデータを操作してください:
- 個人ルール（必読）: {company_dir}/secretary/rules.md
- TODO: {company_dir}/secretary/todos/active.md
- 夢・目標: {company_dir}/secretary/dreams/dreams.md
- 経費: {company_dir}/secretary/expenses/YYYY-MM.md
- Inbox: {company_dir}/secretary/inbox/YYYY-MM-DD.md
- 人物DB: {company_dir}/secretary/people/<名前>.md
- 商談前リサーチ: {company_dir}/secretary/research/YYYY-MM-DD_<案件>.md
- メモリー（行動ログ）: {company_dir}/secretary/memory/raw/YYYY-MM-DD.md
- メモリー（事実）: {company_dir}/secretary/memory/facts/<topic>.md
- メモリー（学び）: {company_dir}/secretary/memory/digest/<topic>.md

"""


def _build_system_prompt(department: str) -> str:
    """Build full system prompt with identity + department + datetime."""
    now = datetime.now(JST)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_info = (
        f"\n\n## 現在の日時\n"
        f"{now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}) "
        f"{now.strftime('%H:%M')} JST"
    )
    identity = IDENTITY_PREFIX.format(company_dir=COMPANY_DIR)
    return identity + load_department_prompt(department) + date_info


# ---------------------------------------------------------------------------
# CLI mode: use `claude -p` (subscription-based, no API cost)
# ---------------------------------------------------------------------------


def _get_or_create_cli_session(channel_id: str) -> tuple[str, bool]:
    """Return (session_uuid, is_new) for a channel. Resets after idle TTL."""
    now = time.time()
    entry = _cli_sessions.get(channel_id)
    if entry and (now - entry["last_used"]) < _CLI_SESSION_TTL_SEC:
        entry["last_used"] = now
        _save_cli_sessions()
        return entry["session_id"], False
    new_id = str(uuid.uuid4())
    _cli_sessions[channel_id] = {"session_id": new_id, "last_used": now}
    _save_cli_sessions()
    return new_id, True


def _process_cli(user_message: str, department: str, channel_id: str) -> str:
    """Process message using Claude Code CLI (`claude -p`).

    Maintains per-channel session continuity via --session-id / --resume so that
    follow-up messages share context (instead of each turn being a cold start).
    """
    session_id, is_new = _get_or_create_cli_session(channel_id)

    if is_new:
        # First turn: include full system prompt + user message
        system_prompt = _build_system_prompt(department)
        full_prompt = f"{system_prompt}\n\n---\n\nユーザーメッセージ:\n{user_message}"
        session_arg = ["--session-id", session_id]
    else:
        # Continuation: resume — system prompt already in session history
        full_prompt = user_message
        session_arg = ["--resume", session_id]

    try:
        cmd = [
            "claude",
            "-p",
            full_prompt,
            "--output-format",
            "text",
            "--max-turns",
            "20",
            "--dangerously-skip-permissions",
            *session_arg,
        ]
        if config.CLAUDE_MODEL_CLI:
            cmd.extend(["--model", config.CLAUDE_MODEL_CLI])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(COMPANY_DIR),
        )

        logger.info(
            f"CLI session={session_id[:8]} new={is_new} returncode={result.returncode} "
            f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}"
        )
        if result.stderr:
            # Log full stderr (up to 2KB) for diagnosis instead of truncating to 500
            logger.warning(f"CLI stderr (full): {result.stderr[:2000]}")

        # If --resume failed for any reason on a continuation, drop and retry as new.
        # Old condition required "session" in stderr — too narrow; resume can fail silently
        # or with different error wording. Be permissive: any non-zero returncode on resume
        # triggers fallback to fresh session.
        if not is_new and (result.returncode != 0 or not result.stdout.strip()):
            logger.warning(
                f"Resume failed for {session_id[:8]} (rc={result.returncode}) — recreating session. "
                f"stderr: {(result.stderr or '')[:300]}"
            )
            _cli_sessions.pop(channel_id, None)
            _save_cli_sessions()
            return _process_cli(user_message, department, channel_id)

        if result.stdout.strip():
            return result.stdout.strip()
        else:
            error = (
                result.stderr.strip()
                if result.stderr
                else f"returncode={result.returncode}, stdout empty"
            )
            logger.error(f"CLI error: {error}")
            return (
                f"⚠️ 処理中にエラーが発生しました。少し後にもう一度話しかけてください。"
            )

    except subprocess.TimeoutExpired:
        logger.error("CLI timeout (300s)")
        return "⚠️ 処理がタイムアウトしました。もう少しシンプルに聞いてみてください。"
    except FileNotFoundError:
        logger.error("claude CLI not found, falling back to API")
        return _process_api(user_message, department, channel_id)
    except Exception as e:
        logger.error(f"CLI unexpected error: {e}")
        return f"⚠️ エラーが発生しました: {e}"


def execute_task(agent: str, task: str, is_coding: bool = False) -> str:
    """Execute a dispatched task as an autonomous agent.

    Unlike process_message (chat mode), this is work mode:
    - Higher turn limit for multi-step execution
    - cwd = workspace root for coding agents, COMPANY_DIR otherwise
    - Explicitly told to DO the work, not describe it
    - Returns a brief completion report

    Args:
        agent: Agent name (e.g. "Elon", "Larry")
        task: Task description
        is_coding: If True, run from workspace root (for code changes)
    """
    from tools.dispatch import AGENT_DEPT

    department = AGENT_DEPT.get(agent, "secretary")
    system_prompt = _build_system_prompt(department)

    work_prompt = f"""{system_prompt}

---

## 作業モード（重要）
あなたは今、実際に仕事を実行するよう依頼されています。
- 「〜します」「〜してください」ではなく、今すぐ実行してください
- ファイルの作成・編集は Write/Edit ツールで実際に行うこと
- 調査はWebSearchや実データ取得で行うこと
- 完了後は「何を行ったか」を具体的に報告すること（ファイルパス・件数・結果を含む）
- 社訓6: 計画なき実行は暴走なり — 3ステップ以上は先に手順を書いてから実行

作業依頼:
{task}
"""

    cwd = str(WORKSPACE_DIR) if is_coding else str(COMPANY_DIR)

    try:
        cmd = [
            "claude",
            "-p",
            work_prompt,
            "--output-format",
            "text",
            "--max-turns",
            "20",
            "--dangerously-skip-permissions",
        ]
        if config.CLAUDE_MODEL_CLI:
            cmd.extend(["--model", config.CLAUDE_MODEL_CLI])

        logger.info(
            f"execute_task: agent={agent} dept={department} coding={is_coding} cwd={cwd}"
        )
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min for work tasks
            cwd=cwd,
        )

        logger.info(
            f"execute_task returncode={result.returncode} stdout_len={len(result.stdout)}"
        )
        if result.stderr:
            logger.warning(f"execute_task stderr: {result.stderr[:300]}")

        if result.stdout.strip():
            return result.stdout.strip()
        error = (
            result.stderr.strip()
            if result.stderr
            else f"returncode={result.returncode}"
        )
        return f"⚠️ 作業中にエラーが発生しました: {error}"

    except subprocess.TimeoutExpired:
        return "⚠️ 作業がタイムアウトしました（10分）。タスクを小さく分割して再依頼してください。"
    except Exception as e:
        logger.error(f"execute_task error: {e}")
        return f"⚠️ 実行エラー: {e}"


# ---------------------------------------------------------------------------
# API mode: use Anthropic API (pay-per-use fallback)
# ---------------------------------------------------------------------------

# Lazy-load API dependencies only when needed
_api_client = None
_api_tools = None
_api_tool_functions = None


def _ensure_api():
    """Lazy-load API client and tools."""
    global _api_client, _api_tools, _api_tool_functions

    if _api_client is not None:
        return

    from anthropic import Anthropic, APIStatusError
    from tools.todo import (
        get_today_todos,
        add_todo,
        complete_todo,
        update_todo,
        capture_inbox,
        get_pending_summary,
        set_state,
    )
    from tools.expense import record_expense, get_expense_summary
    from tools.dream import (
        add_dream,
        list_dreams,
        update_dream,
        complete_dream,
        get_pyramid_summary,
        get_future_timeline,
    )
    from tools.google_ads_tool import (
        google_ads_list_conversions,
        google_ads_add_negative_kw,
        google_ads_remove_negative_kw,
        google_ads_add_kw,
        google_ads_weekly_report,
        google_ads_search_terms,
    )

    # --- Meta Ads Tools ---
    from tools.meta_ads_tool import (
        meta_ads_weekly_report,
        meta_ads_campaign_status,
        meta_ads_pause_campaign,
        meta_ads_resume_campaign,
        meta_ads_set_budget,
        meta_ads_creative_fatigue,
    )
    from tools.youtube import get_transcript
    from tools.x_scraper import get_user_tweets, search_tweets, get_trending

    _api_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    _api_tools = [
        {
            "name": "get_today_todos",
            "description": "今日のTODOリストを取得する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "add_todo",
            "description": "新しいTODOを追加する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "priority": {"type": "string", "enum": ["高", "通常", "低"]},
                },
                "required": ["text"],
            },
        },
        {
            "name": "complete_todo",
            "description": "TODOを完了にする",
            "input_schema": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
        },
        {
            "name": "update_todo",
            "description": "既存TODOのタスク名を更新する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "new_title": {"type": "string"},
                },
                "required": ["keyword", "new_title"],
            },
        },
        {
            "name": "set_todo_state",
            "description": "TODOの状態を変更する（UN=未着手 / IN=着手中 / BL=待ち）。BLにする場合は block_reason を必ず添える。完了は complete_todo を使う。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "new_state": {"type": "string", "enum": ["UN", "IN", "BL"]},
                    "block_reason": {"type": "string"},
                },
                "required": ["keyword", "new_state"],
            },
        },
        {
            "name": "capture_inbox",
            "description": "Inboxにメモを記録する",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
        {
            "name": "get_pending_summary",
            "description": "未完了タスク・期限切れの概要を取得",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "record_expense",
            "description": "経費を記録する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "integer"},
                    "category": {"type": "string"},
                },
                "required": ["description", "amount"],
            },
        },
        {
            "name": "get_expense_summary",
            "description": "月間の経費サマリーを取得",
            "input_schema": {
                "type": "object",
                "properties": {"month": {"type": "string"}},
                "required": [],
            },
        },
        {
            "name": "add_dream",
            "description": "夢・やりたいことを追加する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "priority": {"type": "string"},
                    "target_date": {"type": "string"},
                    "goals": {"type": "string"},
                },
                "required": ["title"],
            },
        },
        {
            "name": "list_dreams",
            "description": "夢・やりたいことリストを取得する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": [],
            },
        },
        {
            "name": "update_dream",
            "description": "夢の進捗・予定日・優先度を更新する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "progress": {"type": "integer"},
                    "target_date": {"type": "string"},
                    "priority": {"type": "string"},
                    "goals": {"type": "string"},
                },
                "required": ["keyword"],
            },
        },
        {
            "name": "complete_dream",
            "description": "夢を達成済みにする",
            "input_schema": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
        },
        {
            "name": "get_pyramid_summary",
            "description": "夢・人生ピラミッドの全体像を表示する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_future_timeline",
            "description": "未来年表を表示する",
            "input_schema": {
                "type": "object",
                "properties": {"year": {"type": "integer"}},
                "required": [],
            },
        },
        {
            "name": "google_ads_list_conversions",
            "description": "Google Adsのコンバージョンアクション一覧を取得する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "google_ads_add_negative_kw",
            "description": "Google Adsのアクティブキャンペーンに除外キーワードを追加する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "除外するキーワードのリスト",
                    }
                },
                "required": ["keywords"],
            },
        },
        {
            "name": "google_ads_remove_negative_kw",
            "description": "Google Adsのアクティブキャンペーンから除外キーワードを削除する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "削除する除外キーワードのリスト",
                    }
                },
                "required": ["keywords"],
            },
        },
        {
            "name": "google_ads_add_kw",
            "description": "Google Adsのアクティブ広告グループにキーワードを追加する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "追加するキーワードのリスト",
                    },
                    "match_type": {
                        "type": "string",
                        "enum": ["exact", "phrase", "broad"],
                        "description": "マッチタイプ（デフォルト: exact）",
                    },
                },
                "required": ["keywords"],
            },
        },
        {
            "name": "google_ads_weekly_report",
            "description": "Google Adsの直近7日間の週次レポート（キャンペーン＋キーワードTOP5）を取得する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "google_ads_search_terms",
            "description": "Google Adsの検索語句データを取得し、CV有無で分類して分析する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "取得期間（日数、デフォルト: 7）",
                    }
                },
                "required": [],
            },
        },
        # --- Meta Ads Tools ---
        {
            "name": "meta_ads_weekly_report",
            "description": "Meta広告の直近7日間パフォーマンスサマリー（消化・imp・click・CV・CPA）を取得する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "meta_ads_campaign_status",
            "description": "Meta広告の全キャンペーン一覧（ステータス・日予算・直近パフォーマンス）を表示する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "meta_ads_pause_campaign",
            "description": "Meta広告のキャンペーンを名前で一時停止する（部分一致）",
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_name": {
                        "type": "string",
                        "description": "停止するキャンペーン名（部分一致）",
                    }
                },
                "required": ["campaign_name"],
            },
        },
        {
            "name": "meta_ads_resume_campaign",
            "description": "Meta広告の一時停止中キャンペーンを再開する（部分一致）",
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_name": {
                        "type": "string",
                        "description": "再開するキャンペーン名（部分一致）",
                    }
                },
                "required": ["campaign_name"],
            },
        },
        {
            "name": "meta_ads_set_budget",
            "description": "Meta広告キャンペーンの日予算を変更する（JPY）",
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_name": {
                        "type": "string",
                        "description": "対象キャンペーン名（部分一致）",
                    },
                    "daily_budget": {
                        "type": "integer",
                        "description": "新しい日予算（円）",
                    },
                },
                "required": ["campaign_name", "daily_budget"],
            },
        },
        {
            "name": "meta_ads_creative_fatigue",
            "description": "Meta広告のクリエイティブ疲弊チェック（フリークエンシー・CTR低下）を実行する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        # --- YouTube Tools ---
        {
            "name": "get_youtube_transcript",
            "description": "YouTube動画のトランスクリプト（字幕・文字起こし）を取得する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url_or_id": {
                        "type": "string",
                        "description": "YouTube URLまたは動画ID",
                    },
                    "language": {
                        "type": "string",
                        "description": "言語コード（デフォルト: ja）",
                    },
                },
                "required": ["url_or_id"],
            },
        },
        # --- X (Twitter) Tools ---
        {
            "name": "get_x_user_tweets",
            "description": "X(Twitter)の公開アカウントの最新ツイートを取得する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Xのユーザー名（@あり・なし両方可）",
                    },
                    "count": {
                        "type": "integer",
                        "description": "取得件数（デフォルト: 10、最大20）",
                    },
                },
                "required": ["username"],
            },
        },
        {
            "name": "search_x_tweets",
            "description": "X(Twitter)でキーワード・ハッシュタグを検索する",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "検索クエリ（ハッシュタグ・キーワード）",
                    },
                    "count": {
                        "type": "integer",
                        "description": "取得件数（デフォルト: 10、最大20）",
                    },
                    "lang": {
                        "type": "string",
                        "description": "言語フィルター（デフォルト: ja）",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_x_trending",
            "description": "X(Twitter)の日本のトレンドトピックを取得する",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ]

    _api_tool_functions = {
        "get_today_todos": lambda **_: get_today_todos(),
        "add_todo": lambda **kw: add_todo(kw["text"], kw.get("priority", "通常")),
        "complete_todo": lambda **kw: complete_todo(kw["keyword"]),
        "update_todo": lambda **kw: update_todo(kw["keyword"], kw["new_title"]),
        "capture_inbox": lambda **kw: capture_inbox(kw["text"]),
        "set_todo_state": lambda **kw: set_state(
            kw["keyword"], kw["new_state"], kw.get("block_reason", "")
        ),
        "get_pending_summary": lambda **_: json.dumps(
            get_pending_summary(), ensure_ascii=False
        ),
        "record_expense": lambda **kw: record_expense(
            kw["description"], kw["amount"], kw.get("category", "その他")
        ),
        "get_expense_summary": lambda **kw: json.dumps(
            get_expense_summary(kw.get("month", "")), ensure_ascii=False
        ),
        "add_dream": lambda **kw: add_dream(
            kw["title"],
            kw.get("category", "未分類"),
            kw.get("priority", "B"),
            kw.get("target_date", ""),
            kw.get("goals", ""),
        ),
        "list_dreams": lambda **kw: list_dreams(
            kw.get("category", ""), kw.get("status", "active")
        ),
        "update_dream": lambda **kw: update_dream(
            kw["keyword"],
            kw.get("progress"),
            kw.get("target_date"),
            kw.get("priority"),
            kw.get("goals"),
        ),
        "complete_dream": lambda **kw: complete_dream(kw["keyword"]),
        "get_pyramid_summary": lambda **_: get_pyramid_summary(),
        "get_future_timeline": lambda **kw: get_future_timeline(kw.get("year")),
        "google_ads_list_conversions": lambda **_: google_ads_list_conversions(),
        "google_ads_add_negative_kw": lambda **kw: google_ads_add_negative_kw(
            kw["keywords"]
        ),
        "google_ads_remove_negative_kw": lambda **kw: google_ads_remove_negative_kw(
            kw["keywords"]
        ),
        "google_ads_add_kw": lambda **kw: google_ads_add_kw(
            kw["keywords"], kw.get("match_type", "exact")
        ),
        "google_ads_weekly_report": lambda **_: google_ads_weekly_report(),
        "google_ads_search_terms": lambda **kw: google_ads_search_terms(
            kw.get("days", 7)
        ),
        # --- Meta Ads Tools ---
        "meta_ads_weekly_report": lambda **_: meta_ads_weekly_report(),
        "meta_ads_campaign_status": lambda **_: meta_ads_campaign_status(),
        "meta_ads_pause_campaign": lambda **kw: meta_ads_pause_campaign(
            kw["campaign_name"]
        ),
        "meta_ads_resume_campaign": lambda **kw: meta_ads_resume_campaign(
            kw["campaign_name"]
        ),
        "meta_ads_set_budget": lambda **kw: meta_ads_set_budget(
            kw["campaign_name"], kw["daily_budget"]
        ),
        "meta_ads_creative_fatigue": lambda **_: meta_ads_creative_fatigue(),
        # --- YouTube Tools ---
        "get_youtube_transcript": lambda **kw: get_transcript(
            kw["url_or_id"], kw.get("language", "ja")
        ),
        # --- X (Twitter) Tools ---
        "get_x_user_tweets": lambda **kw: get_user_tweets(
            kw["username"], kw.get("count", 10)
        ),
        "search_x_tweets": lambda **kw: search_tweets(
            kw["query"], kw.get("count", 10), kw.get("lang", "ja")
        ),
        "get_x_trending": lambda **_: get_trending(),
    }


def _process_api(user_message: str, department: str, channel_id: str) -> str:
    """Process message using Anthropic API (fallback mode)."""
    from anthropic import APIStatusError

    _ensure_api()
    system_prompt = _build_system_prompt(department)

    history = conversations.get(channel_id, [])
    history.append({"role": "user", "content": user_message})
    if len(history) > MAX_HISTORY * 2:
        history = history[-MAX_HISTORY * 2 :]
    conversations[channel_id] = history

    messages = list(history)
    max_iterations = 10
    text_parts = []

    for _ in range(max_iterations):
        response = None
        for attempt in range(3):
            try:
                response = _api_client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=_api_tools,
                    messages=messages,
                )
                break
            except APIStatusError as e:
                if e.status_code in (429, 529) and attempt < 2:
                    wait = 5 * (2**attempt)
                    logger.warning(
                        f"API {e.status_code}, retrying in {wait}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait)
                else:
                    raise

        if response is None:
            result = "⚠️ APIが混み合っています。少し後にもう一度話しかけてください。"
            history.append({"role": "assistant", "content": result})
            return result

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if not tool_calls:
            result = "\n".join(text_parts)
            history.append({"role": "assistant", "content": result})
            return result

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            func = _api_tool_functions.get(tc.name)
            if func:
                try:
                    r = func(**tc.input)
                except Exception as e:
                    r = f"エラー: {e}"
            else:
                r = f"不明なツール: {tc.name}"
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": str(r),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    result = "\n".join(text_parts) if text_parts else "処理がタイムアウトしました。"
    history.append({"role": "assistant", "content": result})
    return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

conversations = {}
MAX_HISTORY = 20


def process_message(user_message: str, department: str, channel_id: str) -> str:
    """Process a message — dispatches to CLI or API based on ENGINE_MODE."""
    if ENGINE_MODE == "cli":
        return _process_cli(user_message, department, channel_id)
    else:
        return _process_api(user_message, department, channel_id)
