#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

# Hero: Teleoperator woman on white background
$PY $GEN "A professional Japanese woman in her late 20s working as a customer service representative. She is wearing a navy blue blazer, white blouse, and a telephone headset with microphone. She is looking directly at the camera with a warm, welcoming smile and a slight head tilt. One hand is raised in a welcoming gesture. Shot against a solid white background for easy cutout. Studio lighting, bright and even with no shadows on the background. Full upper body visible from waist up. Clean, professional corporate portrait style. Canon EOS R5, 85mm lens." --resolution 2K --aspect 3:4 --output $OUT

# Badge: 2026年最新ランキング公開中
$PY $GEN "A premium modern floating badge design. The badge is a rounded pill shape with a gradient from deep blue #1e40af to bright cyan #0ea5e9, with a subtle glow effect around it. Inside the badge, bold white Japanese text reads '2026年 最新ランキング公開中'. The badge has a thin white border and a subtle drop shadow. The background is transparent dark navy #172554. Minimalist, clean, high-end financial website design. No other elements." --resolution 1K --aspect 16:9 --output $OUT

# Stats: 掲載業者数10社 / 利用満足度96% / 最短10分
$PY $GEN "A modern infographic stats bar for a financial comparison website. Three stat blocks side by side on a dark navy blue background #172554. Left block: large bold white number '10' with subscript '社' and label '掲載業者数' below in light blue. Center block: large bold white number '96' with '%' and label '利用満足度' below in light blue. Right block: large bold white text '最短10分' and label '入金スピード' below in light blue. Each block separated by a thin vertical light blue line. Clean, minimal, corporate design. The numbers should be very large and prominent." --resolution 2K --aspect 16:9 --output $OUT

echo "=== Done ==="
ls -lht $OUT/*.jpg | head -10
