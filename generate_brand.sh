#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

echo "=== 1. Logo ==="
$PY $GEN "A clean minimal logo design for 'ファクセル' (FACCEL), a Japanese B2B factoring comparison website. The logo consists of the text 'ファクセル' in bold modern Japanese font with 'FACCEL' in smaller text below. The text color is dark navy blue #1e3a8a. A small abstract geometric accent mark in blue #2563EB to the left of the text, suggesting growth/trust (like an upward chevron or checkmark). Pure white background. No gradients, no decorative elements. Clean corporate minimal style. The logo should work at small sizes." --resolution 2K --aspect 3:1 --output $OUT

echo "=== 2. Advisor Sanada - main (front facing, suit, confident) ==="
$PY $GEN "A professional Japanese male business consultant named Sanada in his early 40s. He is wearing a dark navy blue suit with a white shirt and no tie (business casual). He has short neat black hair, glasses with thin frames, and a warm confident smile. He is looking directly at the camera. His right hand is raised slightly in an explaining gesture. Shot against a pure white background for easy cutout. Studio lighting, bright and even with no shadows on background. Upper body visible from waist up. Professional corporate portrait. Canon EOS R5, 85mm f/1.4 lens." --resolution 2K --aspect 3:4 --output $OUT

echo "=== 3. Advisor Sanada - pointing (explaining pose) ==="
$PY $GEN "The same Japanese male business consultant in his early 40s, dark navy suit, white shirt, thin-framed glasses, short black hair. He is pointing upward with his right index finger in a 'key point' gesture, with a slightly serious but friendly expression. Looking directly at the camera. Pure white background for easy cutout. Studio lighting, bright and even. Upper body from waist up. Professional corporate style." --resolution 1K --aspect 3:4 --output $OUT

echo "=== 4. Advisor Sanada - thinking (chin touch) ==="
$PY $GEN "The same Japanese male business consultant in his early 40s, dark navy suit, white shirt, thin-framed glasses, short black hair. He has his hand on his chin in a thinking pose, with a thoughtful expression. Looking directly at the camera. Pure white background for easy cutout. Studio lighting, bright and even. Upper body from waist up. Professional corporate style." --resolution 1K --aspect 3:4 --output $OUT

echo "=== All done ==="
ls -lht $OUT/*.jpg $OUT/*.png 2>/dev/null | head -10
