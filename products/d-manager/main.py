"""D-Manager — Discord AI Organization Bot."""

import logging
import asyncio
from pathlib import Path

import discord

import config
from departments import get_department_for_channel
from ai_engine import process_message
from scheduler import setup_scheduler

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
    if 'messages' in str(route.url) and route.method == 'POST':
        import traceback
        payload = kwargs.get('json') or kwargs.get('data')
        content = str(payload)[:100] if payload else 'none'
        stack = ''.join(traceback.format_stack()[-5:-1])
        logger.warning(f"HTTP SEND INTERCEPTED: {content}\nSTACK:\n{stack}")
    return await _original_request(self, route, **kwargs)

discord.http.HTTPClient.request = _traced_request

# Channel ID cache
channel_cache = {}

# Webhook cache: channel_name -> discord.Webhook
webhook_cache = {}

# Channel -> AI character mapping
CHANNELS = [
    ("秘書-アイ-general", "👩‍💼 アイ（秘書） — 日常会話・ブリーフィング・何でも相談"),
    ("運営-リク-operations", "👨‍💻 リク — eBay運営・仕入れ・出品・在庫管理"),
    ("開発-レン-product", "🛠️ レン — ZINQ/Sion/プロダクト開発"),
    ("マーケティング-ユウ-marketing", "📣 ユウ — マーケ・SNS・広告・コンテンツ"),
    ("経理-ケイ-finance", "💰 ケイ — 経理・経費・売上・請求"),
    ("調査-アキラ-research", "🔍 アキラ — 市場調査・競合分析・トレンド"),
    ("戦略-ナオ-strategy", "📊 ナオ — 経営企画・KPI・事業戦略"),
    ("決裁-decisions", "📋 決裁案件の通知"),
    ("アラート-alerts", "🚨 システム・セキュリティアラート"),
    ("日報-daily-digest", "📰 AIニュース自動配信"),
    ("記録-backup-log", "💾 バックアップ完了通知"),
]

# Channel -> character name + avatar file
CHANNEL_CHARACTERS = {
    "秘書-アイ-general": ("アイ", "ai.png"),
    "運営-リク-operations": ("リク", "riku.png"),
    "開発-レン-product": ("レン", "ren.png"),
    "マーケティング-ユウ-marketing": ("ユウ", "yuu.png"),
    "経理-ケイ-finance": ("ケイ", "kei.png"),
    "調査-アキラ-research": ("アキラ", "akira.png"),
    "戦略-ナオ-strategy": ("ナオ", "nao.png"),
    "決裁-decisions": ("アイ", "ai.png"),
    "アラート-alerts": ("アイ", "ai.png"),
    "日報-daily-digest": ("アキラ", "akira.png"),
    "記録-backup-log": ("アイ", "ai.png"),
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


async def send_as_character(channel: discord.TextChannel, text: str, channel_name: str = None):
    """Send message via webhook with character name and avatar."""
    ch_name = channel_name or channel.name
    char_name, avatar_file = CHANNEL_CHARACTERS.get(ch_name, ("アイ", "ai.png"))

    webhook = await get_or_create_webhook(channel)

    # Read avatar image
    avatar_path = AVATAR_DIR / avatar_file
    avatar_bytes = None
    if avatar_path.exists():
        avatar_bytes = avatar_path.read_bytes()

    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
    for chunk in chunks:
        await webhook.send(
            content=chunk,
            username=char_name,
            avatar_url=None,  # Use file upload below
        )


async def send_as_character_with_avatar(channel: discord.TextChannel, text: str, channel_name: str = None):
    """Send message via webhook with character name and avatar."""
    ch_name = channel_name or channel.name
    char_name, avatar_file = CHANNEL_CHARACTERS.get(ch_name, ("アイ", "ai.png"))

    # Get or create webhook, set avatar on first use per channel
    cache_key = ch_name
    if cache_key not in webhook_cache:
        webhooks = await channel.webhooks()
        webhook = None
        for wh in webhooks:
            if wh.name == f"DM-{char_name}":
                webhook = wh
                break

        if not webhook:
            avatar_path = AVATAR_DIR / avatar_file
            avatar_bytes = avatar_path.read_bytes() if avatar_path.exists() else None
            webhook = await channel.create_webhook(
                name=f"DM-{char_name}",
                avatar=avatar_bytes,
            )
            logger.info(f"Created webhook DM-{char_name} for #{ch_name}")

        webhook_cache[cache_key] = webhook

    webhook = webhook_cache[cache_key]
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
    for chunk in chunks:
        # Use HTTP request directly to avoid discord.py double-send
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.post(
                webhook.url,
                json={"content": chunk, "username": char_name},
            )


# Old channel names -> new channel names (for migration)
OLD_TO_NEW = {
    "general": "秘書-アイ-general",
    "総合-general": "秘書-アイ-general",
    "総合-アイ": "秘書-アイ-general",
    "総合-アイ-general": "秘書-アイ-general",
    "operations": "運営-リク-operations",
    "運営-operations": "運営-リク-operations",
    "運営-リク": "運営-リク-operations",
    "product": "開発-レン-product",
    "開発-product": "開発-レン-product",
    "開発-レン": "開発-レン-product",
    "marketing": "マーケティング-ユウ-marketing",
    "広報-marketing": "マーケティング-ユウ-marketing",
    "広報-ユウ": "マーケティング-ユウ-marketing",
    "広報-ユウ-marketing": "マーケティング-ユウ-marketing",
    "finance": "経理-ケイ-finance",
    "経理-finance": "経理-ケイ-finance",
    "経理-ケイ": "経理-ケイ-finance",
    "research": "調査-アキラ-research",
    "調査-research": "調査-アキラ-research",
    "調査-アキラ": "調査-アキラ-research",
    "strategy": "戦略-ナオ-strategy",
    "戦略-strategy": "戦略-ナオ-strategy",
    "戦略-ナオ": "戦略-ナオ-strategy",
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
                        await old_ch.edit(name=ch_name, topic=ch_topic)
                        channel = old_ch
                        logger.info(f"Renamed #{old_name} -> #{ch_name}")
                        break

            if not channel:
                channel = await guild.create_text_channel(ch_name, topic=ch_topic)
                logger.info(f"Created channel: #{ch_name}")
            elif channel.topic != ch_topic:
                await channel.edit(topic=ch_topic)

            channel_cache[ch_name] = channel

    # Ensure webhooks exist for notification channels and log URLs
    for ch_name, channel in channel_cache.items():
        try:
            char_name = CHANNEL_CHARACTERS.get(ch_name, ("アイ", "ai.png"))[0]
            webhook_name = f"DM-{char_name}"
            webhooks = await channel.webhooks()
            wh = None
            for w in webhooks:
                if w.name == webhook_name:
                    wh = w
                    break
            if not wh:
                avatar_file = CHANNEL_CHARACTERS.get(ch_name, ("アイ", "ai.png"))[1]
                avatar_path = AVATAR_DIR / avatar_file
                avatar_bytes = avatar_path.read_bytes() if avatar_path.exists() else None
                wh = await channel.create_webhook(name=webhook_name, avatar=avatar_bytes)
                logger.info(f"Created webhook {webhook_name} for #{ch_name}")
            webhook_cache[ch_name] = wh
            logger.info(f"Webhook [{ch_name}] {wh.name}: {wh.url}")
        except Exception as e:
            logger.warning(f"Webhook setup failed for #{ch_name}: {e}")

    # Setup scheduler
    setup_scheduler(send_to_channel)
    logger.info("D-Manager ready!")


@bot.event
async def on_message(message: discord.Message):
    # Debug logging
    logger.info(f"MSG: author={message.author} bot={message.author.bot} webhook_id={message.webhook_id} content={message.content[:50]}")

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

    logger.info(f"SENDING via webhook only: {response[:50]}")

    # Send via webhook with character avatar
    await send_as_character_with_avatar(message.channel, response)

    logger.info("SEND COMPLETE")


async def send_to_channel(channel_name: str, text: str):
    """Send a message to a specific channel via webhook."""
    channel = channel_cache.get(channel_name)
    if not channel:
        for guild in bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel:
                channel_cache[channel_name] = channel
                break

    if channel:
        await send_as_character_with_avatar(channel, text, channel_name)
    else:
        logger.error(f"Channel not found: {channel_name}")


def main():
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
