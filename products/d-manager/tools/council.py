"""Council — マルチエージェント議論オーケストレーター。

Discord Thread 内で複数の AI 社員が順番に発言し、Steve が議事をまとめて
社長 Hiro に承認を仰ぐフロー。承認後は既存の `[→ Agent]` dispatch で
各員のタスクに自動分解される。

実行モード:
  - mode="council" を flows.py に登録
  - !run council preset=経営会議 topic="..."
  - !run council members=Steve,Mark,Warren topic="..."

挙動:
  1. #会議-councils 配下に Thread を作成（議題ごとに独立）
  2. 1巡目: 各員が一次意見（forward order）
  3. 収束判定: 全員ほぼ同意見なら 2巡目をスキップ
  4. 2巡目: 反論/補強（reverse order）
  5. Steve が要約 + [→ Agent] dispatch を含む最終提案
  6. 議事録を .company/meetings/YYYY-MM-DD_<slug>.md に保存
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Optional

import config

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Constants & Mappings
# ---------------------------------------------------------------------------

PRESETS_FILE = config.COMPANY_DIR / "presets" / "council.json"
MEETINGS_DIR = config.COMPANY_DIR / "meetings"
MEETINGS_DIR.mkdir(parents=True, exist_ok=True)

# 議論パラメータ
MAX_ROUNDS = 2  # Phase 1: 最大2巡（早期収束あり）
MAX_CHARS_PER_TURN = 400  # 各発言の文字数上限（指示として渡す）
SUMMARY_MAX_CHARS = 1500
PARENT_CHANNEL = "会議-councils"

# エージェントの役割・部門・council 用の発話キャラクター定義
# avatar は main.py の AVATAR_DIR にある画像ファイル名
COUNCIL_AGENTS: dict[str, dict] = {
    "Steve": {"dept": "secretary", "role": "CEO・議長", "avatar": "steve.png"},
    "Jack": {"dept": "operations", "role": "運営部長", "avatar": "riku.png"},
    "Jeff": {"dept": "operations", "role": "仕入担当", "avatar": "kai.png"},
    "Sara": {"dept": "operations", "role": "出品担当", "avatar": "sora.png"},
    "Larry": {"dept": "product", "role": "開発部長", "avatar": "ren.png"},
    "Tim": {"dept": "product", "role": "エンジニア", "avatar": "shin.png"},
    "Mary": {"dept": "product", "role": "デザイナー", "avatar": "mio.png"},
    "Mark": {"dept": "marketing", "role": "マーケ部長", "avatar": "yuu.png"},
    "Sheryl": {"dept": "marketing", "role": "コンテンツ担当", "avatar": "hina.png"},
    "Gary": {"dept": "marketing", "role": "広告担当", "avatar": "haru.png"},
    "Warren": {"dept": "finance", "role": "経理・CFO", "avatar": "kei.png"},
    "Elon": {"dept": "research", "role": "リサーチ部長", "avatar": "akira.png"},
    "Reid": {"dept": "strategy", "role": "経営企画", "avatar": "nao.png"},
}

# 各員の発話スタイル（council 用に簡潔な一文で。ペルソナ全文より軽い）
AGENT_STYLE: dict[str, str] = {
    "Steve": "冷静沈着なCEO。論点整理・最終決断・社長への取りまとめが役割。",
    "Jack": "現場運営目線。実務オペレーション・人手・物流の制約から論じる。",
    "Jeff": "仕入・調達のプロ。コスト・在庫・サプライチェーン視点。",
    "Sara": "出品・販売のプロ。マーケットの反応・売れ筋から論じる。",
    "Larry": "開発部長。技術選定・スケジュール・実装難度を冷静に評価する。",
    "Tim": "エンジニア。実装の具体的な手段とリスクを技術視点で論じる。",
    "Mary": "デザイナー。UX・体験設計・ユーザー心理を重視。",
    "Mark": "マーケ部長。ターゲット・LTV・ファネル・ブランド戦略から論じる。",
    "Sheryl": "コンテンツ担当。SEO・記事戦略・編集方針から具体策を出す。",
    "Gary": "広告担当。CAC・ROAS・媒体特性・予算配分を数字で論じる。",
    "Warren": "CFO・厳しい数字屋。ROI・キャッシュフロー・税務リスクから判断。",
    "Elon": "リサーチ部長。市場データ・競合・トレンドを根拠に論じる。",
    "Reid": "経営企画。中長期視点・選択肢の構造化・戦略の整合性を見る。",
}

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


def load_presets() -> dict[str, dict]:
    """council.json のプリセットセクションを返す。読めなければ空dict。"""
    if not PRESETS_FILE.exists():
        logger.warning(f"council presets file missing: {PRESETS_FILE}")
        return {}
    try:
        data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        return data.get("presets", {})
    except Exception as e:
        logger.warning(f"Failed to load council presets: {e}")
        return {}


def resolve_members(
    preset: Optional[str], members_arg: Optional[str]
) -> tuple[list[str], Optional[str]]:
    """preset または members_arg からメンバーリストを決定。

    Returns: (members, error_message). エラー時は members=[] かつ error_message にメッセージ。
    Steve は必ず先頭に追加される（重複時は重複を除外）。
    """
    members: list[str] = []

    if preset:
        presets = load_presets()
        if preset not in presets:
            return (
                [],
                f"⚠️ 不明なプリセット: `{preset}`. 利用可能: {list(presets.keys())}",
            )
        members = list(presets[preset].get("members", []))
    elif members_arg:
        members = [m.strip() for m in re.split(r"[,\s]+", members_arg) if m.strip()]
    else:
        return [], "⚠️ preset= または members= のどちらかを指定してください"

    # Validate
    invalid = [m for m in members if m not in COUNCIL_AGENTS]
    if invalid:
        return [], (
            f"⚠️ 不明なエージェント: {invalid}. 利用可能: {list(COUNCIL_AGENTS.keys())}"
        )

    # Steve を必ず先頭に
    members = [m for m in members if m != "Steve"]
    members.insert(0, "Steve")

    if len(members) < 2:
        return [], "⚠️ Council は Steve + 1名以上の参加者が必要です"

    return members, None


# ---------------------------------------------------------------------------
# LLM 呼び出し（議論の各フェーズ）
# ---------------------------------------------------------------------------


def _call_api(system: str, user: str, max_tokens: int = 800) -> str:
    """Claude Code CLI を subprocess で同期呼び出し（claude -p）。

    引数名は `_call_api` のままだが、実体は CLI モード（Claude Max サブスク内）。
    `max_tokens` は CLI に直接の上限は設定できないため、参考値として無視する
    （prompt 内の文字数制約で間接的に制御）。
    """
    full_prompt = f"{system}\n\n---\n\n{user}"
    cmd = [
        "claude",
        "-p",
        full_prompt,
        "--output-format",
        "text",
        "--max-turns",
        "1",  # 議論用：tool_use 不要、テキスト1ターンで返す
        "--dangerously-skip-permissions",
    ]
    if config.CLAUDE_MODEL_CLI:
        cmd.extend(["--model", config.CLAUDE_MODEL_CLI])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(config.COMPANY_DIR),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timeout (180s)")
    except FileNotFoundError:
        raise RuntimeError("claude CLI not found in PATH")

    if result.returncode != 0 or not result.stdout.strip():
        err = (result.stderr or "")[:500]
        raise RuntimeError(
            f"claude CLI rc={result.returncode}, stdout_len={len(result.stdout)}, stderr: {err}"
        )

    return result.stdout.strip()


def agent_speak(
    agent: str,
    topic: str,
    prior_log: list[tuple[str, str]],
    round_num: int,
    total_rounds: int,
) -> str:
    """1人のエージェントに発言させる。"""
    info = COUNCIL_AGENTS[agent]
    style = AGENT_STYLE.get(agent, "")

    history_text = (
        "\n\n".join(f"【{spkr}】\n{msg}" for spkr, msg in prior_log)
        if prior_log
        else "（あなたが最初の発言者です）"
    )

    round_guidance = (
        "ラウンド1: あなたの専門分野からの一次意見・問題提起・前提整理。"
        if round_num == 1
        else "ラウンド2: 既出意見への賛否・補強・反論を明確に。"
        " 同意なら理由を補強、反対なら根拠を示し、新しい視点があれば追加。"
    )

    system_prompt = (
        f"あなたは TrustLink の AI 社員「{agent}」です。"
        f"役割: {info['role']}（{info['dept']}部門）。"
        f"発話スタイル: {style}\n"
        f"council（社内会議）に出席しており、各発言は{MAX_CHARS_PER_TURN}字以内で、"
        f"ロジカルかつ簡潔に述べてください。"
        f"推測は『推測:』と明記。数字を出すなら根拠を添えること。"
    )

    user_prompt = f"""# 議題
{topic}

# 現在のラウンド
{round_num} / {total_rounds}（{round_guidance}）

# これまでの発言ログ
{history_text}

# あなたへの依頼
あなたの番です。次の制約で発言してください:
- {MAX_CHARS_PER_TURN}字以内（厳守）
- 結論を必ず1〜2文で明確に
- 余計な前置き不要、本論からスタート
- 「私は…」のような自己紹介不要（誰の発言かは表示済み）
- 他者の意見に言及するときは【Mark】のように名前を出す

発言してください。"""

    return _call_api(system_prompt, user_prompt, max_tokens=600)


def is_converged(topic: str, round1_log: list[tuple[str, str]]) -> bool:
    """1巡目終了時、全員ほぼ同意見なら True。"""
    if len(round1_log) <= 1:
        return False

    history = "\n\n".join(f"【{spkr}】\n{msg}" for spkr, msg in round1_log)
    user_prompt = f"""以下は council 1巡目の発言ログです。
2巡目で反論や深掘りを行う必要があるか判定してください。

# 議題
{topic}

# 1巡目発言
{history}

# 判定ルール
- 全員の方向性が概ね一致し、追加議論が不要 → CONVERGED
- 意見の隔たり・未解決の論点・対立がある → NEEDS_DEBATE

判定理由を1文添え、最終行に CONVERGED または NEEDS_DEBATE のみを書いてください。
"""
    try:
        text = _call_api(
            system="あなたは厳格な議事進行アナリスト。客観的に判定する。",
            user=user_prompt,
            max_tokens=300,
        )
    except Exception as e:
        logger.warning(f"convergence check failed: {e} — defaulting to NEEDS_DEBATE")
        return False
    last_line = text.splitlines()[-1].strip().upper() if text.strip() else ""
    return "CONVERGED" in last_line


def steve_synthesize(
    topic: str, members: list[str], prior_log: list[tuple[str, str]]
) -> str:
    """Steve が議論をまとめ、[→ Agent] dispatch を含む最終提案を生成。"""
    history = "\n\n".join(f"【{spkr}】\n{msg}" for spkr, msg in prior_log)
    candidate_assignees = [m for m in members if m != "Steve"]

    user_prompt = f"""あなたは CEO の Steve です。今、council 会議の議長を務めました。
議論を要約し、社長 Hiro に承認を仰ぐ最終提案を作成してください。

# 議題
{topic}

# 参加メンバー
{", ".join(members)}

# 全発言ログ
{history}

# 出力フォーマット（厳守）
**会議結果**: <1〜2文で結論>

**主要論点**:
- <論点1>
- <論点2>
- <論点3>

**進める方向**: <選んだ案。理由も1文で>

**各員の担当タスク**:
[→ <Agent>] <具体的なタスク>
[→ <Agent>] ...

**Hiro さん、これで進めて良いですか？**

# ルール
- [→ Agent] は dispatch syntax。形式厳守（半角スペース、矢印は →）
- 担当できるエージェント: {", ".join(candidate_assignees)}
- 担当不要な人は含めない（必ずしも全員に振る必要はない）
- {SUMMARY_MAX_CHARS}字以内
- 推測は「推測:」と明記
"""
    return _call_api(
        system="あなたは CEO の Steve。論点整理に長け、決定事項とアクションを明確にする。",
        user=user_prompt,
        max_tokens=2000,
    )


# ---------------------------------------------------------------------------
# 議事録保存
# ---------------------------------------------------------------------------


def save_minutes(
    topic: str,
    members: list[str],
    prior_log: list[tuple[str, str]],
    summary: str,
    rounds_run: int,
    converged_early: bool,
) -> Path:
    """議事録を Markdown で保存し、ファイルパスを返す。"""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    slug = re.sub(r"[^\w぀-ヿ一-鿿]+", "-", topic[:40]).strip("-")
    if not slug:
        slug = "untitled"
    path = MEETINGS_DIR / f"{today}_{slug}.md"

    # 同名既存があれば連番
    n = 2
    while path.exists():
        path = MEETINGS_DIR / f"{today}_{slug}-{n}.md"
        n += 1

    log_md = "\n\n".join(f"### {spkr}\n\n{msg}" for spkr, msg in prior_log)

    content = f"""# Council 議事録: {topic}

- **日時**: {datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")}
- **議題**: {topic}
- **参加者**: {", ".join(members)}
- **実施ラウンド**: {rounds_run}/{MAX_ROUNDS}{"（早期収束）" if converged_early else ""}

---

## 発言ログ

{log_md}

---

## 会議要約（Steve）

{summary}

---

## 承認状況

- [ ] Hiro 承認済み
- [ ] dispatch 実行済み

> Hiro が Discord で「OK」「いいよ」等で承認すると、要約内の `[→ Agent]` が
> 自動 dispatch される（main.py の on_message → parse_dispatches 経由）。
"""

    path.write_text(content, encoding="utf-8")
    logger.info(f"council minutes saved: {path}")
    return path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_council(
    topic: str,
    preset: Optional[str],
    members_arg: Optional[str],
    bot,  # discord.Bot — for Thread creation & guild access
    parent_channel_name: str = PARENT_CHANNEL,
    progress_fn: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Optional[Path]:
    """Council を実行し、議事録パスを返す（失敗時 None）。

    progress_fn: 親チャンネルへの開会/閉会ステータス通知用（任意）。
    Thread への発話は内部で webhook に直接送信する。
    """
    import discord  # local import to avoid hard dependency at module load

    members, err = resolve_members(preset, members_arg)
    if err:
        if progress_fn:
            await progress_fn(err)
        return None

    # 親チャンネル取得
    parent_ch = None
    for guild in bot.guilds:
        parent_ch = discord.utils.get(guild.text_channels, name=parent_channel_name)
        if parent_ch:
            break
    if not parent_ch:
        msg = f"⚠️ 親チャンネル `{parent_channel_name}` が見つかりません"
        logger.error(msg)
        if progress_fn:
            await progress_fn(msg)
        return None

    # Thread 作成
    today = datetime.now(JST).strftime("%Y-%m-%d")
    slug = re.sub(r"[^\w぀-ヿ一-鿿]+", "-", topic[:30]).strip("-") or "topic"
    thread_name = f"会議-{today}-{slug}"[:100]  # Discord limit
    try:
        thread = await parent_ch.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=1440,  # 24h
            reason=f"council: {topic[:80]}",
        )
    except Exception as e:
        msg = f"⚠️ Thread 作成失敗: {e}"
        logger.error(msg)
        if progress_fn:
            await progress_fn(msg)
        return None

    # Webhook 取得（親チャンネルの webhook を thread_id クエリで使い回す）
    webhook = None
    try:
        for w in await parent_ch.webhooks():
            if w.token:
                webhook = w
                break
    except Exception as e:
        logger.warning(f"failed to fetch webhooks: {e}")

    async def post(agent: str, text: str) -> None:
        """Thread に発言投稿。webhook が無ければ thread.send で fallback。"""
        char_name = agent
        chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)] or [""]
        if webhook:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                for chunk in chunks:
                    try:
                        await session.post(
                            f"{webhook.url}?thread_id={thread.id}",
                            json={"content": chunk, "username": char_name},
                            timeout=aiohttp.ClientTimeout(total=30),
                        )
                    except Exception as e:
                        logger.warning(
                            f"webhook post failed: {e}, fallback to thread.send"
                        )
                        try:
                            await thread.send(f"**{char_name}**: {chunk}")
                        except Exception as e2:
                            logger.error(f"thread.send fallback failed: {e2}")
        else:
            for chunk in chunks:
                try:
                    await thread.send(f"**{char_name}**: {chunk}")
                except Exception as e:
                    logger.error(f"thread.send failed: {e}")

    # 親チャンネルに開会通知（Thread リンク付き）
    if progress_fn:
        await progress_fn(
            f"🎯 Council 招集 → Thread `{thread_name}` に移動してください\n"
            f"議題: {topic}\n"
            f"参加者: {', '.join(members)}"
        )

    # Thread 開会宣言
    await post(
        "Steve",
        f"🎯 **Council 招集**\n"
        f"議題: {topic}\n"
        f"参加者: {', '.join(members)}\n"
        f"ラウンド: 最大{MAX_ROUNDS}巡（1巡目で全員同意なら早期終了）",
    )

    # ---- 議論ループ ----
    prior_log: list[tuple[str, str]] = []
    speaker_order = [m for m in members if m != "Steve"] + ["Steve"]
    converged_early = False
    rounds_run = 0

    loop = asyncio.get_event_loop()

    for round_num in range(1, MAX_ROUNDS + 1):
        rounds_run = round_num
        await post("Steve", f"━━━ **ラウンド {round_num}** 開始 ━━━")

        # 1巡目は forward、2巡目は reverse（多様な順序で気づきを引き出す）
        order = speaker_order if round_num == 1 else list(reversed(speaker_order))

        for agent in order:
            try:
                msg = await loop.run_in_executor(
                    None,
                    agent_speak,
                    agent,
                    topic,
                    prior_log,
                    round_num,
                    MAX_ROUNDS,
                )
            except Exception as e:
                logger.exception(f"agent_speak failed for {agent}")
                msg = f"⚠️ 発言生成エラー: {e}"

            await post(agent, msg)
            prior_log.append((agent, msg))
            await asyncio.sleep(1)  # 連投で webhook が rate limit に当たらぬよう小休止

        # 1巡目終了時の収束判定
        if round_num == 1 and MAX_ROUNDS > 1:
            try:
                converged = await loop.run_in_executor(
                    None, is_converged, topic, prior_log
                )
            except Exception:
                converged = False
            if converged:
                converged_early = True
                await post(
                    "Steve",
                    "✅ 1巡目で全員ほぼ同意見と判定 → 2巡目スキップして要約に入ります",
                )
                break

    # ---- Steve 要約 ----
    await post("Steve", "━━━ **会議要約を作成中…** ━━━")
    try:
        summary = await loop.run_in_executor(
            None, steve_synthesize, topic, members, prior_log
        )
    except Exception as e:
        logger.exception("steve_synthesize failed")
        summary = (
            f"⚠️ 要約生成エラー: {e}\n"
            f"議論ログだけ議事録に保存します。手動で確認してください。"
        )

    await post("Steve", summary)

    # ---- 議事録保存 ----
    minutes_path = save_minutes(
        topic=topic,
        members=members,
        prior_log=prior_log,
        summary=summary,
        rounds_run=rounds_run,
        converged_early=converged_early,
    )
    rel_path = (
        minutes_path.relative_to(config.COMPANY_DIR.parent)
        if minutes_path.is_relative_to(config.COMPANY_DIR.parent)
        else minutes_path
    )
    await post("Steve", f"📝 議事録保存: `{rel_path}`")

    # 親チャンネルに閉会通知
    if progress_fn:
        await progress_fn(
            f"✅ Council 終了\n"
            f"議事録: `{rel_path}`\n"
            f"承認するなら Thread 内で「OK」と返答してください"
        )

    return minutes_path
