#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

echo "=== 1. Logo icon (F mark) ==="
$PY $GEN "A minimal logo mark for FACCEL, a Japanese financial comparison website. The mark is a stylized letter 'F' inside a rounded square shape. The F is white, the background is a gradient from dark navy #1e3a8a to blue #2563EB. Clean, modern, simple geometric design. No text, just the icon mark. Pure white outer background for cutout. Corporate minimal style suitable for a header favicon." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 2. 2社間vs3社間 comparison ==="
$PY $GEN "A comparison infographic of two factoring types. Left: 2社間ファクタリング in blue, bullets 取引先に知られない, 手数料5-20%, 最短即日. Right: 3社間ファクタリング in navy, bullets 取引先の承諾必要, 手数料1-10%, 数日. Light gray background. Clean flat design." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 3. vs銀行融資 ==="
$PY $GEN "Comparison infographic: ファクタリング vs 銀行融資. Two columns. Factoring in blue: 即日, 売掛先審査, 信用情報なし, 担保不要, 赤字OK. Bank loan in gray: 2週間, 自社業績, 信用情報あり, 担保必要, 赤字困難. Light background. Corporate flat design." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 4. 5 steps flow ==="
$PY $GEN "Horizontal 5-step process. Step 1 見積もり依頼, Step 2 条件提示, Step 3 書類提出, Step 4 審査契約, Step 5 入金. Blue circles with numbers connected by arrows. Light background. Minimal corporate." --resolution 2K --aspect 16:9 --output $OUT

echo "=== Done ==="
ls -lht $OUT/*.jpg | head -8
