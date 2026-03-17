"""Set up Telegram Bot commands menu (replaces LINE Rich Menu)."""

import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot, BotCommand

load_dotenv()

COMMANDS = [
    BotCommand("briefing", "📋 朝のブリーフィング"),
    BotCommand("todo", "✅ 今日のTODO確認"),
    BotCommand("schedule", "📅 今日の予定確認"),
    BotCommand("expense", "💰 今月の経費サマリー"),
    BotCommand("habit", "🏋️ 習慣チェック"),
    BotCommand("help", "❓ 機能一覧"),
]


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env")
        return

    bot = Bot(token=token)
    await bot.set_my_commands(COMMANDS)
    me = await bot.get_me()
    print(f"Commands set for @{me.username}")
    print("Menu commands:")
    for cmd in COMMANDS:
        print(f"  /{cmd.command} — {cmd.description}")


if __name__ == "__main__":
    asyncio.run(main())
