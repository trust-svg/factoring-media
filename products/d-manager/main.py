"""D-Manager — Discord AI Organization Bot."""

import logging
import asyncio

import discord
from discord.ext import commands

import config
from departments import get_department_for_channel
from secretary_engine import process_message
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Discord Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Channel ID cache
channel_cache: dict[str, discord.TextChannel] = {}

# Channels to auto-create
CHANNELS = [
    ("general", "アイ（秘書）— 日常会話・ブリーフィング"),
    ("operations", "リク — eBay運営・仕入れ・出品"),
    ("product", "レン — ZINQ/Sion/プロダクト開発"),
    ("marketing", "ユウ — マーケ・SNS・広告"),
    ("finance", "ケイ — 経理・経費・売上"),
    ("research", "アキラ — 市場調査・競合分析"),
    ("strategy", "ナオ — 経営企画・KPI"),
    ("decisions", "決裁案件の通知"),
    ("alerts", "システム・セキュリティアラート"),
    ("daily-digest", "AIニュース自動配信"),
    ("backup-log", "バックアップ完了通知"),
]


@bot.event
async def on_ready():
    logger.info(f"D-Manager logged in as {bot.user}")

    # Auto-create channels if missing
    for guild in bot.guilds:
        existing = {ch.name for ch in guild.text_channels}
        for ch_name, ch_topic in CHANNELS:
            if ch_name not in existing:
                channel = await guild.create_text_channel(ch_name, topic=ch_topic)
                logger.info(f"Created channel: #{ch_name}")
            else:
                channel = discord.utils.get(guild.text_channels, name=ch_name)

            if channel:
                channel_cache[ch_name] = channel

    # Setup scheduler
    setup_scheduler(send_to_channel)
    logger.info("D-Manager ready!")


@bot.event
async def on_message(message: discord.Message):
    # Ignore bot's own messages
    if message.author == bot.user:
        return

    # Ignore DMs
    if not message.guild:
        return

    # Ignore non-text channels and read-only channels
    channel_name = message.channel.name
    if channel_name in ("alerts", "backup-log", "daily-digest"):
        return

    # Determine department from channel
    department = get_department_for_channel(channel_name)

    # Show typing indicator
    async with message.channel.typing():
        # Process in thread to not block
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            process_message,
            message.content,
            department,
            str(message.channel.id),
        )

    # Discord message limit is 2000 chars
    chunks = [response[i:i + 1900] for i in range(0, len(response), 1900)]
    for chunk in chunks:
        await message.channel.send(chunk)


async def send_to_channel(channel_name: str, text: str):
    """Send a message to a specific channel."""
    channel = channel_cache.get(channel_name)
    if not channel:
        # Try to find it
        for guild in bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel:
                channel_cache[channel_name] = channel
                break

    if channel:
        chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
        for chunk in chunks:
            await channel.send(chunk)
    else:
        logger.error(f"Channel not found: {channel_name}")


def main():
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
