"""親コマンド（チェーン dispatch）— 複数エージェントを連携させて動かすフロー定義。

ワークフローパターン (mode):
  - sequential : 直列実行（A → B → C）。各ステップは前ステップの結果に依存。
  - parallel   : 並行実行。全ステップが同時に走る。時間短縮目的。
  - loop       : 条件を満たすまで steps を繰り返し実行。max_iterations で上限。

定義方法:
    FLOWS = {
        "<flow_name>": {
            "description": "...",
            "args": ["arg1", "arg2"],
            "owner": "...",
            "channel": "...",
            "mode": "sequential" | "parallel" | "loop",
            "steps": [
                ("agent", "プロンプト（{ticket_id}/{arg} が使える）"),
                ...
            ],
            # loop モード専用
            "max_iterations": 5,
            "stop_keyword": "DONE",   # この文字列がレスポンスにあればループ終了
        }
    }

実行: `await run_flow("article-factory", {"topic": "...", "site": "..."}, send_fn)`
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from ai_engine import process_message
from tools import tickets

logger = logging.getLogger(__name__)


FLOWS: dict[str, dict] = {
    "article-factory": {
        "description": "記事1本を量産: Elon(リサーチ) → Sheryl(執筆) → Mark(SEOチェック)",
        "args": ["site", "topic"],
        "owner": "sheryl",
        "channel": "マーケティング-mark-marketing",
        "mode": "sequential",
        "steps": [
            (
                "research",
                "{site} の記事として「{topic}」のリサーチを実行してください。"
                "チケット {ticket_id} に紐づきます。append_log で進捗を記録し、"
                "完了時にリサーチ結果のサマリーを残してください。",
            ),
            (
                "content",
                "チケット {ticket_id} のリサーチ結果を読み、{site} 向けの記事原稿を作成してください。"
                "skills/article-writing.md の手順に従うこと。完了時に原稿のファイルパスを記録。",
            ),
            (
                "marketing",
                "チケット {ticket_id} の原稿をSEO観点でレビューし、改善提案を3点以内で記録してください。"
                "致命的な問題があれば status=blocked にしてロキにエスカレーション。",
            ),
        ],
    },
    "ebay-research": {
        "description": "eBay仕入候補リサーチ: Elon(市場) → Jack(仕入候補) → Sara(出品文案)",
        "args": ["category"],
        "owner": "jack",
        "channel": "運営-jack-operations",
        "mode": "sequential",
        "steps": [
            (
                "research",
                "eBayカテゴリ「{category}」の直近30日の売れ筋を調査してください。"
                "チケット {ticket_id} に append_log で結果を記録。",
            ),
            (
                "operations",
                "チケット {ticket_id} のリサーチを元に、仕入候補を5件まで絞り込んでください。"
                "各候補の利益率見込みを記録。",
            ),
            (
                "content",
                "チケット {ticket_id} の仕入候補に対して、eBay 出品タイトル・説明文の案を作成してください。",
            ),
        ],
    },
    "meeting-prep": {
        "description": "商談前リサーチ: Steve が単独で skills/meeting-prep.md に従って実行",
        "args": ["target"],
        "owner": "steve",
        "channel": "秘書-steve-general",
        "mode": "sequential",
        "steps": [
            (
                "secretary",
                "「{target}」との商談準備を skills/meeting-prep.md の手順で実行してください。"
                "チケット {ticket_id} に進捗を記録し、完了時にリサーチノートのパスを残すこと。",
            ),
        ],
    },
    "sns-research": {
        "description": "SNSバズリサーチ: Elon が sns-research スキルでジャンル別バズ投稿を収集し指示書まで生成",
        "args": ["genre"],
        "defaults": {"platforms": "all", "days": "7"},
        "owner": "elon",
        "channel": "調査-elon-research",
        "mode": "sequential",
        "steps": [
            (
                "research",
                "sns-research スキルを使って、ジャンル「{genre}」のSNSバズリサーチを実行してください。\n"
                '- プラットフォーム: {platforms} ("all" または "x,threads,youtube" 等)\n'
                "- 期間: 過去 {days} 日\n"
                "- チケット {ticket_id} に append_log で進捗を記録\n\n"
                "完了時に1メッセージで:\n"
                "1. **バズ投稿トップ5** (プラットフォーム/投稿者/エンゲージメント/一行要旨)\n"
                "2. **検出トレンド** (3〜5個)\n"
                "3. **ライター指示書サマリー** (3〜5行)\n\n"
                "書式: 太字・箇条書き・絵文字 OK。コードブロック禁止。",
            ),
        ],
    },
    "council": {
        "description": (
            "council: マルチエージェント議論。Thread作成→各員発言(最大2巡)→Steve要約→[→Agent]に分解。"
            "実体は tools/council.py。main.py が直接ハンドル（mode='external'）。"
        ),
        "args": ["topic"],
        "defaults": {"preset": "経営会議"},
        "owner": "steve",
        "channel": "ceo-steve-general",
        "mode": "external",  # main.py で intercept される
        "steps": [],
    },
    "morning-parallel": {
        "description": "朝の並行ブリーフィング: Elon/Mark/Warren を同時実行 → Steve が統合",
        "args": [],
        "owner": "steve",
        "channel": "秘書-steve-general",
        "mode": "parallel",
        "steps": [
            (
                "research",
                "今朝の業界ニュース・X バズ・AIトレンドを 5行以内で要約してください。"
                "チケット {ticket_id} に append_log で記録。",
            ),
            (
                "marketing",
                "今朝の広告レポート（Google/Meta）を skills/ad-report.md に従って要約してください。"
                "チケット {ticket_id} に append_log で記録。",
            ),
            (
                "finance",
                "今月の経費・売上の進捗を確認し、要注意項目があれば抽出してください。"
                "チケット {ticket_id} に append_log で記録。",
            ),
        ],
        # parallel 後の統合ステップ（自動で sequential として最後に走る）
        "post": [
            (
                "secretary",
                "チケット {ticket_id} の append_log を全て読み、Elon/Mark/Warren 3名のレポートを"
                "統合した朝のブリーフィングを作成してください。最後に「今日の最優先タスク」を1〜2個提示。",
            ),
        ],
    },
}


def list_flows() -> list[tuple[str, str]]:
    """フロー名と説明のリスト。"""
    return [(name, info["description"]) for name, info in FLOWS.items()]


# ---------------------------------------------------------------------------
# Mode 別の実行ロジック
# ---------------------------------------------------------------------------


async def _run_step(
    agent: str,
    prompt_tpl: str,
    args: dict,
    ticket_id: str,
    flow_name: str,
    step_marker: str,
    channel: str,
    send_fn: Optional[Callable[[str, str], Awaitable[None]]],
) -> tuple[bool, str]:
    """単一ステップを実行。 (success, result_or_error) を返す。"""
    prompt = prompt_tpl.format(ticket_id=ticket_id, **args)
    tickets.append_log(ticket_id, f"step start — {step_marker}")
    if send_fn:
        await send_fn(channel, f"⏳ {step_marker} 実行中…")
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            process_message,
            prompt,
            agent,
            f"flow-{flow_name}-{ticket_id}",
        )
        tickets.append_log(ticket_id, f"step done — {step_marker}")
        if send_fn:
            preview = (result[:1200] + "…") if len(result) > 1200 else result
            await send_fn(channel, f"✅ {step_marker} 完了\n\n{preview}")
        return True, result
    except Exception as e:
        err = f"step failed — {step_marker}: {e}"
        logger.error(err)
        if send_fn:
            await send_fn(channel, f"🔴 {step_marker} 失敗 — {e}")
        return False, str(e)


async def _run_sequential(
    flow: dict,
    args: dict,
    ticket_id: str,
    send_fn: Optional[Callable[[str, str], Awaitable[None]]],
    flow_name: str,
) -> bool:
    """直列実行。1つでも失敗したら中断。"""
    channel = flow.get("channel", "秘書-steve-general")
    steps = flow["steps"]
    for idx, (agent, prompt_tpl) in enumerate(steps, 1):
        marker = f"[{idx}/{len(steps)}] {agent}"
        ok, _ = await _run_step(
            agent, prompt_tpl, args, ticket_id, flow_name, marker, channel, send_fn
        )
        if not ok:
            tickets.update_status(
                ticket_id, "blocked", note=f"sequential 中断: {marker}"
            )
            return False
    return True


async def _run_parallel(
    flow: dict,
    args: dict,
    ticket_id: str,
    send_fn: Optional[Callable[[str, str], Awaitable[None]]],
    flow_name: str,
) -> bool:
    """並行実行。全ステップを同時起動し、全完了を待つ。

    `post` キーで sequential な統合ステップを後段に置ける。
    """
    channel = flow.get("channel", "秘書-steve-general")
    steps = flow["steps"]
    if send_fn:
        await send_fn(channel, f"⚡ 並行実行: {len(steps)} ステップを同時起動")

    tasks = []
    for idx, (agent, prompt_tpl) in enumerate(steps, 1):
        marker = f"[par {idx}/{len(steps)}] {agent}"
        tasks.append(
            _run_step(
                agent, prompt_tpl, args, ticket_id, flow_name, marker, channel, send_fn
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    failed = [
        r
        for r in results
        if isinstance(r, Exception) or (isinstance(r, tuple) and not r[0])
    ]
    if failed:
        tickets.update_status(
            ticket_id, "blocked", note=f"parallel: {len(failed)}/{len(steps)} 失敗"
        )
        if send_fn:
            await send_fn(channel, f"🟡 並行ステップ {len(failed)}/{len(steps)} が失敗")
        # post 統合ステップは失敗でも実行しない
        return False

    # 後段の統合ステップ（あれば sequential 実行）
    post = flow.get("post", [])
    for idx, (agent, prompt_tpl) in enumerate(post, 1):
        marker = f"[post {idx}/{len(post)}] {agent}"
        ok, _ = await _run_step(
            agent, prompt_tpl, args, ticket_id, flow_name, marker, channel, send_fn
        )
        if not ok:
            tickets.update_status(ticket_id, "blocked", note=f"post 中断: {marker}")
            return False
    return True


async def _run_loop(
    flow: dict,
    args: dict,
    ticket_id: str,
    send_fn: Optional[Callable[[str, str], Awaitable[None]]],
    flow_name: str,
) -> bool:
    """ループ実行。stop_keyword がレスポンスに出るか、max_iterations 到達まで繰り返す。"""
    channel = flow.get("channel", "秘書-steve-general")
    steps = flow["steps"]
    max_iter = int(flow.get("max_iterations", 5))
    stop_kw = flow.get("stop_keyword", "DONE")

    for it in range(1, max_iter + 1):
        if send_fn:
            await send_fn(channel, f"🔁 ループ {it}/{max_iter} 開始")
        last_result = ""
        for idx, (agent, prompt_tpl) in enumerate(steps, 1):
            marker = f"[loop{it} {idx}/{len(steps)}] {agent}"
            ok, result = await _run_step(
                agent,
                prompt_tpl,
                {**args, "iteration": it},
                ticket_id,
                flow_name,
                marker,
                channel,
                send_fn,
            )
            if not ok:
                tickets.update_status(ticket_id, "blocked", note=f"loop 中断: {marker}")
                return False
            last_result = result
        if stop_kw and stop_kw in last_result:
            tickets.append_log(
                ticket_id, f"loop stopped at iteration {it} (stop_keyword 検出)"
            )
            if send_fn:
                await send_fn(channel, f"🟢 stop_keyword 検出 — ループ {it} で終了")
            return True

    tickets.append_log(ticket_id, f"loop reached max_iterations={max_iter}")
    if send_fn:
        await send_fn(channel, f"🟡 max_iterations({max_iter}) 到達でループ終了")
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_flow(
    flow_name: str,
    args: dict,
    send_fn: Optional[Callable[[str, str], Awaitable[None]]] = None,
    channel_override: Optional[str] = None,
) -> Optional[str]:
    """フローを mode に応じて実行し、親チケットIDを返す。

    channel_override: 進捗送信先を指定した場合、フロー定義の channel を上書き。
    呼び出し元のチャンネル（例: 動画分析-video-research）に出力させたい時に使う。
    """
    base = FLOWS.get(flow_name)
    if not base:
        msg = f"⚠️ 未定義のフロー: `{flow_name}`. 利用可能: {list(FLOWS.keys())}"
        if send_fn:
            await send_fn("秘書-steve-general", msg)
        return None

    flow = dict(base)
    if channel_override:
        flow["channel"] = channel_override

    args = {**flow.get("defaults", {}), **args}

    missing = [a for a in flow["args"] if a not in args]
    if missing:
        msg = f"⚠️ フロー `{flow_name}` に引数不足: {missing}"
        if send_fn:
            await send_fn("秘書-steve-general", msg)
        return None

    mode = flow.get("mode", "sequential")
    title = f"[{flow_name}/{mode}] " + " / ".join(f"{k}={v}" for k, v in args.items())
    ticket_id = tickets.create_ticket(
        title=title,
        owner=flow["owner"],
        detail=(
            f"親フロー: {flow_name}\nmode: {mode}\n引数: {args}\n"
            f"ステップ数: {len(flow['steps'])}"
        ),
    )
    channel = flow.get("channel", "秘書-steve-general")
    logger.info(f"Flow {flow_name} ({mode}) started — ticket={ticket_id}")
    if send_fn:
        await send_fn(
            channel, f"🚀 フロー開始: **{flow_name}** ({mode}) — チケット {ticket_id}"
        )

    if mode == "sequential":
        ok = await _run_sequential(flow, args, ticket_id, send_fn, flow_name)
    elif mode == "parallel":
        ok = await _run_parallel(flow, args, ticket_id, send_fn, flow_name)
    elif mode == "loop":
        ok = await _run_loop(flow, args, ticket_id, send_fn, flow_name)
    else:
        msg = f"⚠️ 未対応の mode: {mode}"
        tickets.update_status(ticket_id, "blocked", note=msg)
        if send_fn:
            await send_fn(channel, msg)
        return ticket_id

    if ok:
        tickets.update_status(ticket_id, "done", note="全ステップ完了")
        if send_fn:
            await send_fn(
                channel, f"🎉 フロー完了: **{flow_name}** (チケット {ticket_id})"
            )
    return ticket_id
