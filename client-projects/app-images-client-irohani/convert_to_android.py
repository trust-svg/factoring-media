#!/usr/bin/env python3
"""
いろはに - iOS App Store画像 → Android版アプリダウンロードページ画像 変換スクリプト

Usage:
    # 人物プレースホルダーで仮出力
    python3 convert_to_android.py

    # 人物写真を指定して本番出力
    python3 convert_to_android.py --person-left woman.png --person-right man.png

    # 特定の画像のみ出力
    python3 convert_to_android.py --only ver01

Requirements:
    pip install "Pillow>=10.0"
"""

import argparse
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────

FOLDER = os.path.dirname(os.path.abspath(__file__))

FONTS = {
    "w7": "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "w5": "/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc",
    "w4": "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "w3": "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "maru": "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
}

COLORS = {
    "phone_body":      (28, 28, 30),
    "phone_bezel":     (44, 44, 46),
    "phone_screen":    (240, 248, 236),
    "phone_button":    (62, 62, 64),
    "phone_shadow":    (0, 0, 0, 60),
    "bg_light":        (248, 255, 242),
    "bg_green":        (200, 235, 175),
    "placeholder_bg":  (208, 225, 200),
    "placeholder_fg":  (140, 175, 130),
    "placeholder_txt": (80, 120, 75),
    "panel_bg":        (255, 255, 255, 230),
    "panel_border":    (90, 160, 80),
    "text_dark":       (35, 35, 35),
    "text_green":      (40, 100, 40),
    "text_red":        (190, 30, 30),
    "header_bg":       (25, 80, 25),
    "header_text":     (255, 255, 255),
    "footer_bg":       (25, 80, 25),
    "footer_text":     (255, 255, 255),
}

# ─────────────────────────────────────────────
# テキスト内容
# ─────────────────────────────────────────────

TEXTS = {
    "ver01": {
        "panel1_lines": ["「笑える」「うなれる」", "「つながれる」"],
        "panel1_sub":   ["大歓迎"],
        "panel2_lines": ["おじさん構文も", "ダジャレも"],
        "panel2_accent": "OK",
    },
    "ver02": {
        "header":    "こんな方におすすめ",
        "rec1": ["川柳を気軽に", "楽しみたい方"],
        "rec2": ["「ちょっとひと言」", "言いたくなる方"],
        "rec3": ["日本語の面白さを", "再発見したい方"],
    },
    "ver03": {
        "header":     "いろはにの主な機能",
        "feature1":   "川柳・ダジャレなど自由な表現で\n楽しめます。",
        "feature2":   "AIが自己紹介を作成するから簡単",
        "feature3":   "ルール違反はAIが即対応で安心",
        "feature4":   "24時間サポートで安心",
        "footer_note": "※年齢・性別・地域の入力は任意。\n安全で共感しやすいコミュニティ運営のためにのみ利用します。",
    },
    "feature": {
        "main_catch":  "言葉で笑い、言葉でつながる",
        "sub_catch":   "みんなの川柳コミュニティ　いろはに",
        "left_text":   ["毎日のお題で、", "笑って・考えて・", "つながって"],
        "right_text":  ["ことばで遊ぶ、", "笑いと共感の", "川柳広場"],
        "footer":      "川柳初心者も、おじさん構文の達人も、ようこそ「いろはに」へ",
    },
}

# ─────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────

def load_font(key: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS[key]
    try:
        return ImageFont.truetype(path, size=size, index=0)
    except OSError:
        print(f"[WARN] フォント読み込み失敗: {path}  → デフォルトフォントを使用")
        return ImageFont.load_default()


def draw_gradient_rect(img: Image.Image, x: int, y: int, w: int, h: int,
                        color_top=(248, 255, 242), color_bottom=(215, 240, 200)) -> None:
    """上から下へ縦グラデーション矩形を描画"""
    draw = ImageDraw.Draw(img)
    for i in range(h):
        t = i / max(h - 1, 1)
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
        draw.line([(x, y + i), (x + w, y + i)], fill=(r, g, b))


def draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill=None,
                       outline=None, outline_width=2) -> None:
    """角丸矩形（Pillow 8.2+ の rounded_rectangle を使用）"""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                            outline=outline, width=outline_width)


def draw_flower(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 16,
                petal_color=(200, 35, 35), center_color=(230, 190, 40),
                petals: int = 6) -> None:
    """梅の花（装飾）を描画"""
    for i in range(petals):
        angle = 2 * math.pi * i / petals
        px = cx + int(r * 1.6 * math.cos(angle))
        py = cy + int(r * 1.6 * math.sin(angle))
        draw.ellipse([px - r, py - r, px + r, py + r], fill=petal_color)
    draw.ellipse([cx - int(r * 0.7), cy - int(r * 0.7),
                  cx + int(r * 0.7), cy + int(r * 0.7)],
                 fill=center_color)


# ─────────────────────────────────────────────
# Androidモックアップ描画
# ─────────────────────────────────────────────

def draw_android_phone(img: Image.Image, cx: int, cy: int,
                        phone_w: int = 310, phone_h: int = 640) -> None:
    """
    Androidスマートフォンを描画する。
    cx, cy: 端末の中心座標
    """
    draw = ImageDraw.Draw(img, "RGBA")

    x0 = cx - phone_w // 2
    y0 = cy - phone_h // 2
    x1 = cx + phone_w // 2
    y1 = cy + phone_h // 2

    # ドロップシャドウ（楕円でぼかし）
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    sdraw.rounded_rectangle([x0 + 8, y0 + 12, x1 + 8, y1 + 12],
                             radius=38, fill=(0, 0, 0, 60))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=14))
    img.paste(shadow_layer, mask=shadow_layer)

    draw = ImageDraw.Draw(img)

    # 1. ボディ外形
    draw.rounded_rectangle([x0, y0, x1, y1], radius=38,
                            fill=COLORS["phone_body"])

    # 2. ベゼル（内側 6px）
    draw.rounded_rectangle([x0 + 6, y0 + 6, x1 - 6, y1 - 6], radius=32,
                            fill=COLORS["phone_bezel"])

    # 3. スクリーン（ベゼルの内側 6px）
    sx0 = x0 + 12
    sy0 = y0 + 14
    sx1 = x1 - 12
    sy1 = y1 - 14
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=26,
                            fill=COLORS["phone_screen"])

    # 4. スクリーン内グラデーション（ブランドカラー）
    screen_w = sx1 - sx0
    screen_h = sy1 - sy0
    for i in range(screen_h):
        t = i / max(screen_h - 1, 1)
        sr = int(248 + (215 - 248) * t)
        sg = int(255 + (242 - 255) * t)
        sb = int(242 + (195 - 242) * t)
        draw.line([(sx0, sy0 + i), (sx1, sy0 + i)], fill=(sr, sg, sb))

    # 5. パンチホールカメラ（上部中央）
    cam_cx = cx
    cam_cy = sy0 + 22
    cam_r = 7
    draw.ellipse([cam_cx - cam_r, cam_cy - cam_r,
                  cam_cx + cam_r, cam_cy + cam_r],
                 fill=(12, 12, 14))
    # カメラレンズ光沢
    draw.ellipse([cam_cx - cam_r + 2, cam_cy - cam_r + 2,
                  cam_cx - cam_r + 5, cam_cy - cam_r + 5],
                 fill=(80, 80, 90))

    # 6. ステータスバー（時刻・バッテリー）
    status_font = load_font("w4", 16)
    draw.text((cam_cx - 55, sy0 + 10), "9:41", font=status_font,
              fill=(50, 50, 50), anchor="lt")
    # バッテリーアイコン（小さい矩形）
    bx = sx1 - 40
    by = sy0 + 11
    draw.rounded_rectangle([bx, by, bx + 24, by + 12], radius=3,
                            outline=(60, 60, 60), width=2)
    draw.rounded_rectangle([bx + 2, by + 2, bx + 18, by + 10], radius=1,
                            fill=(60, 160, 60))
    draw.rounded_rectangle([bx + 24, by + 4, bx + 27, by + 8], radius=1,
                            fill=(60, 60, 60))

    # 7. 右側: 電源ボタン
    pw = 5
    draw.rounded_rectangle([x1 - 3, cy - 45, x1 + pw, cy + 45],
                            radius=3, fill=COLORS["phone_button"])

    # 8. 左側: 音量+ボタン
    draw.rounded_rectangle([x0 - pw, cy - 95, x0 + 3, cy - 30],
                            radius=3, fill=COLORS["phone_button"])

    # 9. 左側: 音量−ボタン
    draw.rounded_rectangle([x0 - pw, cy - 10, x0 + 3, cy + 55],
                            radius=3, fill=COLORS["phone_button"])

    # 10. 下部: USB-C ポート
    ux = cx - 16
    uy = y1 - 17
    draw.rounded_rectangle([ux, uy, ux + 32, uy + 9],
                            radius=4, fill=(52, 52, 55))

    # 11. アプリコンテンツ（スクリーン内にロゴ風テキストを薄く）
    try:
        app_font = load_font("maru", 28)
        logo_text = "いろはに"
        tw = draw.textlength(logo_text, font=app_font)
        tx = cx - tw // 2
        ty = cy - 20
        draw.text((tx, ty), logo_text, font=app_font,
                  fill=(60, 130, 60, 180))
    except Exception:
        pass


# ─────────────────────────────────────────────
# 人物写真プレースホルダー / 実写真貼り付け
# ─────────────────────────────────────────────

def draw_person_placeholder(img: Image.Image, x: int, y: int,
                             w: int, h: int, label: str = "人物写真") -> None:
    """人物写真エリアにプレースホルダーを描画"""
    # 背景グラデーション
    draw_gradient_rect(img, x, y, w, h,
                       color_top=(218, 238, 210), color_bottom=(195, 225, 185))

    draw = ImageDraw.Draw(img)
    cx = x + w // 2
    cy = y + h // 2

    # 人物シルエット
    head_r = min(w, h) // 8
    head_cy = cy - head_r * 2
    # 頭
    draw.ellipse([cx - head_r, head_cy - head_r,
                  cx + head_r, head_cy + head_r],
                 fill=COLORS["placeholder_fg"])
    # 胴体
    body_top = head_cy + head_r + 4
    body_bot = cy + h // 5
    tw = head_r * 2
    bw = head_r * 4
    draw.polygon([
        (cx - tw // 2, body_top),
        (cx + tw // 2, body_top),
        (cx + bw // 2, body_bot),
        (cx - bw // 2, body_bot),
    ], fill=COLORS["placeholder_fg"])

    # ラベル（幅に収まるサイズに調整）
    font_size = min(max(18, h // 28), int(w * 0.9 / max(len(label), 1)))
    font_size = max(16, min(font_size, 40))
    font = load_font("w4", font_size)
    draw.text((cx, body_bot + 20), label, font=font,
              fill=COLORS["placeholder_txt"], anchor="mt")


def paste_person_photo(img: Image.Image, photo_path: str,
                        x: int, y: int, w: int, h: int) -> None:
    """人物写真をカバーフィットで貼り付け"""
    photo = Image.open(photo_path).convert("RGBA")
    photo_ratio = photo.width / photo.height
    box_ratio = w / h
    if photo_ratio > box_ratio:
        new_h = h
        new_w = int(h * photo_ratio)
    else:
        new_w = w
        new_h = int(w / photo_ratio)
    photo = photo.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    photo = photo.crop((left, top, left + w, top + h))
    if photo.mode == "RGBA":
        img.paste(photo, (x, y), photo)
    else:
        img.paste(photo, (x, y))


def place_person(img: Image.Image, photo_path, x: int, y: int,
                  w: int, h: int, label: str = "人物写真") -> None:
    if photo_path and os.path.exists(photo_path):
        paste_person_photo(img, photo_path, x, y, w, h)
    else:
        draw_person_placeholder(img, x, y, w, h, label)


# ─────────────────────────────────────────────
# テキストパネル描画
# ─────────────────────────────────────────────

def draw_text_panel_vertical(img: Image.Image, lines, accent_line=None,
                              x: int = 0, y: int = 0,
                              w: int = 300, h: int = 400,
                              bg_color=(255, 255, 255, 230),
                              border_color=None,
                              font_key="w7", font_size=52,
                              text_color=(35, 35, 35),
                              accent_color=(190, 30, 30),
                              accent_font_key="w7", accent_size=72,
                              line_gap=12) -> None:
    """縦書き風テキストパネル（横書き・和紙風）"""
    # 半透明パネル背景
    panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)

    r, g, b, a = bg_color if len(bg_color) == 4 else (*bg_color, 230)
    panel_draw.rounded_rectangle([x, y, x + w, y + h], radius=18,
                                  fill=(r, g, b, a))
    if border_color:
        panel_draw.rounded_rectangle([x, y, x + w, y + h], radius=18,
                                      outline=border_color, width=3)
    img.paste(panel, mask=panel)

    draw = ImageDraw.Draw(img)
    font = load_font(font_key, font_size)

    # テキスト描画（行ごと）
    total_lines = len(lines)
    total_h = total_lines * (font_size + line_gap)
    if accent_line:
        total_h += accent_size + line_gap

    ty = y + (h - total_h) // 2
    for line in lines:
        tw = draw.textlength(line, font=font)
        tx = x + (w - tw) // 2
        draw.text((tx, ty), line, font=font, fill=text_color)
        ty += font_size + line_gap

    if accent_line:
        acc_font = load_font(accent_font_key, accent_size)
        tw = draw.textlength(accent_line, font=acc_font)
        tx = x + (w - tw) // 2
        draw.text((tx, ty), accent_line, font=acc_font, fill=accent_color)


def draw_recommendation_panel(img: Image.Image, lines,
                               x: int, y: int, w: int, h: int,
                               font_size: int = 40) -> None:
    """「こんな方におすすめ」の短冊パネル（縦書きスタイル）"""
    panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle([x, y, x + w, y + h], radius=14,
                              fill=(255, 255, 255, 235))
    pdraw.rounded_rectangle([x, y, x + w, y + h], radius=14,
                              outline=(100, 170, 90), width=3)
    img.paste(panel, mask=panel)

    draw = ImageDraw.Draw(img)
    font = load_font("w5", font_size)
    char_step = font_size + 6  # 1文字あたりの縦ピクセル数

    cx = x + w // 2

    # 2行を縦書きで2列に描画（右列=lines[0]、左列=lines[1]）
    # 列間隔
    col_gap = font_size + 8
    # 2列の最大文字数でテキスト総高さを計算
    max_chars = max(len(l) for l in lines) if lines else 0
    text_total_h = max_chars * char_step
    # テキスト開始Y（上部 20% 付近）
    text_start_y = y + int(h * 0.12)

    for col_i, line in enumerate(lines):
        if len(lines) == 2:
            # 2列: 右列→左列
            col_x = cx + col_gap // 2 - col_i * col_gap
        else:
            col_x = cx

        for char_i, char in enumerate(line):
            tw = draw.textlength(char, font=font)
            draw.text((col_x - tw // 2, text_start_y + char_i * char_step),
                      char, font=font, fill=(35, 35, 35))

    # 区切り線
    sep_y = text_start_y + max_chars * char_step + 16
    draw.line([(x + 20, sep_y), (x + w - 20, sep_y)],
              fill=(150, 200, 130), width=2)

    # 梅の花（装飾）
    flower_cy = sep_y + (y + h - sep_y) // 2
    draw_flower(draw, cx, flower_cy, r=18,
                petal_color=(190, 30, 30), center_color=(230, 190, 40))


def draw_feature_item(img: Image.Image, text: str,
                       x: int, y: int, w: int, h: int,
                       font_size: int = 36,
                       highlight_text: str = None) -> None:
    """「主な機能」の機能項目ボックス"""
    panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle([x, y, x + w, y + h], radius=12,
                              fill=(255, 255, 255, 235))
    pdraw.rounded_rectangle([x, y, x + w, y + h], radius=12,
                              outline=(120, 180, 110), width=2)
    img.paste(panel, mask=panel)

    draw = ImageDraw.Draw(img)
    font = load_font("w5", font_size)

    lines = text.split("\n")
    total_h = len(lines) * (font_size + 8)
    ty = y + (h - total_h) // 2

    for line in lines:
        # ハイライトワードを赤で描画
        if highlight_text and highlight_text in line:
            parts = line.split(highlight_text)
            acc_font = load_font("w7", font_size)
            # 全テキスト幅で中央揃え
            normal_font = load_font("w5", font_size)
            parts_w = [draw.textlength(p, font=normal_font) for p in parts]
            hl_w = draw.textlength(highlight_text, font=acc_font)
            total_w = sum(parts_w) + hl_w
            tx = x + (w - total_w) // 2
            # 前部分
            if parts[0]:
                draw.text((tx, ty), parts[0], font=normal_font, fill=(35, 35, 35))
                tx += parts_w[0]
            # ハイライト部分
            draw.text((tx, ty), highlight_text, font=acc_font, fill=(190, 30, 30))
            tx += int(hl_w)
            # 後部分
            if len(parts) > 1 and parts[1]:
                draw.text((tx, ty), parts[1], font=normal_font, fill=(35, 35, 35))
        else:
            tw = draw.textlength(line, font=font)
            tx = x + (w - tw) // 2
            draw.text((tx, ty), line, font=font, fill=(35, 35, 35))
        ty += font_size + 8


def draw_header_banner(img: Image.Image, text: str,
                        x: int, y: int, w: int, h: int,
                        font_size: int = 52) -> None:
    """緑の帯ヘッダーバナー"""
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10,
                            fill=COLORS["header_bg"])
    font = load_font("w7", font_size)
    tw = draw.textlength(text, font=font)
    tx = x + (w - tw) // 2
    ty = y + (h - font_size) // 2
    draw.text((tx, ty), text, font=font, fill=COLORS["header_text"])


def draw_footer_bar(img: Image.Image, text: str, font_size: int = 38) -> None:
    """画像下部の緑フッターバー"""
    W, H = img.size
    bar_h = max(60, font_size + 20)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H - bar_h, W, H], fill=COLORS["footer_bg"])
    font = load_font("w5", font_size)
    tw = draw.textlength(text, font=font)
    tx = (W - tw) // 2
    ty = H - bar_h + (bar_h - font_size) // 2
    draw.text((tx, ty), text, font=font, fill=COLORS["footer_text"])


# ─────────────────────────────────────────────
# 各画像の生成
# ─────────────────────────────────────────────

def generate_ver01(folder: str, person_left=None, person_right=None) -> str:
    """
    ver01: 若い女性（左）+ テキストパネル（中央）+ Androidモックアップ（右）
    サイズ: 1920×1080
    """
    src = os.path.join(folder, "app_store_main_image_ver01.jpg")
    dst = os.path.join(folder, "android_app_store_main_image_ver01.jpg")

    img = Image.open(src).convert("RGBA")
    W, H = img.size  # 1920×1080

    # ── 人物エリア（左: x 0〜640）を差し替え ──
    place_person(img, person_left, 0, 0, 640, H, "人物写真（若い女性）")

    # ── 中央エリア（元のカード類）を背景で塗りつぶす ──
    draw_gradient_rect(img, 500, 0, 730, H,
                       color_top=(248, 255, 242), color_bottom=(215, 242, 200))

    # ── テキストパネルエリアを再描画 ──
    # パネル1: 「笑える」「うなれる」「つながれる」+ 大歓迎
    draw_text_panel_vertical(
        img,
        lines=TEXTS["ver01"]["panel1_lines"],
        accent_line="大歓迎",
        x=655, y=290,
        w=540, h=210,
        bg_color=(255, 255, 255, 235),
        border_color=(100, 170, 85),
        font_key="w5", font_size=44,
        text_color=(35, 35, 35),
        accent_color=(190, 30, 30),
        accent_font_key="w7", accent_size=64,
    )

    # パネル2: おじさん構文もダジャレも OK
    draw_text_panel_vertical(
        img,
        lines=TEXTS["ver01"]["panel2_lines"],
        accent_line=TEXTS["ver01"]["panel2_accent"],
        x=655, y=530,
        w=540, h=210,
        bg_color=(255, 255, 255, 235),
        border_color=(100, 170, 85),
        font_key="w5", font_size=44,
        text_color=(35, 35, 35),
        accent_color=(190, 30, 30),
        accent_font_key="w7", accent_size=80,
    )

    # ── Androidモックアップ（右: 中心 x≈1530, y≈540）──
    # まず元のiPhone部分をグラデーションで塗りつぶす
    draw_gradient_rect(img, 1230, 50, 640, 980,
                       color_top=(248, 255, 242), color_bottom=(210, 240, 195))
    # 装飾用の花を追加
    draw = ImageDraw.Draw(img)
    draw_flower(draw, 1870, 80, r=20)
    draw_flower(draw, 1840, 130, r=14)

    draw_android_phone(img, cx=1530, cy=530, phone_w=330, phone_h=660)

    # ── フッターバー ──
    draw_footer_bar(img, "ことばでつながる川柳アプリ　いろはに", font_size=36)

    # RGBA → RGB で保存
    out = img.convert("RGB")
    out.save(dst, "JPEG", quality=95)
    return dst


def generate_ver02(folder: str, person_left=None, person_right=None) -> str:
    """
    ver02: Androidモックアップ（左）+ おすすめ3パネル（中央）+ 中年男性（右）
    サイズ: 1920×1080
    """
    src = os.path.join(folder, "app_store_main_image_ver02.jpg")
    dst = os.path.join(folder, "android_app_store_main_image_ver02.jpg")

    img = Image.open(src).convert("RGBA")
    W, H = img.size

    # ── 左エリア（phone + 上部）を完全に背景で塗りつぶす ──
    draw_gradient_rect(img, 0, 0, 580, H,
                       color_top=(248, 255, 242), color_bottom=(210, 240, 195))

    # ── 中央エリアを背景で塗りつぶす ──
    draw_gradient_rect(img, 580, 0, 730, H,
                       color_top=(248, 255, 242), color_bottom=(215, 242, 200))

    # ── Androidモックアップ（左: 中心 x≈290）──
    draw_android_phone(img, cx=290, cy=540, phone_w=320, phone_h=680)

    # 装飾用の花（左上）
    draw = ImageDraw.Draw(img)
    draw_flower(draw, 55, 90, r=22)
    draw_flower(draw, 90, 140, r=16)

    # ── ヘッダーバナー（中央エリア）──
    draw_header_banner(img, "　" + TEXTS["ver02"]["header"] + "　",
                        x=580, y=30, w=730, h=110, font_size=52)

    # ── おすすめ3パネル（縦長短冊風: 225×700px、38px）──
    panel_w = 225
    panel_h = 700
    panel_gap = 12
    total_panels_w = panel_w * 3 + panel_gap * 2
    panel_x_base = 580 + (730 - total_panels_w) // 2
    panel_y = 155

    for i, key in enumerate(["rec1", "rec2", "rec3"]):
        px = panel_x_base + i * (panel_w + panel_gap)
        draw_recommendation_panel(img, TEXTS["ver02"][key],
                                   px, panel_y, panel_w, panel_h, font_size=38)

    # ── 人物エリア（右: x 1310〜1920）──
    place_person(img, person_right, 1310, 0, W - 1310, H, "人物写真（中年男性）")

    # ── フッターバー（ver02は上部バナーのみ、フッターなし）──

    out = img.convert("RGB")
    out.save(dst, "JPEG", quality=95)
    return dst


def generate_ver03(folder: str, person_left=None, person_right=None) -> str:
    """
    ver03: 若い女性（左）+ 主な機能リスト（中央）+ Androidモックアップ（右）
    サイズ: 1920×1080
    """
    src = os.path.join(folder, "app_store_main_image_ver03.jpg")
    dst = os.path.join(folder, "android_app_store_main_image_ver03.jpg")

    img = Image.open(src).convert("RGBA")
    W, H = img.size

    # ── 人物エリア（左: x 0〜380）──
    place_person(img, person_left, 0, 0, 380, H, "人物写真（若い女性）")

    # ── 中央・右エリアを先に背景で塗りつぶす（描画順が重要）──
    draw_gradient_rect(img, 380, 0, 620, H,
                       color_top=(248, 255, 242), color_bottom=(215, 242, 200))
    draw_gradient_rect(img, 1000, 0, W - 1000, H,
                       color_top=(248, 255, 242), color_bottom=(215, 242, 200))

    # ── ヘッダーバナー（左端から電話エリア手前まで）──
    draw_header_banner(img, TEXTS["ver03"]["header"],
                        x=385, y=30, w=600, h=90, font_size=50)

    # ── 機能項目4つ ──
    items = [
        (TEXTS["ver03"]["feature1"], "自由な表現"),
        (TEXTS["ver03"]["feature2"], "簡単"),
        (TEXTS["ver03"]["feature3"], "安心"),
        (TEXTS["ver03"]["feature4"], "24時間"),
    ]
    feat_x = 395
    feat_w = 570
    feat_h = 148
    feat_y_start = 145
    feat_gap = 12

    for i, (text, hl) in enumerate(items):
        fy = feat_y_start + i * (feat_h + feat_gap)
        draw_feature_item(img, text, feat_x, fy, feat_w, feat_h,
                          font_size=34, highlight_text=hl)

    # ── Androidモックアップ（右: 中心 x≈1300）──
    draw_android_phone(img, cx=1300, cy=535, phone_w=340, phone_h=670)

    # ── 下部注記 ──
    draw = ImageDraw.Draw(img)
    note_font = load_font("w3", 24)
    note_lines = TEXTS["ver03"]["footer_note"].split("\n")
    ny = H - 90
    for line in note_lines:
        draw.text((400, ny), line, font=note_font, fill=(35, 35, 35))
        ny += 28

    # フッターバー（緑帯）
    draw.rectangle([0, H - 56, W, H], fill=COLORS["footer_bg"])
    footer_font = load_font("w5", 30)
    # ver03にはフッターテキストなし（元画像に合わせる）

    out = img.convert("RGB")
    out.save(dst, "JPEG", quality=95)
    return dst


def generate_feature_graphic(folder: str, person_left=None, person_right=None) -> str:
    """
    feature_graphic: 人物（左）+ ロゴ＋キャッチ（中央）+ 人物（右）
    サイズ: 1024×500
    """
    src = os.path.join(folder, "feature_graphic01-1024x500_01.jpg")
    dst = os.path.join(folder, "android_feature_graphic01-1024x500_01.jpg")

    img = Image.open(src).convert("RGBA")
    W, H = img.size  # 1024×500

    # ── 人物エリア（左: x 0〜260）──
    place_person(img, person_left, 0, 0, 260, H, "人物写真（女性）")

    # ── 人物エリア（右: x 760〜1024）──
    place_person(img, person_right, 760, 0, W - 760, H, "人物写真（男性）")

    # ── 中央テキストエリアを再描画 ──
    draw = ImageDraw.Draw(img)

    # 背景を軽くクリア（中央部分）
    draw_gradient_rect(img, 265, 0, 490, H,
                       color_top=(248, 255, 242), color_bottom=(210, 242, 190))

    # ロゴ画像を貼り付け（アイコンが同フォルダにある場合）
    icon_path = os.path.join(folder, "icon_512.png")
    if os.path.exists(icon_path):
        icon = Image.open(icon_path).convert("RGBA")
        icon_size = 200
        icon = icon.resize((icon_size, icon_size), Image.LANCZOS)
        ix = 512 - icon_size // 2
        iy = 30
        img.paste(icon, (ix, iy), icon)
    else:
        # ロゴが無い場合はテキストで代替
        logo_font = load_font("maru", 72)
        draw = ImageDraw.Draw(img)
        lw = draw.textlength("いろはに", font=logo_font)
        draw.text((512 - lw // 2, 30), "いろはに", font=logo_font,
                  fill=(40, 100, 40))

    draw = ImageDraw.Draw(img)

    # メインキャッチコピー
    catch_font = load_font("w7", 44)
    catch_text = TEXTS["feature"]["main_catch"]
    cw = draw.textlength(catch_text, font=catch_font)
    draw.text((512 - cw // 2, 248), catch_text, font=catch_font, fill=(35, 35, 35))

    # サブキャッチコピー
    sub_font = load_font("maru", 30)
    sub_text = TEXTS["feature"]["sub_catch"]
    sw = draw.textlength(sub_text, font=sub_font)
    draw.text((512 - sw // 2, 304), sub_text, font=sub_font, fill=(50, 110, 50))

    # 左テキスト（ロゴの左側に縦書き風テキスト）
    left_font = load_font("w4", 28)
    lty = 40
    for line in TEXTS["feature"]["left_text"]:
        lw2 = draw.textlength(line, font=left_font)
        draw.text((400 - lw2 - 10, lty), line, font=left_font,
                  fill=(40, 90, 40))
        lty += 36

    # 右テキスト
    for line in TEXTS["feature"]["right_text"]:
        rw = draw.textlength(line, font=left_font)
        draw.text((630, lty - 108 + TEXTS["feature"]["right_text"].index(line) * 36),
                  line, font=left_font, fill=(40, 90, 40))

    # ── フッターバー ──
    bar_h = 52
    draw.rectangle([0, H - bar_h, W, H], fill=COLORS["footer_bg"])
    footer_font = load_font("w5", 28)
    footer_text = TEXTS["feature"]["footer"]
    fw = draw.textlength(footer_text, font=footer_font)
    draw.text((512 - fw // 2, H - bar_h + (bar_h - 28) // 2),
              footer_text, font=footer_font, fill=COLORS["footer_text"])

    out = img.convert("RGB")
    out.save(dst, "JPEG", quality=95)
    return dst


# ─────────────────────────────────────────────
# 検証
# ─────────────────────────────────────────────

def verify_output(path: str, expected_size: tuple) -> bool:
    if not os.path.exists(path):
        print(f"  [NG] ファイルが存在しません: {path}")
        return False
    img = Image.open(path)
    if img.size != expected_size:
        print(f"  [NG] サイズ不一致: {img.size} (期待: {expected_size})")
        return False
    file_kb = os.path.getsize(path) // 1024
    if file_kb < 50:
        print(f"  [NG] ファイルサイズが小さすぎます ({file_kb}KB)")
        return False
    print(f"  [OK] {os.path.basename(path)} — {img.size}, {file_kb}KB")
    return True


# ─────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="いろはに iOS→Android 画像変換スクリプト"
    )
    parser.add_argument("--person-left", default=None,
                        help="左側の人物写真パス（PNG/JPG）")
    parser.add_argument("--person-right", default=None,
                        help="右側の人物写真パス（PNG/JPG）")
    parser.add_argument("--output-dir", default=None,
                        help="出力先フォルダ（省略時は同フォルダ）")
    parser.add_argument("--only", default=None,
                        choices=["ver01", "ver02", "ver03", "feature"],
                        help="特定の画像のみ生成")
    args = parser.parse_args()

    folder = args.output_dir or FOLDER
    pl = args.person_left
    pr = args.person_right

    print("=" * 60)
    print("いろはに Android版 画像変換スクリプト")
    print("=" * 60)

    if pl and not os.path.exists(pl):
        print(f"[WARN] person-left ファイルが見つかりません: {pl}")
        pl = None
    if pr and not os.path.exists(pr):
        print(f"[WARN] person-right ファイルが見つかりません: {pr}")
        pr = None

    tasks = {
        "ver01":   (generate_ver01,          (1920, 1080)),
        "ver02":   (generate_ver02,          (1920, 1080)),
        "ver03":   (generate_ver03,          (1920, 1080)),
        "feature": (generate_feature_graphic, (1024, 500)),
    }

    targets = [args.only] if args.only else list(tasks.keys())
    all_ok = True

    for key in targets:
        fn, expected_size = tasks[key]
        print(f"\n処理中: {key} ...")
        try:
            out_path = fn(FOLDER, pl, pr)
            ok = verify_output(out_path, expected_size)
            all_ok = all_ok and ok
        except Exception as e:
            print(f"  [ERROR] {key}: {e}")
            import traceback
            traceback.print_exc()
            all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("完了！全ての画像が正常に生成されました。")
    else:
        print("一部のエラーが発生しました。上記のメッセージを確認してください。")
    print("=" * 60)

    print("\n【次のステップ】")
    print("1. 出力画像（android_*.jpg）を確認してください")
    print("2. AIツールで人物写真を生成したら:")
    print("   python3 convert_to_android.py \\")
    print("     --person-left /path/to/woman.png \\")
    print("     --person-right /path/to/man.png")


if __name__ == "__main__":
    main()
