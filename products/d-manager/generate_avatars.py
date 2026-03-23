#!/usr/bin/env python3
"""
D-Manager AI社員アバター一括生成スクリプト

アイの参照画像をベースに、統一スタイルで13名分のアバターを生成する。
Gemini 2.5 Flash Image APIを使用（gemini-3-pro-image-previewが503のため）。
"""

import os
import sys
import time
from pathlib import Path

# SOCKS proxyを除去（socksioが入っていないため）
for k in list(os.environ):
    kl = k.lower()
    if kl in ("all_proxy", "ftp_proxy", "grpc_proxy", "rsync_proxy"):
        del os.environ[k]

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

# nano-banana-proの.envからAPIキーを読み込む
load_dotenv(Path.home() / "projects" / "ccskill-nanobanana" / ".env")

REFERENCE_IMAGE = str(Path.home() / "Claude-Workspace" / "img" / "18.png")
OUTPUT_DIR = Path(__file__).parent / "avatars"
MODEL = "gemini-2.5-flash-image"

# 各キャラの定義: (ファイル名, プロンプト)
CHARACTERS = [
    ("ai", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Ai (アイ) - Female secretary/executive assistant
- Black straight hair with bangs, shoulder length
- Navy blue blazer over white blouse
- Pearl necklace and small pearl earrings
- Warm, confident smile
- Hands clasped near chest
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("riku", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Riku (リク) - Male operations director
- Short dark brown hair, neatly styled, side part
- Navy blue suit jacket over light blue dress shirt, no tie
- Sharp, focused eyes with a slight confident smile
- Arms crossed or one hand adjusting collar
- Professional and practical appearance
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("kai", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Kai (カイ) - Male procurement/sourcing analyst
- Medium-length black hair, slightly messy but stylish
- Dark green vest over white shirt, rolled-up sleeves
- Glasses (thin rectangular frames)
- Thoughtful expression, slight smile
- One hand touching chin in thinking pose
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("sora", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Sora (ソラ) - Female fulfillment/listing specialist
- Light brown hair in a ponytail, with side-swept bangs
- Casual navy cardigan over white t-shirt
- Headset/earpiece (customer support style)
- Bright, energetic smile
- One hand giving a small wave or thumbs up
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("ren", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Ren (レン) - Male product development director
- Black hair, medium length, swept back
- Dark charcoal blazer over black turtleneck
- Calm, intellectual expression with slight smile
- Arms crossed confidently
- Clean, minimalist appearance
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("haru", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Haru (ハル) - Male software engineer
- Messy dark hair, slightly longer
- Gray hoodie over a t-shirt with a small code bracket logo
- Relaxed, friendly smile
- Holding a laptop or typing gesture
- Casual but smart appearance
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("mio", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Mio (ミオ) - Female UI/UX designer
- Dark purple-tinted black hair, bob cut with subtle highlights
- White blouse with a colorful scarf/bandana accent
- Stylish small earrings
- Creative, warm smile
- Holding a stylus pen or pencil
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("yuu", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Yuu (ユウ) - Marketing director (androgynous/stylish male)
- Styled medium brown hair with subtle highlights
- Burgundy/wine-colored blazer over white shirt
- Trendy, fashion-forward appearance
- Charismatic smile, confident posture
- One hand gesturing as if presenting an idea
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("hina", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Hina (ヒナ) - Female content creator/SNS specialist
- Long wavy light brown hair with soft curls
- Pastel pink cardigan over white top
- Small flower hair accessory
- Cheerful, approachable smile
- Holding a smartphone or making a heart gesture
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("shin", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Shin (シン) - Male advertising/analytics specialist
- Short black hair, clean cut, professional
- Dark blue suit with a subtle pattern, white shirt, slim tie
- Glasses (modern, slightly angular frames)
- Analytical, composed expression with subtle smile
- Holding or adjusting glasses
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("kei", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Kei (ケイ) - Female finance/accounting specialist
- Black hair in a neat low bun
- Dark gray blazer over cream/beige blouse
- Small stud earrings
- Careful, precise expression with gentle smile
- Holding a document or tablet
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("akira", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Akira (アキラ) - Male research analyst
- Dark hair with a slight wave, medium length
- Olive/khaki jacket over dark shirt
- Round glasses (academic style)
- Curious, thoughtful expression
- One hand holding a book or notebook
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("nao", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Nao (ナオ) - Female strategy director
- Dark hair, elegant shoulder-length with gentle waves
- Black blazer with a brooch accent
- Sophisticated, composed expression
- Slight knowing smile, leadership aura
- Hands together or one hand on chin thoughtfully
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),

    ("roki", """Using this reference image as the style guide, generate a character avatar with the EXACT SAME art style, composition, and circular frame.
Character: Roki (ロキ) - Male CEO / company founder
- Black hair, short mash style, clean and refreshing
- Navy blue jacket over white shirt, no tie
- Refreshing, bright smile with confident aura
- Youthful but authoritative presence
- One hand in pocket or relaxed confident pose
- White background, thin circular border
Keep the same anime-illustration style, same line weight, same color palette approach."""),
]


def generate_avatar(client, prompt, ref_image, output_path, max_retries=5):
    """1キャラ分のアバターを生成"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[ref_image, prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio="1:1",
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


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 既に生成済みのキャラをスキップ
    existing = {p.stem for p in OUTPUT_DIR.glob("*.png")}
    existing.update(p.stem for p in OUTPUT_DIR.glob("*.jpg"))

    client = genai.Client()
    ref_image = Image.open(REFERENCE_IMAGE)

    results = {}
    for name, prompt in CHARACTERS:
        if name in existing:
            print(f"[Skip] {name} — 既に生成済み", flush=True)
            results[name] = "skipped"
            continue

        print(f"\n[Generating] {name}", flush=True)
        out_path = OUTPUT_DIR / f"{name}.png"
        success = generate_avatar(client, prompt, ref_image, out_path)
        results[name] = "done" if success else "failed"

        # API rate limit対策
        time.sleep(3)

    # 結果サマリー
    print(f"\n{'='*50}", flush=True)
    print("生成結果サマリー", flush=True)
    print(f"{'='*50}", flush=True)
    success_count = 0
    for name, status in results.items():
        icon = "✓" if status == "done" else ("⊘" if status == "skipped" else "✗")
        if status in ("done", "skipped"):
            success_count += 1
        print(f"  {icon} {name}: {status}", flush=True)
    print(f"\n{success_count}/{len(CHARACTERS)} 完了", flush=True)


if __name__ == "__main__":
    main()
