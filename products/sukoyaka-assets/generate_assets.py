#!/usr/bin/env python3
"""
generate_assets.py — Flux Pro APIで人物素材3点を生成するスクリプト
"""

import os
import fal_client
from dotenv import load_dotenv
from pathlib import Path
from prompts import WOMAN_A, WOMAN_B, COUPLE, FLUX_MODEL, GENERATION_PARAMS
from config import FLUX_DIR

load_dotenv()


def generate_image(prompt: str, output_filename: str) -> str:
    """
    Flux Pro APIで画像を生成してローカルに保存する。
    Returns: 保存されたファイルパス
    """
    print(f"生成中: {output_filename} ...")

    result = fal_client.subscribe(
        FLUX_MODEL,
        arguments={
            "prompt": prompt,
            **GENERATION_PARAMS,
        },
        with_logs=True,
    )

    image_url = result["images"][0]["url"]

    # ダウンロードして保存
    import requests
    response = requests.get(image_url)
    response.raise_for_status()

    output_path = Path(FLUX_DIR) / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"  保存完了: {output_path}")
    return str(output_path)


def main():
    api_key = os.getenv("FAL_KEY")
    if not api_key or api_key == "your_fal_api_key_here":
        print("エラー: .env に FAL_KEY を設定してください")
        print("  取得先: https://fal.ai → API Keys")
        return

    os.environ["FAL_KEY"] = api_key

    assets = [
        (WOMAN_A, "woman_a.png"),
        (WOMAN_B, "woman_b.png"),
        (COUPLE, "couple.png"),
    ]

    results = {}
    for prompt, filename in assets:
        path = generate_image(prompt, filename)
        results[filename] = path

    print("\n=== 生成完了 ===")
    for filename, path in results.items():
        print(f"  {filename}: {path}")
    print("\n次のステップ: Figma MCPでレイアウトを組み立ててください")
    print("  参照: docs/superpowers/specs/2026-04-06-app-store-assets-design.md")


if __name__ == "__main__":
    main()
