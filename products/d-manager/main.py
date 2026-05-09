"""D-Manager — Discord AI Organization Bot."""

from __future__ import annotations

import logging
import asyncio
from pathlib import Path

import discord
import httpx

import config
from departments import get_department_for_channel
from ai_engine import process_message
from scheduler import setup_scheduler
from tools.todo import complete_todo, drop_todo, defer_todo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Discord Client setup (not commands.Bot to avoid default message handling)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Client(intents=intents)

# Intercept ALL Discord HTTP API message sends to find the ghost sender
import discord.http

_original_request = discord.http.HTTPClient.request


async def _traced_request(self, route, **kwargs):
    if "messages" in str(route.url) and route.method == "POST":
        import traceback

        payload = kwargs.get("json") or kwargs.get("data")
        content = str(payload)[:100] if payload else "none"
        stack = "".join(traceback.format_stack()[-5:-1])
        logger.warning(f"HTTP SEND INTERCEPTED: {content}\nSTACK:\n{stack}")
    return await _original_request(self, route, **kwargs)


discord.http.HTTPClient.request = _traced_request

# Channel ID cache
channel_cache = {}

# Webhook cache: channel_name -> discord.Webhook
webhook_cache = {}

# Video Analyzer: serialize concurrent analyses (one job at a time on the VPS)
_VIDEO_ANALYZER_SEMA = asyncio.Semaphore(1)
VIDEO_ANALYZER_CHANNEL = "動画分析-video-research"
import re

_VIDEO_URL_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be|tiktok\.com|vt\.tiktok\.com|"
    r"instagram\.com)/[^\s<>\"']+",
    re.IGNORECASE,
)

# Tighter pattern: matches only single-video page URLs. Account / channel URLs
# (youtube.com/@x, tiktok.com/@x, instagram.com/<user>) intentionally don't
# match — those are routed to sns-research instead.
_VIDEO_PAGE_RE = re.compile(
    r"(?:"
    r"youtube\.com/(?:watch\?|shorts/|embed/|live/)"
    r"|youtu\.be/[\w-]+"
    r"|tiktok\.com/[^/\s]+/video/[\w-]+"
    r"|vt\.tiktok\.com/[\w-]+"
    r"|tiktok\.com/[tv]/[\w-]+"
    r"|instagram\.com/(?:p|reel|reels|tv)/[\w-]+"
    r")",
    re.IGNORECASE,
)


def _extract_video_urls(text: str) -> list[str]:
    return _VIDEO_URL_RE.findall(text or "")


def _classify_video_research_input(text: str) -> tuple[str, str | None]:
    """動画分析-video-research チャンネル入力の振り分け。

    Returns:
        ("video", url)        — 動画ページ URL → 既存の構造化分析を実行
        ("sns_research", txt) — それ以外（アカウントURL・キーワード等）→ sns-research フロー
        ("empty", None)       — 空メッセージ
    """
    text = (text or "").strip()
    if not text:
        return ("empty", None)
    for url in _VIDEO_URL_RE.findall(text):
        if _VIDEO_PAGE_RE.search(url):
            return ("video", url)
    return ("sns_research", text)


# Channel -> AI character mapping
CHANNELS = [
    ("ceo-steve-general", "👨‍💼 Steve（CEO） — 日常会話・ブリーフィング・何でも相談"),
    ("運営-jack-operations", "👨‍💻 Jack — eBay運営・仕入れ・出品・在庫管理"),
    ("開発-larry-product", "🛠️ Larry — ZINQ/Sion/プロダクト開発"),
    ("マーケティング-mark-marketing", "📣 Mark — マーケ・SNS・広告・コンテンツ"),
    ("経理-warren-finance", "💰 Warren — 経理・経費・売上・請求"),
    ("調査-elon-research", "🔍 Elon — 市場調査・競合分析・トレンド"),
    ("戦略-reid-strategy", "📊 Reid — 経営企画・KPI・事業戦略"),
    (
        "動画分析-video-research",
        "🎬 Elon — YouTube/TikTok/Instagram の URL を貼ると構造化分析",
    ),
    ("決裁-decisions", "📋 決裁案件の通知"),
    ("アラート-alerts", "🚨 システム・セキュリティアラート"),
    ("日報-daily-digest", "📰 AIニュース自動配信"),
    ("記録-backup-log", "💾 バックアップ完了通知"),
]

# Channel -> character name + avatar file
CHANNEL_CHARACTERS = {
    "ceo-steve-general": ("Steve", "steve.png"),
    "運営-jack-operations": ("Jack", "riku.png"),
    "開発-larry-product": ("Larry", "ren.png"),
    "マーケティング-mark-marketing": ("Mark", "yuu.png"),
    "経理-warren-finance": ("Warren", "kei.png"),
    "調査-elon-research": ("Elon", "akira.png"),
    "戦略-reid-strategy": ("Reid", "nao.png"),
    "動画分析-video-research": ("Elon", "akira.png"),
    "決裁-decisions": ("Steve", "steve.png"),
    "アラート-alerts": ("Steve", "steve.png"),
    "日報-daily-digest": ("Elon", "akira.png"),
    "記録-backup-log": ("Steve", "steve.png"),
}

AVATAR_DIR = Path(__file__).parent / "avatars"


async def get_or_create_webhook(channel: discord.TextChannel) -> discord.Webhook:
    """Get existing D-Manager webhook or create one for the channel."""
    channel_name = channel.name
    if channel_name in webhook_cache:
        return webhook_cache[channel_name]

    # Check existing webhooks
    webhooks = await channel.webhooks()
    for wh in webhooks:
        if wh.name == "D-Manager":
            webhook_cache[channel_name] = wh
            return wh

    # Create new webhook
    wh = await channel.create_webhook(name="D-Manager")
    webhook_cache[channel_name] = wh
    logger.info(f"Created webhook for #{channel_name}")
    return wh


async def send_as_character(
    channel: discord.TextChannel, text: str, channel_name: str = None
):
    """Send message via webhook with character name and avatar."""
    ch_name = channel_name or channel.name
    char_name, avatar_file = CHANNEL_CHARACTERS.get(ch_name, ("Steve", "steve.png"))

    webhook = await get_or_create_webhook(channel)

    # Read avatar image
    avatar_path = AVATAR_DIR / avatar_file
    avatar_bytes = None
    if avatar_path.exists():
        avatar_bytes = avatar_path.read_bytes()

    chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
    for chunk in chunks:
        await webhook.send(
            content=chunk,
            username=char_name,
            avatar_url=None,  # Use file upload below
        )


async def send_as_character_with_avatar(
    channel: discord.TextChannel, text: str, channel_name: str = None
):
    """Send message via webhook with character name and avatar."""
    ch_name = channel_name or channel.name
    char_name, avatar_file = CHANNEL_CHARACTERS.get(ch_name, ("Steve", "steve.png"))

    # Look up webhook: try logical name → actual Discord name → channel ID
    webhook = (
        webhook_cache.get(ch_name)
        or webhook_cache.get(channel.name)
        or webhook_cache.get(channel.id)
    )
    if not webhook:
        logger.warning(
            f"No webhook cached for #{ch_name} (actual: #{channel.name}), sending as bot"
        )
        chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
        for chunk in chunks:
            await channel.send(chunk)
        return

    chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
    for chunk in chunks:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            await session.post(
                webhook.url,
                json={"content": chunk, "username": char_name},
            )


# Old channel names -> new channel names (for migration)
OLD_TO_NEW = {
    # Legacy -> Japanese names
    "general": "ceo-steve-general",
    "総合-general": "ceo-steve-general",
    "総合-アイ": "ceo-steve-general",
    "総合-アイ-general": "ceo-steve-general",
    "operations": "運営-jack-operations",
    "運営-operations": "運営-jack-operations",
    "運営-リク": "運営-jack-operations",
    "product": "開発-larry-product",
    "開発-product": "開発-larry-product",
    "開発-レン": "開発-larry-product",
    "marketing": "マーケティング-mark-marketing",
    "広報-marketing": "マーケティング-mark-marketing",
    "広報-ユウ": "マーケティング-mark-marketing",
    "広報-ユウ-marketing": "マーケティング-mark-marketing",
    "finance": "経理-warren-finance",
    "経理-finance": "経理-warren-finance",
    "経理-ケイ": "経理-warren-finance",
    "research": "調査-elon-research",
    "調査-research": "調査-elon-research",
    "調査-アキラ": "調査-elon-research",
    "strategy": "戦略-reid-strategy",
    "戦略-strategy": "戦略-reid-strategy",
    "戦略-ナオ": "戦略-reid-strategy",
    "decisions": "決裁-decisions",
    "決裁-decisions": "決裁-decisions",
    "決裁-通知": "決裁-decisions",
    "alerts": "アラート-alerts",
    "警報-alerts": "アラート-alerts",
    "警報-通知": "アラート-alerts",
    "daily-digest": "日報-daily-digest",
    "日報-daily-digest": "日報-daily-digest",
    "日報-配信": "日報-daily-digest",
    "backup-log": "記録-backup-log",
    "記録-backup-log": "記録-backup-log",
    "記録-ログ": "記録-backup-log",
    # Japanese names -> English names (current migration)
    "秘書-アイ-general": "ceo-steve-general",
    "秘書-steve-general": "ceo-steve-general",
    # Discord truncates long channel names
    "ceo-steve": "ceo-steve-general",
    "運営-リク-operations": "運営-jack-operations",
    "開発-レン-product": "開発-larry-product",
    "マーケティング-ユウ-marketing": "マーケティング-mark-marketing",
    "経理-ケイ-finance": "経理-warren-finance",
    "調査-アキラ-research": "調査-elon-research",
    "戦略-ナオ-strategy": "戦略-reid-strategy",
}


@bot.event
async def on_ready():
    logger.info(f"D-Manager logged in as {bot.user}")

    for guild in bot.guilds:
        existing = {ch.name: ch for ch in guild.text_channels}

        for ch_name, ch_topic in CHANNELS:
            channel = existing.get(ch_name)

            if not channel:
                # Check if old-named channel exists and rename it
                old_names = [k for k, v in OLD_TO_NEW.items() if v == ch_name]
                for old_name in old_names:
                    old_ch = existing.get(old_name)
                    if old_ch:
                        try:
                            await old_ch.edit(name=ch_name, topic=ch_topic)
                            channel = old_ch
                            logger.info(f"Renamed #{old_name} -> #{ch_name}")
                        except discord.Forbidden:
                            logger.warning(
                                f"No permission to rename #{old_name} -> #{ch_name}. Rename manually in Discord."
                            )
                            channel = old_ch  # Use as-is
                        break

            if not channel:
                try:
                    channel = await guild.create_text_channel(ch_name, topic=ch_topic)
                    logger.info(f"Created channel: #{ch_name}")
                except discord.Forbidden:
                    logger.warning(f"No permission to create #{ch_name}. Skipping.")
                    continue
            elif channel.topic != ch_topic:
                try:
                    await channel.edit(topic=ch_topic)
                except discord.Forbidden:
                    logger.warning(f"No permission to update topic for #{ch_name}")

            channel_cache[ch_name] = channel

    # Ensure webhooks exist — use bot-specific prefix to avoid token conflicts
    bot_prefix = bot.user.name.replace(" ", "")[:10] if bot.user else "DM"
    for ch_name, channel in channel_cache.items():
        try:
            char_name = CHANNEL_CHARACTERS.get(ch_name, ("Steve", "steve.png"))[0]
            webhook_name = f"{bot_prefix}-{char_name}"
            webhooks = await channel.webhooks()
            wh = None
            for w in webhooks:
                if w.name == webhook_name and w.token:
                    wh = w
                    break
            if not wh:
                avatar_file = CHANNEL_CHARACTERS.get(ch_name, ("Steve", "steve.png"))[1]
                avatar_path = AVATAR_DIR / avatar_file
                avatar_bytes = (
                    avatar_path.read_bytes() if avatar_path.exists() else None
                )
                wh = await channel.create_webhook(
                    name=webhook_name, avatar=avatar_bytes
                )
                logger.info(f"Created webhook {webhook_name} for #{ch_name}")
            # Delete stale webhooks (old character names, old prefixes)
            for old_wh in webhooks:
                if (
                    old_wh.id != wh.id
                    and old_wh.token
                    and (
                        old_wh.name.startswith(bot_prefix + "-")
                        or old_wh.name.startswith("TrustLinkD-")
                        or old_wh.name == "D-Manager"
                    )
                ):
                    try:
                        await old_wh.delete()
                        logger.info(
                            f"Deleted stale webhook '{old_wh.name}' from #{ch_name}"
                        )
                    except Exception as del_err:
                        logger.warning(
                            f"Could not delete stale webhook '{old_wh.name}': {del_err}"
                        )
            webhook_cache[ch_name] = wh
            # Also index by actual Discord channel name and ID (handles rename mismatches)
            webhook_cache[channel.name] = wh
            webhook_cache[channel.id] = wh
            logger.info(
                f"Webhook [{ch_name}] actual=#{channel.name} {wh.name}: {wh.url}"
            )
        except Exception as e:
            logger.warning(f"Webhook setup failed for #{ch_name}: {e}")

    # Setup scheduler
    setup_scheduler(send_to_channel, task_view_fn=TaskBoardView)
    logger.info("D-Manager ready!")


@bot.event
async def on_message(message: discord.Message):
    # Debug logging
    logger.info(
        f"MSG: author={message.author} bot={message.author.bot} webhook_id={message.webhook_id} content={message.content[:50]}"
    )

    # Ignore all bot/webhook messages
    if message.author.bot or message.webhook_id:
        logger.info(f"IGNORED: bot={message.author.bot} webhook={message.webhook_id}")
        return

    # Ignore DMs
    if not message.guild:
        return

    # Ignore non-text channels and read-only channels
    channel_name = message.channel.name
    if channel_name in ("アラート-alerts", "記録-backup-log", "日報-daily-digest"):
        return

    # Determine department from channel
    department = get_department_for_channel(channel_name)

    logger.info(f"PROCESSING: {message.content[:50]} in #{channel_name}")

    # Video analyzer channel: 2モード対応 (動画分析 / SNSバズリサーチ)
    if channel_name == VIDEO_ANALYZER_CHANNEL:
        kind, payload = _classify_video_research_input(message.content)
        if kind == "video":
            asyncio.create_task(_run_video_analysis(message.channel, payload))
            return
        if kind == "sns_research":
            from flows import run_flow

            asyncio.create_task(
                run_flow(
                    "sns-research",
                    {"genre": payload},
                    send_to_channel,
                    channel_override=channel_name,
                )
            )
            preview = payload[:80] + ("…" if len(payload) > 80 else "")
            await send_as_character_with_avatar(
                message.channel,
                f"🔍 SNSバズリサーチを開始します: 「{preview}」\n"
                "Elon が sns-research スキルで実行中…",
                channel_name,
            )
            return
        await send_as_character_with_avatar(
            message.channel,
            "🎬 このチャンネルは2モード対応です。\n"
            "- **動画分析**: YouTube / TikTok / Instagram の動画ページ URL を貼る → 構造化分析\n"
            "- **SNSバズリサーチ**: ジャンル名・キーワード・アカウントURL を貼る → Elon が sns-research スキルで実行",
            channel_name,
        )
        return

    # Quick command: task board with buttons
    content_lower = message.content.lower()
    task_keywords = ["タスクボード", "タスク一覧", "タスク見せて"]
    if content_lower in task_keywords or any(
        content_lower == kw for kw in task_keywords
    ):
        from scheduler import _parse_active_tasks, _build_task_board

        tasks = _parse_active_tasks()
        board = _build_task_board()
        view = TaskBoardView(tasks) if tasks else None
        await send_to_channel(channel_name, board, view)
        logger.info("SEND COMPLETE (task board with buttons)")
        return

    # Quick command: !rule add <category> <text>  /  !rule list
    raw = message.content.strip()
    if raw.startswith("!rule"):
        from tools.rules import add_rule, list_categories, read_rules

        parts = raw.split(maxsplit=2)
        if len(parts) >= 2 and parts[1] == "list":
            cats = list_categories()
            msg = "📚 **rules.md カテゴリ一覧**\n" + "\n".join(f"- {c}" for c in cats)
            await send_as_character_with_avatar(message.channel, msg, channel_name)
            return
        if len(parts) >= 2 and parts[1] == "show":
            content = read_rules()
            await send_as_character_with_avatar(
                message.channel, f"```\n{content[:1800]}\n```", channel_name
            )
            return
        if len(parts) >= 3 and parts[1] == "add":
            # parts[2] format: "<category> <rule_text>"
            sub = parts[2].split(maxsplit=1)
            if len(sub) < 2:
                await send_as_character_with_avatar(
                    message.channel,
                    "⚠️ 形式: `!rule add <カテゴリ> <ルール内容>`\n例: `!rule add メール 山田さんからのメールは最優先`",
                    channel_name,
                )
                return
            category, rule_text = sub[0], sub[1]
            result = add_rule(category, rule_text)
            await send_as_character_with_avatar(message.channel, result, channel_name)
            return
        # Help
        await send_as_character_with_avatar(
            message.channel,
            "📘 **!rule コマンド**\n"
            "- `!rule add <カテゴリ> <ルール>` — ルール追記\n"
            "- `!rule list` — カテゴリ一覧\n"
            "- `!rule show` — 現在のルール全文",
            channel_name,
        )
        return

    # Quick command: !session reset / !session info
    if raw.startswith("!session"):
        from ai_engine import reset_cli_session, get_cli_session_info

        parts = raw.split(maxsplit=1)
        sub = parts[1].strip().lower() if len(parts) >= 2 else ""
        channel_id = str(message.channel.id)

        if sub == "reset":
            ok = reset_cli_session(channel_id)
            msg = (
                "🔄 このチャンネルのCLIセッションをリセットしました。次回から新しい会話として開始します。"
                if ok
                else "ℹ️ このチャンネルにはアクティブなセッションがありませんでした。"
            )
            await send_as_character_with_avatar(message.channel, msg, channel_name)
            return

        if sub == "info":
            info = get_cli_session_info(channel_id)
            if not info:
                msg = "ℹ️ このチャンネルにはアクティブなセッションがありません。次のメッセージで新規作成されます。"
            else:
                msg = (
                    "🧠 **CLIセッション情報**\n"
                    f"- session_id: {info['session_id']}\n"
                    f"- 経過時間: {info['age_minutes']} 分\n"
                    f"- TTL残り: {info['expires_in_minutes']} 分（最大 12 時間）"
                )
            await send_as_character_with_avatar(message.channel, msg, channel_name)
            return

        # Help
        await send_as_character_with_avatar(
            message.channel,
            "🧠 **!session コマンド**\n"
            "- `!session info` — このチャンネルのセッション状態\n"
            "- `!session reset` — セッションをリセット（新しい会話として開始）",
            channel_name,
        )
        return

    # Quick command: !run <flow> [arg=value] [arg=value] …
    if raw.startswith("!run"):
        from flows import FLOWS, list_flows, run_flow

        parts = raw.split(maxsplit=1)
        rest = parts[1].strip() if len(parts) >= 2 else ""

        if not rest or rest in ("list", "ls", "help"):
            lines = ["🚀 **利用可能フロー**"]
            for name, desc in list_flows():
                args = ", ".join(FLOWS[name]["args"])
                lines.append(f"- `!run {name} {args}=…` — {desc}")
            lines.append(
                '\n例: `!run article-factory site=FACCEL topic="ファクタリング 即日"`'
            )
            await send_as_character_with_avatar(
                message.channel, "\n".join(lines), channel_name
            )
            return

        # Parse: <flow_name> key=value key="quoted value" …
        import shlex

        tokens = shlex.split(rest)
        flow_name = tokens[0]
        flow_args: dict[str, str] = {}
        for tok in tokens[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                flow_args[k.strip()] = v.strip()

        # Run in background so the Discord handler can return promptly
        asyncio.create_task(run_flow(flow_name, flow_args, send_to_channel))
        await send_as_character_with_avatar(
            message.channel,
            f"🟢 フロー `{flow_name}` をバックグラウンドで起動しました。引数: {flow_args}",
            channel_name,
        )
        return

    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None,
            process_message,
            message.content,
            department,
            str(message.channel.id),
        )
    except Exception as e:
        logger.error(f"process_message failed: {e}")
        response = "⚠️ APIエラーが発生しました。少し後にもう一度話しかけてください。"

    # --- Phase 2: Dispatch handling ---
    from tools.dispatch import parse_dispatches, strip_dispatches
    from ai_engine import execute_task

    dispatches = parse_dispatches(response)
    if dispatches:
        # Send Steve's reply without the dispatch blocks
        visible = strip_dispatches(response)
        if visible:
            await send_as_character_with_avatar(message.channel, visible)

        # Spawn each dispatched task in the background
        for d in dispatches:
            asyncio.create_task(
                _run_dispatched_task(
                    d["agent"], d["task"], d["channel"], d["is_coding"]
                )
            )
        logger.info(
            f"Dispatched {len(dispatches)} task(s): {[d['agent'] for d in dispatches]}"
        )
    else:
        await send_as_character_with_avatar(message.channel, response)

    logger.info("SEND COMPLETE")


async def _run_dispatched_task(
    agent: str, task: str, channel_name: str, is_coding: bool
):
    """Background: execute a dispatched task and report result to channel."""
    loop = asyncio.get_event_loop()
    logger.info(f"Dispatched task starting: {agent} → {task[:60]}")

    # Notify the target channel that work has started
    target_ch = channel_cache.get(channel_name)
    if target_ch:
        await send_as_character_with_avatar(
            target_ch,
            f"📋 作業開始: {task[:100]}{'...' if len(task) > 100 else ''}",
            channel_name,
        )

    try:
        result = await loop.run_in_executor(None, execute_task, agent, task, is_coding)
    except Exception as e:
        result = f"⚠️ 実行エラー: {e}"

    logger.info(f"Dispatched task done: {agent}")

    # Report result to the agent's channel
    if target_ch:
        await send_as_character_with_avatar(target_ch, result, channel_name)
    else:
        # Fallback: report to CEO channel
        ceo_ch = channel_cache.get("ceo-steve-general")
        if ceo_ch:
            await send_as_character_with_avatar(
                ceo_ch, f"✅ **{agent}** 作業完了:\n{result}", "ceo-steve-general"
            )


async def _run_video_analysis(channel: discord.TextChannel, url: str) -> None:
    """Background task: call video-analyzer /analyze and post the formatted result.

    Serialized via _VIDEO_ANALYZER_SEMA so multiple URLs queue rather than
    racing the upstream service (which holds the model API key budget).
    """
    from tools import video_analyzer, video_format

    queued_msg = None
    if _VIDEO_ANALYZER_SEMA.locked():
        queued_msg = await channel.send(
            f"⏳ 既に分析中の動画があります。順番待ちで処理します: {url[:80]}"
        )

    async with _VIDEO_ANALYZER_SEMA:
        notice = await channel.send(f"🎬 分析開始: {url[:120]}")
        try:
            data = await video_analyzer.analyze(url, force=False)
        except httpx.ReadTimeout:
            logger.exception("video analyze timed out")
            await notice.edit(
                content=(
                    "⚠️ 分析タイムアウト（10 分）— 動画が長すぎる可能性があります。\n"
                    "目安: 13 分以内なら通る想定。それ以上は分割をご検討ください。"
                )
            )
            return
        except Exception as e:
            logger.exception("video analyze failed")
            msg = str(e) or type(e).__name__
            await notice.edit(content=f"⚠️ 分析失敗: {msg}")
            return

        if data.get("error"):
            await notice.edit(content=f"⚠️ 分析エラー: {data['error']}")
            return

        analysis = data.get("analysis") or {}
        row_id = data.get("row_id")
        cached = data.get("cached")
        elapsed = data.get("elapsed_sec") or 0

        try:
            await notice.edit(
                content=(
                    f"✅ 分析完了 ({'cache' if cached else 'fresh'}, "
                    f"{elapsed:.1f}s, row_id={row_id})"
                )
            )
        except Exception:
            pass

        # Message 1: summary
        await channel.send(video_format.format_summary(analysis, row_id))
        # Message 2: structure + triggers + CTA
        await channel.send(video_format.format_structure_and_triggers(analysis))
        # Message 3: keyframes (with attachments) + view button
        if row_id:
            caption, files = await video_format.fetch_keyframe_files(row_id, n=3)
            view = video_format.VideoAnalysisView(row_id)
            if files:
                await channel.send(content=caption, files=files, view=view)
            else:
                await channel.send(content=caption, view=view)

        if queued_msg:
            try:
                await queued_msg.delete()
            except Exception:
                pass


class TaskActionButton(discord.ui.Button):
    """Button for a task action (complete/defer/drop)."""

    def __init__(self, task_name: str, action: str, row: int = 0):
        short_name = task_name[:20] if len(task_name) > 20 else task_name
        styles = {
            "complete": (discord.ButtonStyle.success, f"✅ {short_name}"),
            "defer": (discord.ButtonStyle.primary, f"⏰ {short_name}"),
            "drop": (discord.ButtonStyle.danger, f"🗑 {short_name}"),
        }
        style, label = styles[action]
        super().__init__(
            style=style,
            label=label,
            custom_id=f"{action}:{task_name[:80]}",
            row=row,
        )
        self.task_name = task_name
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        actions = {
            "complete": (complete_todo, "✅"),
            "defer": (defer_todo, "⏰"),
            "drop": (drop_todo, "🗑"),
        }
        func, emoji = actions[self.action]
        result = func(self.task_name)
        await interaction.response.send_message(f"{emoji} {result}", ephemeral=False)
        # Disable all buttons for this task
        for item in self.view.children:
            if isinstance(item, TaskActionButton) and item.task_name == self.task_name:
                item.disabled = True
                item.style = discord.ButtonStyle.secondary
        await interaction.message.edit(view=self.view)


class TaskBoardView(discord.ui.View):
    """Interactive task board — one row per task with task name on each button."""

    def __init__(self, tasks: list):
        super().__init__(timeout=None)
        # 3 buttons per task, 5 rows max (Discord limit)
        for i, task in enumerate(tasks[:5]):
            self.add_item(TaskActionButton(task["name"], "complete", row=i))
            self.add_item(TaskActionButton(task["name"], "defer", row=i))
            self.add_item(TaskActionButton(task["name"], "drop", row=i))


async def send_to_channel(channel_name: str, text: str, view: discord.ui.View = None):
    """Send a message to a specific channel. Supports optional View (buttons)."""
    channel = channel_cache.get(channel_name)
    if not channel:
        for guild in bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel:
                channel_cache[channel_name] = channel
                break

    if channel:
        if view:
            # Send with buttons via bot (not webhook — webhooks don't support views)
            chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    await channel.send(content=chunk, view=view)
                else:
                    await channel.send(content=chunk)
        else:
            await send_as_character_with_avatar(channel, text, channel_name)
    else:
        logger.error(f"Channel not found: {channel_name}")


def main():
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
