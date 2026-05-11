#!/bin/bash
# Steve アバター生成 — ターミナルで直接実行してください
# Usage: bash products/d-manager/gen_steve_avatar.sh

set -e
cd "$(dirname "$0")"

unset ALL_PROXY HTTP_PROXY HTTPS_PROXY http_proxy https_proxy all_proxy

PYTHON="$HOME/projects/ccskill-nanobanana/venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="$HOME/Projects/ccskill-nanobanana/venv/bin/python3"
fi

"$PYTHON" - << 'PYEOF'
import os, io, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.home() / "projects" / "ccskill-nanobanana" / ".env")

from google import genai
from google.genai import types
from PIL import Image

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
print(f"API key: {'OK' if api_key else 'MISSING'}")

client = genai.Client(api_key=api_key)

ref_path = Path(__file__).parent / "avatars" / "riku.png"
ref_bytes = io.BytesIO()
Image.open(ref_path).save(ref_bytes, format="PNG")
ref_bytes.seek(0)

prompt = """Using this reference image as the EXACT style guide, generate a character avatar with the SAME anime art style, circular frame, and composition.

Character: Steve — Male CEO (inspired by Steve Jobs)
- Short salt-and-pepper hair, neatly combed back
- Black turtleneck sweater (iconic Steve Jobs look)
- Sharp, intense eyes with a visionary, confident expression
- Slight charismatic smile
- White background, thin circular border
- Same anime-illustration style, same line weight as the reference"""

response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=[
        types.Part.from_bytes(data=ref_bytes.read(), mime_type="image/png"),
        prompt,
    ],
    config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
)

out = Path(__file__).parent / "avatars" / "steve.png"
for part in response.candidates[0].content.parts:
    if part.inline_data:
        img = Image.open(io.BytesIO(part.inline_data.data))
        img.save(out)
        print(f"✅ Saved: {out} {img.size}")
        sys.exit(0)

print("❌ No image in response")
for part in response.candidates[0].content.parts:
    if part.text:
        print(part.text[:300])
PYEOF
