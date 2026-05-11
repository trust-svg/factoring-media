"""オーケストレーター用：他エージェントを「ツール」として呼び出す。

通常の dispatch は Discord 経由で fire-and-forget だが、agent_call は
**同期的に応答を取得して返す**ので、呼び出し元のエージェント（Steve など）が
結果を批評・統合・追加質問できる。

使い方（Steve のシステムプロンプト経由）:
    Bash 経由で:
        cd products/d-manager && python3 -c \\
        "from tools.agent_call import call_agent; \\
         print(call_agent('research', '今週のAIニュースを5行で'))"

注意:
- 同期実行のため、深いネスト（A→B→C→…）はトークン消費が指数的に増える。
- max_depth=2 で再帰深度を制限（A が B を呼び、B が C を呼ぶまで）。
- 同じセッションは使わず、毎回新規セッションで実行（context 汚染を避ける）。
"""

import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DEPTH = 2
_call_depth_counter = {"value": 0}


def call_agent(
    department: str,
    prompt: str,
    timeout: int = 180,
    max_depth: Optional[int] = None,
) -> str:
    """他部門のエージェントを呼び出して応答を返す。

    Args:
        department: 呼び出し先の部門名（research / marketing / finance / content / ...）
        prompt:     依頼内容
        timeout:    秒（デフォルト180秒）
        max_depth:  再帰呼び出しの最大深度

    Returns:
        呼び出し先エージェントの応答テキスト。

    Raises:
        RecursionError: max_depth を超えた場合。
    """
    md = max_depth if max_depth is not None else _DEFAULT_MAX_DEPTH
    if _call_depth_counter["value"] >= md:
        msg = f"agent_call depth limit reached ({md}). 呼び出し元で処理を完結させてください。"
        logger.warning(msg)
        raise RecursionError(msg)

    _call_depth_counter["value"] += 1
    try:
        # 遅延 import（循環依存回避のため）
        from ai_engine import process_message

        # 一意のチャンネルIDで呼び出し → セッションが共有されない
        synthetic_channel = f"agent-call-{uuid.uuid4().hex[:8]}"
        logger.info(
            f"agent_call → dept={department} depth={_call_depth_counter['value']} "
            f"prompt_len={len(prompt)}"
        )
        # process_message は同期関数なので直接呼び出し
        # （非同期ループの中から呼ぶ場合は run_in_executor が必要だが、
        #  Bash 経由で呼ばれる前提なので OK）
        old_timeout = os.environ.get("CLAUDE_CLI_TIMEOUT")
        os.environ["CLAUDE_CLI_TIMEOUT"] = str(timeout)
        try:
            result = process_message(prompt, department, synthetic_channel)
        finally:
            if old_timeout:
                os.environ["CLAUDE_CLI_TIMEOUT"] = old_timeout
            else:
                os.environ.pop("CLAUDE_CLI_TIMEOUT", None)
        return result
    finally:
        _call_depth_counter["value"] -= 1


def reset_depth() -> None:
    """デプスカウンターをリセット（プロセス再起動時 or テスト用）。"""
    _call_depth_counter["value"] = 0
