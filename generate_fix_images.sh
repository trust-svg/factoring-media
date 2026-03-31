#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

echo "=== 1. TOP3 header (site-matching bg) ==="
$PY $GEN "A minimal section header for a professional financial comparison website. Solid flat background color exactly #f8fafc (very light gray, almost white). Small gold crown icon at top center. Below it, small text '厳選ランキング' in navy #1e3a8a. Large bold text 'おすすめファクタリング業者 TOP3' in dark navy #172554. Small text below '2026年最新版 - 口コミ・手数料・入金速度を総合評価' in gray #64748b. Minimal, clean, corporate BtoB design. No gradients, no decorative elements, no photos. Just clean typography on flat light background." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 2. Company list header (site-matching bg) ==="
$PY $GEN "A minimal section header for a professional financial comparison website. Solid flat background color exactly #f8fafc (very light gray, almost white). A small navy blue list icon on the left. Bold text 'ファクタリング業者一覧' in dark navy #172554. Small text below '手数料・入金速度・評価を一目で比較' in gray #64748b. Minimal, clean, corporate BtoB design. No gradients, no decorative elements, no photos. Compact height, wide aspect ratio." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 3. Crown rank 1 (flat, transparent bg) ==="
$PY $GEN "A flat design gold crown icon with number 1. Simple geometric crown shape in flat gold #F59E0B color with white number '1' in center circle below the crown. Pure white background for easy cutout. No gradients, no 3D effects, no shadows, no jewels. Clean flat vector minimal style. Simple geometric shapes only." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 4. Crown rank 2 (flat, transparent bg) ==="
$PY $GEN "A flat design silver crown icon with number 2. Simple geometric crown shape in flat silver #94A3B8 color with white number '2' in center circle below the crown. Pure white background for easy cutout. No gradients, no 3D effects, no shadows, no jewels. Clean flat vector minimal style. Simple geometric shapes only." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 5. Crown rank 3 (flat, transparent bg) ==="
$PY $GEN "A flat design bronze crown icon with number 3. Simple geometric crown shape in flat bronze #D97706 color with white number '3' in center circle below the crown. Pure white background for easy cutout. No gradients, no 3D effects, no shadows, no jewels. Clean flat vector minimal style. Simple geometric shapes only." --resolution 1K --aspect 1:1 --output $OUT

echo "=== All done ==="
ls -lht $OUT/*.jpg $OUT/*.png 2>/dev/null | head -10
