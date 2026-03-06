"""LINE リッチメニュー作成スクリプト（初期設定時に一度だけ実行する）

使い方:
  cd ai-fortune
  pip install Pillow  # 画像生成用（ローカルのみ）
  python -m line_features.rich_menu

カスタム画像を使う場合:
  python -m line_features.rich_menu path/to/image.png
"""
from __future__ import annotations

import os
import sys

import httpx
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

# 3パネル（1行）: 簡易鑑定 | 料金・メニュー | 本鑑定を申し込む
RICH_MENU_DEFINITION = RichMenuRequest(
    size=RichMenuSize(width=2500, height=843),
    selected=True,
    name="メインメニュー",
    chat_bar_text="メニューを開く ✨",
    areas=[
        # 左: 簡易鑑定（無料）
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=0, width=833, height=843),
            action=MessageAction(label="簡易鑑定", text="簡易鑑定をお願いします"),
        ),
        # 中: 料金・メニュー
        RichMenuArea(
            bounds=RichMenuBounds(x=833, y=0, width=834, height=843),
            action=MessageAction(label="料金・メニュー", text="プランを教えてください"),
        ),
        # 右: 本鑑定（STORES）
        RichMenuArea(
            bounds=RichMenuBounds(x=1667, y=0, width=833, height=843),
            action=URIAction(label="本鑑定を申し込む", uri=STORES_URL),
        ),
    ],
)


def generate_menu_image(output_path: str = "rich_menu.png") -> str:
    """リッチメニュー画像を生成する（2500x843px）"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow が必要です: pip install Pillow")
        sys.exit(1)

    width, height = 2500, 843
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # 3パネルの色設定（紫系）
    panels = [
        {"color": (88, 44, 140), "text": "簡易鑑定\n（無料）"},
        {"color": (120, 60, 160), "text": "料金・\nメニュー"},
        {"color": (150, 80, 180), "text": "本鑑定を\n申し込む"},
    ]

    panel_w = width // 3

    # 日本語フォント探索（macOS → Linux）
    font = None
    font_paths = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 64)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()
        print("日本語フォントが見つかりません。テキストが正しく表示されない可能性があります。")

    for i, panel in enumerate(panels):
        x0 = i * panel_w
        x1 = x0 + panel_w

        # パネル背景
        draw.rectangle([x0, 0, x1, height], fill=panel["color"])

        # 区切り線（白）
        if i > 0:
            draw.line([(x0, 20), (x0, height - 20)], fill=(255, 255, 255), width=3)

        # テキスト中央配置
        x_center = x0 + panel_w // 2
        y_center = height // 2
        bbox = draw.multiline_textbbox((0, 0), panel["text"], font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.multiline_text(
            (x_center - tw // 2, y_center - th // 2),
            panel["text"],
            fill=(255, 255, 255),
            font=font,
            align="center",
        )

    img.save(output_path)
    print(f"メニュー画像を生成しました: {output_path}")
    return output_path


def create_rich_menu() -> str:
    """リッチメニューを作成してIDを返す"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        result = line_api.create_rich_menu(rich_menu_request=RICH_MENU_DEFINITION)
        menu_id = result.rich_menu_id
        print(f"リッチメニュー作成完了: {menu_id}")
        return menu_id


def upload_rich_menu_image(rich_menu_id: str, image_path: str) -> None:
    """リッチメニューに画像をアップロードする"""
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    with open(image_path, "rb") as f:
        image_data = f.read()

    resp = httpx.post(
        f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/png",
        },
        content=image_data,
        timeout=30.0,
    )
    resp.raise_for_status()
    print("画像アップロード完了")


def set_default_rich_menu(rich_menu_id: str) -> None:
    """デフォルトリッチメニューに設定する"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        line_api.set_default_rich_menu(rich_menu_id=rich_menu_id)
        print("デフォルトリッチメニュー設定完了")


def delete_all_rich_menus() -> None:
    """既存のリッチメニューを全削除する（リセット用）"""
    line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        menus = line_api.get_rich_menu_list()
        for menu in menus.richmenus:
            line_api.delete_rich_menu(menu.rich_menu_id)
            print(f"  削除: {menu.rich_menu_id} ({menu.name})")
        if not menus.richmenus:
            print("  既存メニューなし")


def setup_all(image_path: str | None = None) -> None:
    """リッチメニューの一括セットアップ"""
    print("=" * 50)
    print(" 占いサロン Sion — リッチメニューセットアップ")
    print("=" * 50)
    print()

    # 0. 既存メニュー削除
    print("[1/4] 既存リッチメニュー削除...")
    delete_all_rich_menus()

    # 1. メニュー作成
    print("[2/4] リッチメニュー作成...")
    menu_id = create_rich_menu()

    # 2. 画像
    print("[3/4] 画像準備...")
    if image_path is None:
        image_path = generate_menu_image()
    else:
        print(f"指定画像を使用: {image_path}")

    # 3. アップロード + デフォルト設定
    upload_rich_menu_image(menu_id, image_path)

    print("[4/4] デフォルトメニューに設定...")
    set_default_rich_menu(menu_id)

    print()
    print("セットアップ完了!")
    print(f"  メニューID: {menu_id}")
    print("  LINEアプリでメニューが表示されることを確認してください。")


if __name__ == "__main__":
    image_arg = sys.argv[1] if len(sys.argv) > 1 else None
    setup_all(image_path=image_arg)
