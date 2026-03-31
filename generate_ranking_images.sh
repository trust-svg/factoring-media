#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

echo "=== 1. Crown rank 1 (gold) ==="
$PY $GEN "A premium gold crown badge with the number '1' in the center. The crown is ornate with jewels and sits above a circular gold medal. Rich golden color #FFD700 with metallic shine and subtle shadow. Dark navy background #172554. Clean vector style, suitable for a ranking website. The number 1 is large, bold, and white." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 2. Crown rank 2 (silver) ==="
$PY $GEN "A premium silver crown badge with the number '2' in the center. The crown is ornate and sits above a circular silver medal. Metallic silver color with shine and subtle shadow. Dark navy background #172554. Clean vector style, suitable for a ranking website. The number 2 is large, bold, and white." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 3. Crown rank 3 (bronze) ==="
$PY $GEN "A premium bronze crown badge with the number '3' in the center. The crown is ornate and sits above a circular bronze/copper medal. Warm bronze color #CD7F32 with metallic shine and subtle shadow. Dark navy background #172554. Clean vector style, suitable for a ranking website. The number 3 is large, bold, and white." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 4. Rank 4 badge ==="
$PY $GEN "A clean circular badge with the number '4' in the center. Simple blue gradient circle from #2563EB to #1e40af. The number 4 is large, bold, and white. Dark navy background #172554. Minimal clean design, no crown, just a simple numbered badge." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 5. Rank 5 badge ==="
$PY $GEN "A clean circular badge with the number '5' in the center. Simple blue gradient circle from #2563EB to #1e40af. The number 5 is large, bold, and white. Dark navy background #172554. Minimal clean design, no crown, just a simple numbered badge." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 6. Section header: 業者一覧 ==="
$PY $GEN "A sleek financial comparison website section header. Dark navy blue gradient background from #172554 to #1e3a8a. Bold white Japanese text 'ファクタリング業者一覧' centered. Subtle geometric accent lines and a small list icon on the left. Below in smaller light cyan text '手数料・入金速度・評価を一目で比較'. Clean, professional, corporate design. No photos." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 7. Section header: おすすめTOP3 ==="
$PY $GEN "A premium ranking section header for a financial comparison website. Dark navy blue gradient background from #172554 to #1e3a8a. At the top, a small gold crown icon and text '厳選ランキング' in gold color. Below, large bold white Japanese text 'おすすめファクタリング業者 TOP3'. At the bottom, smaller text '2026年最新版 - 口コミ・手数料・入金速度を総合評価' in light cyan. Clean elegant financial design with subtle gold accent lines." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 8. Company card: OLTA ==="
$PY $GEN "A premium company comparison card for a financial website. White background with blue accents. Company name 'OLTA' in large bold navy text at top. Below are three large stat blocks side by side: Left block shows '2%-9%' in large bold blue text with label '手数料' below. Center block shows '最短即日' in large bold green text with label '入金速度' below. Right block shows '4.5' with a gold star icon in large bold text with label '総合評価' below. Clean corporate infographic style. Each stat number should be very large and eye-catching." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 9. Company card: ペイトナー ==="
$PY $GEN "A premium company comparison card for a financial website. White background with blue accents. Company name 'ペイトナーファクタリング' in large bold navy text at top. Below are three large stat blocks side by side: Left block shows '一律10%' in large bold blue text with label '手数料' below. Center block shows '最短10分' in large bold green text with label '入金速度' below. Right block shows '4.3' with a gold star icon in large bold text with label '総合評価' below. Clean corporate infographic style. Each stat number should be very large and eye-catching." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 10. Company card: QuQuMo ==="
$PY $GEN "A premium company comparison card for a financial website. White background with blue accents. Company name 'QuQuMo' in large bold navy text at top. Below are three large stat blocks side by side: Left block shows '1%-14.8%' in large bold blue text with label '手数料' below. Center block shows '最短2時間' in large bold green text with label '入金速度' below. Right block shows '4.2' with a gold star icon in large bold text with label '総合評価' below. Clean corporate infographic style. Each stat number should be very large and eye-catching." --resolution 2K --aspect 16:9 --output $OUT

echo "=== All done ==="
ls -lht $OUT/*.jpg $OUT/*.png 2>/dev/null | head -15
