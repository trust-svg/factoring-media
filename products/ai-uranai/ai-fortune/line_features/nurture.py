"""ナーチャリングシーケンス（友達追加後 Day1/3/7 のフォローアップ）"""

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
        "🌟 友達追加ありがとうございます！\n\n"
        "AI占いサロン「Sion」へようこそ✨\n\n"
        "初回限定で無料鑑定をお試しいただけます🃏\n"
        "「タロット占いして」と送ってみてください！\n\n"
        "下のメニューから占いの種類を選べます💫"
    ),
    3: (
        "🔮 占いはお役に立てていますか？\n\n"
        "無料鑑定で気になる部分はありましたか？\n\n"
        "本鑑定では恋愛・仕事・人生の転機を\n"
        "より深く、詳しくお伝えします。\n\n"
        "「続きが知りたい」と思ったら\n"
        f"ぜひ本鑑定をお試しください🌙\n"
        f"▶ {STORES_URL}"
    ),
    7: (
        "💫 1週間、ありがとうございます！\n\n"
        "無料鑑定では伝えきれない\n"
        "あなただけの深い読み解きを\n"
        "本鑑定でお届けしています。\n\n"
        "今なら初回限定の特別価格も\n"
        "ご用意しています🌟\n\n"
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
