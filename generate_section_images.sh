#!/bin/bash
DIR="/Users/Mac_air/Claude-Workspace/ccskill-nanobanana"
PY="$DIR/venv/bin/python"
GEN="$DIR/generate_image.py"
OUT="/Users/Mac_air/Claude-Workspace/products/factoring-media/public/images"

echo "=== 1. TOP5 header banner ==="
$PY $GEN "A premium financial comparison header banner. Dark navy blue gradient background from #172554 to #1e3a8a. In the center, bold white Japanese text 'TOP5 ファクタリング業者 早見表' with a subtle gold crown icon on the left. Below the text, smaller text '2026年最新版' in light cyan. Clean, professional, minimal design. No photos, just typography and subtle geometric accent lines in gold." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 2. Factoring flow diagram ==="
$PY $GEN "A clean professional infographic explaining factoring flow. On a white background with subtle blue tones. Three entities shown as rounded rectangles connected by arrows: Left box labeled 'あなたの会社' (Your Company) in blue, Center box labeled 'ファクタリング業者' (Factoring Company) in navy blue, Right box labeled '取引先' (Client) in gray. Arrow from right to left labeled '売掛金（請求書）' (Accounts Receivable). Arrow from center to left labeled '即日入金' (Same-day Payment) in green with a money icon. Arrow from right to center labeled '支払期日に入金' (Payment on Due Date). Clean flat design, corporate style, easy to understand diagram. Japanese text must be clear and legible." --resolution 2K --aspect 16:9 --output $OUT

echo "=== 3. Worried businessman ==="
$PY $GEN "A worried Japanese male business owner in his 40s, sitting at a desk in a small office, looking stressed while reviewing financial documents and bills. He is holding his head with one hand. The desk has scattered invoices and a calculator. Soft office lighting. Photorealistic corporate photography, shot from slightly above. The mood should convey financial stress and worry." --resolution 1K --aspect 4:3 --output $OUT

echo "=== 4. Rejected at bank ==="
$PY $GEN "A disappointed Japanese businessman in his 50s leaving a bank building, looking dejected while holding a folder of documents. He is wearing a dark suit. The bank entrance with glass doors is visible in the background. Overcast lighting conveying disappointment. Photorealistic photography." --resolution 1K --aspect 4:3 --output $OUT

echo "=== 5. Urgent cash need ==="
$PY $GEN "A Japanese female small business owner in her 30s, looking worried while checking her smartphone banking app in her shop. She is biting her lip with a concerned expression. Clean bright interior. The phone screen shows a low bank balance. Photorealistic photography, close-up portrait." --resolution 1K --aspect 4:3 --output $OUT

echo "=== 6. Construction industry icon ==="
$PY $GEN "A modern flat design icon for construction industry. A stylized construction crane and building under construction on a circular blue gradient background from #2563EB to #1e40af. Clean vector style, no text, minimal design, suitable for web use as a category icon. White construction elements on blue background." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 7. Transport industry icon ==="
$PY $GEN "A modern flat design icon for transport and logistics industry. A stylized delivery truck on a circular blue gradient background from #2563EB to #1e40af. Clean vector style, no text, minimal design, suitable for web use as a category icon. White truck on blue background." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 8. IT freelance icon ==="
$PY $GEN "A modern flat design icon for IT and freelance industry. A stylized laptop computer with code brackets on screen, on a circular blue gradient background from #2563EB to #1e40af. Clean vector style, no text, minimal design, suitable for web use as a category icon. White laptop on blue background." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 9. Medical industry icon ==="
$PY $GEN "A modern flat design icon for medical and healthcare industry. A stylized medical cross or stethoscope on a circular blue gradient background from #2563EB to #1e40af. Clean vector style, no text, minimal design, suitable for web use as a category icon. White medical symbol on blue background." --resolution 1K --aspect 1:1 --output $OUT

echo "=== 10. Sole proprietor icon ==="
$PY $GEN "A modern flat design icon for individual business owners and sole proprietors. A stylized person with a briefcase on a circular blue gradient background from #2563EB to #1e40af. Clean vector style, no text, minimal design, suitable for web use as a category icon. White silhouette on blue background." --resolution 1K --aspect 1:1 --output $OUT

echo "=== All done ==="
ls -lht $OUT/*.jpg $OUT/*.png 2>/dev/null | head -15
