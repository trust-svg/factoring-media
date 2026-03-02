"""LINE リッチメニュー作成スクリプト（初期設定時に一度だけ実行する）"""

import os

from dotenv import load_dotenv
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessageAction,
    RichMenuArea,
    RichMenuBounds,
    RichMenuRequest,
    RichMenuSize,
    URIAction,
)

load_dotenv()

STORES_URL = "https://sion-salon.stores.jp"

RICH_MENU_DEFINITION = RichMenuRequest(
    size=RichMenuSize(width=2500, height=843),
    selected=True,
    name="メインメニュー",
    chat_bar_text="メニューを開く ✨",
    areas=[
        # 上段左: タロット占い
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=0, width=833, height=421),
            action=MessageAction(label="タロット占い", text="タロット占いをしてください"),
        ),
        # 上段中: 星座占い
        RichMenuArea(
            bounds=RichMenuBounds(x=833, y=0, width=834, height=421),
            action=MessageAction(label="星座占い", text="星座占いをしてください"),
        ),
        # 上段右: 数秘術
        RichMenuArea(
            bounds=RichMenuBounds(x=1667, y=0, width=833, height=421),
            action=MessageAction(label="数秘術", text="数秘術で占ってください"),
        ),
        # 下段左: 今日の運勢
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=421, width=833, height=422),
            action=MessageAction(label="今日の運勢", text="今日の運勢を教えてください"),
        ),
        # 下段中: 本鑑定（STORES）
        RichMenuArea(
            bounds=RichMenuBounds(x=833, y=421, width=834, height=422),
            action=URIAction(label="本鑑定", uri=STORES_URL),
        ),
        # 下段右: プランを見る
        RichMenuArea(
            bounds=RichMenuBounds(x=1667, y=421, width=833, height=422),
            action=MessageAction(label="プランを見る", text="プランを教えてください"),
        ),
    ],
)


def create_rich_menu() -> str:
    """リッチメニューを作成してIDを返す"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        result = line_api.create_rich_menu(rich_menu_request=RICH_MENU_DEFINITION)
        rich_menu_id = result.rich_menu_id
        print(f"✅ リッチメニュー作成完了")
        print(f"   ID: {rich_menu_id}")
        print()
        print("次のステップ:")
        print("1. LINE Developers Console でこのIDに背景画像をアップロード")
        print("   （2500×843px の画像が必要です）")
        print("2. このIDをデフォルトリッチメニューに設定")
        print()
        print(f"   line_api.set_default_rich_menu(rich_menu_id='{rich_menu_id}')")
        return rich_menu_id


def set_default_rich_menu(rich_menu_id: str) -> None:
    """指定IDをデフォルトリッチメニューに設定する"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        line_api.set_default_rich_menu(rich_menu_id=rich_menu_id)
        print(f"✅ デフォルトリッチメニューを設定しました: {rich_menu_id}")


if __name__ == "__main__":
    menu_id = create_rich_menu()
    # 画像アップロード後に set_default_rich_menu(menu_id) を実行してください
