"""スタンダードユーザーへの朝の運勢プッシュ通知"""

import logging
import os
from datetime import date

import anthropic
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

from database.crud import AsyncSessionLocal, get_standard_users

logger = logging.getLogger(__name__)


async def _generate_daily_fortune() -> str:
    client = anthropic.Anthropic()
    today = date.today().strftime("%Y年%m月%d日")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        system=(
            "あなたはプロの占い師です。毎朝ユーザーに送る運勢メッセージを作成します。\n"
            "150〜200文字で、前向きで具体的なアドバイスを1つ含めてください。\n"
            "絵文字を使って明るく、一日の始まりを応援する内容にしてください。"
        ),
        messages=[
            {"role": "user", "content": f"今日（{today}）の朝の運勢メッセージを作成してください。"}
        ],
    )
    return response.content[0].text


async def send_morning_fortune_to_all() -> None:
    """全スタンダードユーザーに朝の運勢プッシュを送信する"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])

    async with AsyncSessionLocal() as session:
        users = await get_standard_users(session)

    if not users:
        logger.info("スタンダードユーザーなし。プッシュをスキップ。")
        return

    fortune_text = await _generate_daily_fortune()
    message_text = f"🌅 おはようございます！今日の運勢\n\n{fortune_text}"

    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        for user in users:
            try:
                line_api.push_message(
                    PushMessageRequest(
                        to=user.line_user_id,
                        messages=[TextMessage(text=message_text)],
                    )
                )
            except Exception as e:
                logger.warning(f"Push通知失敗 {user.line_user_id}: {e}")

    logger.info(f"朝の運勢プッシュ完了: {len(users)}件")
