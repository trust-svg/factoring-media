"""Create and set LINE Rich Menu for B-Manager."""

import json
import os
import httpx
from PIL import Image, ImageDraw, ImageFont

# Load from .env or env
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
API = "https://api.line.me/v2/bot"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Rich menu layout: 2 rows x 3 columns (2500x1686)
MENU_WIDTH = 2500
MENU_HEIGHT = 1686
COL_W = MENU_WIDTH // 3
ROW_H = MENU_HEIGHT // 2

BUTTONS = [
    # Row 1
    {"label": "ブリーフィング", "text": "おはよう", "emoji": "📋", "row": 0, "col": 0},
    {"label": "TODO", "text": "今日のタスク", "emoji": "✅", "row": 0, "col": 1},
    {"label": "予定確認", "text": "今日の予定", "emoji": "📅", "row": 0, "col": 2},
    # Row 2
    {"label": "経費記録", "text": "今月の経費", "emoji": "💰", "row": 1, "col": 0},
    {"label": "習慣チェック", "text": "習慣チェック", "emoji": "🏋️", "row": 1, "col": 1},
    {"label": "ヘルプ", "text": "ヘルプ", "emoji": "❓", "row": 1, "col": 2},
]


def create_menu_image(path: str):
    """Generate rich menu image with Pillow."""
    img = Image.new("RGB", (MENU_WIDTH, MENU_HEIGHT), "#1a1a2e")
    draw = ImageDraw.Draw(img)

    # Try to load a good font, fallback to default
    font_paths = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    label_font = None
    emoji_font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                label_font = ImageFont.truetype(fp, 52)
                emoji_font = ImageFont.truetype(fp, 80)
                break
            except Exception:
                continue

    if not label_font:
        label_font = ImageFont.load_default()
        emoji_font = label_font

    # Colors
    bg_colors = [
        "#16213e", "#0f3460", "#533483",
        "#e94560", "#0f3460", "#16213e",
    ]

    for btn in BUTTONS:
        x = btn["col"] * COL_W
        y = btn["row"] * ROW_H
        idx = btn["row"] * 3 + btn["col"]
        color = bg_colors[idx]

        # Button background with slight padding for grid effect
        pad = 4
        draw.rounded_rectangle(
            [x + pad, y + pad, x + COL_W - pad, y + ROW_H - pad],
            radius=20,
            fill=color,
        )

        # Emoji (centered, upper)
        emoji = btn["emoji"]
        try:
            e_bbox = draw.textbbox((0, 0), emoji, font=emoji_font)
            e_w = e_bbox[2] - e_bbox[0]
            e_h = e_bbox[3] - e_bbox[1]
            e_x = x + (COL_W - e_w) // 2
            e_y = y + ROW_H // 2 - e_h - 30
            draw.text((e_x, e_y), emoji, fill="white", font=emoji_font)
        except Exception:
            pass

        # Label (centered, lower)
        label = btn["label"]
        l_bbox = draw.textbbox((0, 0), label, font=label_font)
        l_w = l_bbox[2] - l_bbox[0]
        l_x = x + (COL_W - l_w) // 2
        l_y = y + ROW_H // 2 + 20
        draw.text((l_x, l_y), label, fill="white", font=label_font)

    img.save(path, "PNG")
    print(f"Menu image saved: {path}")


def create_rich_menu() -> str:
    """Create rich menu via LINE API and return menu ID."""
    areas = []
    for btn in BUTTONS:
        x = btn["col"] * COL_W
        y = btn["row"] * ROW_H
        areas.append({
            "bounds": {"x": x, "y": y, "width": COL_W, "height": ROW_H},
            "action": {"type": "message", "label": btn["label"], "text": btn["text"]},
        })

    body = {
        "size": {"width": MENU_WIDTH, "height": MENU_HEIGHT},
        "selected": True,
        "name": "B-Manager Menu",
        "chatBarText": "メニュー",
        "areas": areas,
    }

    resp = httpx.post(f"{API}/richmenu", headers=HEADERS, json=body)
    print(f"Create menu: {resp.status_code}")
    data = resp.json()
    menu_id = data.get("richMenuId", "")
    print(f"Menu ID: {menu_id}")
    return menu_id


def upload_image(menu_id: str, image_path: str):
    """Upload image to rich menu."""
    with open(image_path, "rb") as f:
        resp = httpx.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "image/png",
            },
            content=f.read(),
            timeout=30,
        )
    print(f"Upload image: {resp.status_code} {resp.text}")


def set_default(menu_id: str):
    """Set as default rich menu for all users."""
    resp = httpx.post(
        f"{API}/user/all/richmenu/{menu_id}",
        headers=HEADERS,
    )
    print(f"Set default: {resp.status_code} {resp.text}")


def delete_all_menus():
    """Delete all existing rich menus."""
    resp = httpx.get(f"{API}/richmenu/list", headers=HEADERS)
    menus = resp.json().get("richmenus", [])
    for m in menus:
        rid = m["richMenuId"]
        httpx.delete(f"{API}/richmenu/{rid}", headers=HEADERS)
        print(f"Deleted: {rid}")


def main():
    if not TOKEN:
        print("ERROR: LINE_CHANNEL_ACCESS_TOKEN not set")
        return

    print("=== B-Manager Rich Menu Setup ===\n")

    # Step 1: Clean up old menus
    print("1. Deleting old menus...")
    delete_all_menus()

    # Step 2: Generate image
    print("\n2. Generating menu image...")
    img_path = "/tmp/b-manager-richmenu.png"
    create_menu_image(img_path)

    # Step 3: Create menu
    print("\n3. Creating rich menu...")
    menu_id = create_rich_menu()
    if not menu_id:
        print("ERROR: Failed to create menu")
        return

    # Step 4: Upload image
    print("\n4. Uploading image...")
    upload_image(menu_id, img_path)

    # Step 5: Set as default
    print("\n5. Setting as default...")
    set_default(menu_id)

    print("\n=== Done! リッチメニューが設定されました ===")


if __name__ == "__main__":
    main()
