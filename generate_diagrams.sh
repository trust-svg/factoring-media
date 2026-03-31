#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

echo "=== 1. 2社間vs3社間 comparison diagram ==="
$PY $GEN "A clean professional infographic comparing two types of factoring. Left side labeled '2社間ファクタリング' (2-party factoring) in blue #2563EB, showing 2 entities connected. Right side labeled '3社間ファクタリング' (3-party factoring) in navy #1e3a8a, showing 3 entities connected. Key differences listed below each: Left shows '取引先に知られない' '手数料 5%-20%' '最短即日'. Right shows '取引先の承諾必要' '手数料 1%-10%' '数日〜1週間'. Light gray background #f8fafc. Clean flat corporate infographic style. Japanese text must be legible." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 2. Factoring vs Bank loan comparison ==="
$PY $GEN "A professional comparison infographic. Two columns. Left column header 'ファクタリング' in blue #2563EB with a document icon. Right column header '銀行融資' in gray #64748b with a bank building icon. Comparison rows: Speed (即日 vs 2週間〜), Credit check (売掛先 vs 自社業績), Credit info (影響なし vs あり), Collateral (不要 vs 必要な場合あり), Deficit OK (可能 vs 困難). Blue checkmarks for factoring advantages, gray for bank advantages. Light background #f8fafc. Clean corporate flat design." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 3. 5 steps flow illustration ==="
$PY $GEN "A clean horizontal 5-step process flow infographic for factoring application. Step 1: '見積もり依頼' with a form icon. Step 2: '条件提示' with a document icon. Step 3: '書類提出' with an upload icon. Step 4: '審査・契約' with a checkmark icon. Step 5: '入金' with a money/bank icon. Each step is a circle with number and icon, connected by arrows. Blue gradient from light to dark (#60a5fa to #1e40af). Light background #f8fafc. Clean minimal corporate style. Japanese text must be clear." --resolution 2K --aspect 16:9 --output $OUT

echo "=== Done ==="
ls -lht $OUT/*.jpg | head -5
