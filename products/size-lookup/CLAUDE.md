# Size Lookup - Chrome Extension

型番を入力すると、Claude AI が商品サイズを推定し、壊れやすさを考慮した海外発送用梱包サイズを算出するChrome拡張機能。

## Architecture

- **Chrome Extension (Manifest V3)** — バックエンドサーバー不要
- **Claude API** 直接呼び出し（`anthropic-dangerous-direct-browser-access` ヘッダー使用）
- API キーは `chrome.storage.sync` に保存

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Chrome 拡張マニフェスト (MV3) |
| `popup.html/css/js` | メインUI・ロジック |
| `options.html/css/js` | 設定画面（APIキー・モデル選択）|
| `icons/` | 拡張アイコン（PNG必要、SVGはプレースホルダー）|

## Setup

1. `chrome://extensions/` を開く
2. 「デベロッパーモード」を有効化
3. 「パッケージ化されていない拡張機能を読み込む」→ このディレクトリを選択
4. 拡張アイコン → 設定 → Claude API キーを入力

## Icon Generation

PNGアイコンが必要な場合、SVGから変換:
```bash
# macOS (rsvg-convert)
brew install librsvg
for size in 16 48 128; do
  rsvg-convert -w $size -h $size icons/icon${size}.svg > icons/icon${size}.png
done
```

アイコンなしで開発する場合は `manifest.json` から `icons` ブロックを削除。

## Packaging Logic

壊れやすさレベル（1-5）に応じた緩衝材厚さ:
- Level 1 (頑丈): 各辺 +2cm
- Level 2 (普通): 各辺 +3cm
- Level 3 (やや壊れやすい): 各辺 +5cm
- Level 4 (壊れやすい): 各辺 +7cm
- Level 5 (非常に壊れやすい): 各辺 +10cm + 二重箱

容積重量 = (L × W × H) / 5000
