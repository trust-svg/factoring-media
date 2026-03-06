"""ナーチャリングシーケンス（友達追加後 Day1/3/7 のフォローアップ）"""
from __future__ import annotations

import logging
import os

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)

from database.crud import AsyncSessionLocal, get_users_for_nurturing

logger = logging.getLogger(__name__)

STORES_URL = "https://sion-salon.stores.jp"

NURTURE_MESSAGES: dict[int, str] = {
    1: (
        "🌟 祈音（しおん）です✨\n\n"
        "昨日はお悩みを教えていただき\n"
        "ありがとうございました。\n\n"
        "まだお悩みを送られていない方は、\n"
        "今のお気持ちを自由にお送りください🔮\n"
        "縁の声から視えるものをお伝えします💫"
    ),
    3: (
        "🔮 祈音です。\n\n"
        "簡易鑑定はいかがでしたか？\n\n"
        "本鑑定では恋愛の転機・仕事の変化・\n"
        "具体的なタイミングまで\n"
        "深く読み解いてお伝えします。\n\n"
        "「続きが気になる」と感じた方は\n"
        f"ぜひ本鑑定をお試しください🌙\n"
        f"▶ {STORES_URL}"
    ),
    7: (
        "💫 祈音です。\n"
        "1週間ありがとうございます。\n\n"
        "簡易鑑定では伝えきれない\n"
        "あなただけの深い読み解きを\n"
        "本鑑定でお届けしています。\n\n"
        f"▶ {STORES_URL}"
    ),
}


async def send_nurturing_messages() -> None:
    """Day1/3/7 に該当するユーザーへナーチャリングメッセージを送信する"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])

    async with AsyncSessionLocal() as session:
        with ApiClient(line_config) as api_client:
            line_api = MessagingApi(api_client)

            for days, message_text in NURTURE_MESSAGES.items():
                users = await get_users_for_nurturing(session, days)
                for user in users:
                    try:
                        line_api.push_message(
                            PushMessageRequest(
                                to=user.line_user_id,
                                messages=[TextMessage(text=message_text)],
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"ナーチャリング送信失敗 day{days} {user.line_user_id}: {e}"
                        )

                if users:
                    logger.info(f"ナーチャリング Day{days}: {len(users)}件送信")
