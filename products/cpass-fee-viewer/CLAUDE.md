# CPASS Fee Viewer - Chrome Extension

## Overview
SpeedPAKセラーポータル (`ebay-jp.orangeconnex.com`) の取引明細料金内訳を一括取得・集計するChrome拡張機能。

## Tech Stack
- Chrome Extension Manifest V3
- Vanilla JavaScript (no framework)
- Japanese UI

## Architecture
- `content/interceptor.js` — ページのメインワールドでfetch/XHRフック（API自動検出）
- `content/content.js` — コンテンツスクリプト（UI注入、データ収集ループ、DOMフォールバック）
- `content/ui.js` — ページ内注入UI
- `background/service-worker.js` — メッセージング、ストレージ管理
- `dashboard/` — 結果表示ダッシュボード（新規タブ）
- `lib/` — 共通ライブラリ

## Key Patterns
- APIインターセプトはCustomEvent経由でコンテンツスクリプトと通信
- データ収集ループはコンテンツスクリプト側で実行（MV3サービスワーカーのライフサイクル制約回避）
- chrome.storage.local でデータ永続化
