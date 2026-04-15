#!/usr/bin/env python3
"""
Dark Luxury LP用 画像一括生成スクリプト
NanoBananaPro (Gemini Image API) を使用
"""

import os
import sys
import time
import shutil
from pathlib import Path

# SOCKS proxyを除去
for k in list(os.environ):
    kl = k.lower()
    if kl in ("all_proxy", "ftp_proxy", "grpc_proxy", "rsync_proxy"):
        del os.environ[k]

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

# NanoBananaPro の .env からAPIキーを読み込む
load_dotenv(Path.home() / "projects" / "ccskill-nanobanana" / ".env")

OUTPUT_DIR = Path(__file__).parent / "generated"
MODEL = "gemini-2.5-flash-image"  # gemini-3-pro-image-previewが503の場合のフォールバック

# 全LP一覧
LP_DIRS = [
    "MassiveLP", "MemoriaLP", "TravisLP", "JoyRideLP",
    "ASAPLP", "TourLP", "OliveLP", "ActionLP", "楽艶LP"
]

# 共通スタイル指示
STYLE_BASE = """
IMPORTANT STYLE RULES:
- Japanese woman, age 35-45, cute/pretty face (可愛い系), NOT cool/sexy type
- Larger bust (Fcup), visible but tasteful - wearing fitted clothing that shows curves naturally
- Warm, friendly, approachable expression - the kind of woman who makes you feel comfortable
- Natural makeup, soft features, slightly round face
- NOT luxury/hostess/club vibe - absolutely NO cocktail glasses, NO bar counters, NO expensive jewelry
- Photorealistic, high quality, natural lighting
- The vibe should be: "the cute woman next door who you'd meet at a casual outing"
""".strip()

# 各画像の定義: (ファイル名, アスペクト比, プロンプト)
IMAGES = [
    ("hero.png", "16:9", f"""
Generate a warm, inviting scene of a Japanese man (50s, average-looking, slightly round face, friendly smile, casual jacket over polo shirt) and a cute Japanese woman (late 30s, {STYLE_BASE.split('Larger bust')[0]} larger bust, wearing a fitted beige knit top) sitting at a casual outdoor cafe terrace in the evening. Warm string lights in the background. They are laughing together naturally over coffee. The mood is relaxed and happy - NOT luxury, NOT a bar. Think "neighborhood cafe date". Warm golden hour lighting.
{STYLE_BASE}
"""),

    ("vision.png", "1:1", f"""
Portrait of a cute Japanese woman, age 38, sitting at a bright casual cafe during daytime. She is wearing a fitted light pink knit sweater that shows her curves naturally (large bust, Fcup). She has a warm, genuine smile looking slightly toward camera. Short bob haircut, natural makeup. Background is a cozy cafe with plants and warm wood interior. She looks friendly and approachable - like someone you'd want to talk to. Holding a coffee cup with both hands.
{STYLE_BASE}
"""),

    ("woman_40s_1.png", "16:9", f"""
A cute Japanese woman, age 40, in a casual Italian restaurant (NOT high-end). She is wearing a fitted navy blue V-neck knit top that shows her figure naturally (large bust). She has shoulder-length dark hair, gentle smile, and is resting her chin on her hand. The restaurant has warm lighting, checkered tablecloth, casual atmosphere. A glass of water and pasta on the table. She looks relaxed and happy.
{STYLE_BASE}
"""),

    ("woman_40s_2.png", "16:9", f"""
A cute Japanese woman, age 42, at a lively izakaya (Japanese pub). She is wearing a fitted cream-colored ribbed turtleneck sweater (large bust visible through fitted clothing). She has medium-length hair with soft waves, laughing naturally with a beer glass on the table. The izakaya has warm yellow lighting, wooden counter, Japanese menu signs in background. Very casual, warm atmosphere. She looks fun and easy to talk to.
{STYLE_BASE}
"""),

    ("rendezvous.png", "16:9", f"""
A wide shot of a Japanese couple meeting at a casual cafe terrace in the evening. The man is average-looking, 50s, wearing a simple button-down shirt and slacks - NOT a suit. The woman is cute, late 30s, wearing a fitted cardigan over a camisole top (showing curves). They are sitting across from each other, both smiling warmly. Background shows a quiet Japanese shopping street with soft warm lights. The mood is "first casual meetup" - comfortable, not fancy.
{STYLE_BASE}
"""),

    ("smartphone_woman.png", "4:3", f"""
A cute Japanese woman, age 36, sitting on a sofa at home in the evening, looking at her smartphone with a happy, excited smile. She is wearing a fitted room wear / loungewear top (V-neck, showing curves naturally, large bust). Her hair is in a messy bun. Warm room lighting, cozy apartment interior with cushions. She looks like she just received a fun message. The vibe is "getting excited about a new match on her phone at home".
{STYLE_BASE}
"""),

    ("night_walk.png", "16:9", f"""
A Japanese couple walking together on a quiet residential street at night. The man is 50s, casual jacket, relaxed posture. The woman is late 30s, cute face, wearing a fitted coat that shows her figure. They are walking close together, the woman looking up at the man with a warm smile. Soft street lights and a few shop signs in the background. NOT a busy nightlife area - more like a quiet neighborhood after dinner. Romantic but comfortable atmosphere.
{STYLE_BASE}
"""),
]


def generate_image(client, name, aspect_ratio, prompt, max_retries=5):
    """1枚の画像を生成"""
    output_path = OUTPUT_DIR / name

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size="2K",
                    ),
                ),
            )
            for part in response.parts:
                if part.text is not None:
                    print(f"  [Info] {part.text}", flush=True)
                elif part.inline_data is not None:
                    image = part.as_image()
                    image.save(str(output_path))
                    print(f"  [Saved] {output_path}", flush=True)
                    return True
            print("  [Warning] レスポンスに画像なし", flush=True)
            return False
        except Exception as e:
            err_str = str(e)
            if ("503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str) and attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  [Retry] {wait}秒後にリトライ ({attempt+1}/{max_retries})", flush=True)
                time.sleep(wait)
            else:
                print(f"  [Error] {e}", flush=True)
                return False
    return False


def distribute_images(base_dir):
    """生成画像を全LPにコピー"""
    generated = list(OUTPUT_DIR.glob("*.png"))
    if not generated:
        print("[Warning] コピーする画像がありません", flush=True)
        return

    for lp_dir_name in LP_DIRS:
        lp_images_dir = base_dir / lp_dir_name / "images"
        if not lp_images_dir.exists():
            print(f"  [Skip] {lp_dir_name}/images が見つかりません", flush=True)
            continue

        for img_path in generated:
            dest = lp_images_dir / img_path.name
            shutil.copy2(str(img_path), str(dest))
        print(f"  [Copied] {lp_dir_name} <- {len(generated)}枚", flush=True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_dir = Path(__file__).parent

    # 既に生成済みをスキップ
    existing = {p.stem for p in OUTPUT_DIR.glob("*.png")}

    client = genai.Client()

    results = {}
    for name, aspect, prompt in IMAGES:
        stem = Path(name).stem
        if stem in existing:
            print(f"[Skip] {name} — 既に生成済み", flush=True)
            results[name] = "skipped"
            continue

        print(f"\n[Generating] {name} ({aspect})", flush=True)
        success = generate_image(client, name, aspect, prompt)
        results[name] = "done" if success else "failed"

        # API rate limit対策
        time.sleep(5)

    # 結果サマリー
    print(f"\n{'='*50}", flush=True)
    print("生成結果サマリー", flush=True)
    print(f"{'='*50}", flush=True)
    success_count = 0
    for name, status in results.items():
        icon = "ok" if status in ("done", "skipped") else "NG"
        if status in ("done", "skipped"):
            success_count += 1
        print(f"  {icon} {name}: {status}", flush=True)
    print(f"\n{success_count}/{len(IMAGES)} 完了", flush=True)

    # 全LPに配布
    if success_count > 0:
        print(f"\n{'='*50}", flush=True)
        print("全LPに画像を配布中...", flush=True)
        distribute_images(base_dir)
        print("配布完了!", flush=True)


if __name__ == "__main__":
    main()
