# CLAUDE.md — Workspace Rules for Claude

This file is automatically read by Claude at the start of every session.

## Workspace Overview

This workspace contains 4 top-level directories.
They are NOT related unless explicitly stated.

| Directory | Purpose |
|---|---|
| `.company/` | AI組織本部（部門・戦略・秘書・知識ベース） |
| `products/` | 全プロダクト・ツール・クライアント案件 |
| `marketing/` | 広告・マーケ素材（Google/Meta広告、SNS） |
| `resources/` | ドキュメント・参考資料・素材 |

## Mandatory Rules

1. **Always work ONLY in the directory explicitly specified by the user.**
2. **Do NOT mix logic, content, or context across directories.**
3. `products/clients/` must remain strictly isolated — no reuse without abstraction.
4. **If no target directory is specified, ask before proceeding.**

## Directory-Specific Notes

### products/
- `ebay-agent/` — FastAPI + Claude tool_use + eBay API
- `d-manager/` — Discord AI組織Bot
- `messecoach/` (ZINQ) — LINE Bot AIコーチ
- `factoring-media/` — ファクセルメディアサイト
- `threads-auto/` — Threads自動運用
- `lp-templates/` — LPテンプレート（旧reusable/）
- `clients/` — クライアント案件

### resources/
- `docs/` — 仕様書・設計プラン
- `references/` — 参考資料・スクリーンショット・データファイル
- `books/` — 参考書籍PDF
- `images/` — 画像素材

## Code Style Preferences

- Python: follow PEP8, use type hints where practical
- Use `.env` files for secrets (never hardcode credentials)
- Each product manages its own `requirements.txt`

## What NOT to Do

- Never commit `.env` files
- Never mix client data into `products/` general directories
- Never create files outside the specified target directory without asking

## Working Process Rules（作業プロセス規律）

### 自己検証ルール（完了報告の前に必須）
- **コード変更後は、対象プロダクトのテスト or スモーク確認を実行し、出力を貼ってから「完了」と報告すること**
- 確認手段が無い／実行できない場合は、その旨を明示して報告（黙って完了にしない）
- 検証手段の優先順位:
  1. 該当プロダクトの `pytest` / `npm test` 等のテストコマンド
  2. 起動確認（`python main.py` / `docker compose up` で正常起動）
  3. UI変更ならスクリーンショット or curl での疎通確認
  4. ログ出力の目視確認
- 検証コマンドが重い場合（VPS本番デプロイ等）は、ユーザーに確認手段を相談する

### 同じミスは繰り返さない
- **同じ指摘を2回受けたら、CLAUDE.md or `~/.claude/CLAUDE.md` に追記すること**
- 局所的な事情（特定プロダクトのみ）なら、そのプロダクト配下に `CLAUDE.md` を置く
- 全体ルールに昇格させる前に、適用範囲（どのディレクトリ/どの状況）を明示する
- 不要になったルールは消す（CLAUDE.mdが膨らむと逆効果）

### 不可逆な操作の前に確認
- 破壊的・不可逆な操作（force push, reset --hard, 本番VPSへの変更, DB drop, 外部API本番送信）は、毎回ユーザーに確認すること
- 「過去に許可されたから」を理由に省略しない
- ※ 絶対に止めるべきものはhooksで強制（Phase 3で整備）

## Temporary Files / Screenshots

- 一時ファイル（スクショ・デバッグ用JSON・動作確認ログなど）は **Workspace直下に置かない**
- 保存先の優先順位:
  1. `$TMPDIR`（セッション後に消えて良いもの）
  2. `tmp/` 配下（`tmp/screenshots/YYYY-MM-DD/` など日付別サブディレクトリを推奨）
  3. 対象プロダクト配下の `tmp/` or `_scratch/`
- Playwright MCP / ブラウザ操作のスクショは **必ず絶対パスで上記いずれかに保存**
- ルート直下に `*.png` / `*.json` / `*.log` を作らないこと（`.gitignore` にも追記済み）

## Daily Dev Journal (Obsidian)

会話の最後（ユーザーが作業を終えようとしている時）に、以下をリマインドする:

> 「今日の開発日誌、Obsidianに付けますか？」

- 保存先: `/Users/Mac_air/Obsidian/Daily/YYYY-MM-DD.md`
- git log + 未コミット変更から自動生成
- テンプレート: Tasks / Dev Log / Tomorrow Next / Reflection
