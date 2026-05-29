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

## AIツールごとの役割と権限

このワークスペースでは、d-managerを司令塔として扱う。

- Claude Code / Larry は、既存プロダクトのメイン実装担当とする。
- Codex は、原則として `products/codex-labs/` 内での開発・運用を担当する（本番利用を含む）。
- Codex が既存プロダクトを編集する場合は、明示的な指示がある場合のみとする。
- Gemini は、原則として読み取り・分析・仕様整理専用とし、ファイル編集は行わない。
- Hermes は、外部情報収集・X/Grok検索・調査補助として扱う。
- mainブランチへの直接編集・直接pushは禁止する。
- `.env`、APIキー、認証情報、トークン類は読まない・編集しない・出力しない。

## SSoT Map（横断台帳の参照先）

「広告アカウントID」「サブスク契約」「自動実行ジョブ」などの **横断情報** は、ここから探す。
個別プロダクトの memory より優先。アカウント不明・契約状況不明な時は **最初にこの3つを見る**。

| 種別 | 場所 | 内容 |
|------|------|------|
| 広告アカウント | `~/Obsidian/context/ad-accounts.md` | Meta/Google/LinkedIn/TikTok/X 全アカウントID |
| 契約/サブスク | `~/Obsidian/context/subscriptions.md` | AI/API・インフラ・SaaS・広告予算・ASP |
| 自動実行ジョブ | `~/Obsidian/context/cron-inventory.md` | VPS cron + launchd + GitHub Actions + CronCreate |

更新ルール: 該当ファイルを上書き、`last_confirmed` を更新。詳細スキーマと flow/stock 設計は `~/Claude-Workspace/docs/superpowers/specs/2026-05-14-ssot-flow-stock-design.md`。

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

### 暗黙の了解は通用しない（AI運用規律）
- AIエージェントには「常識でわかる」を前提にしない。指示は「やってよいこと／やってはいけないこと／迷ったときの判断基準」を明示書き出し
- 特に新しいskill・subagent・部門エージェントを定義するときは、責務（やる）と非責務（やらない）の両方を書く
- 過去に「Obsidianのinboxを勝手に消した」のような事故が他環境で起きている。`.company/` 配下と各エージェント定義ではやってはいけないこと（破壊的操作）を毎回明文化する

### サイレント故障対策
- AIエージェントは設定不整合や接続切れでも「完了しました」とエラーを出さず動き続ける
- 重要パイプ（cron、scheduler.py、bot通知、APIキー）は**月1で end-to-end 疎通確認**を実施
- 「動いてます」報告だけでは足りず、最終出力（Discord通知到達／ファイル更新／DB書き込み）を実物で確認する
- 具体運用は d-manager 夜間QA（深夜サイト疎通＋朝ブリーフィング合否表示）に任せる

### 組織化の真の利得は「未着手仕事の解放」
- AI組織化の本質は時間節約ではなく、**人間ひとりでは絶対やらない／割に合わない仕事**を回せるようにすること（夜間QA、リファクタ、未読の整理、定期監査など）
- 新規Cron/夜間ジョブを追加するときの判定基準: 「Hiroひとりでは継続不能か」がYesのときのみ採用
- 「時間が浮きそうだから」という理由だけでは追加しない（メンテ負担とトラブルの方が大きくなる）

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

## 共通スキル領域・棚卸し（Claude Code & Codex 共有）

L2共通スキルは `_shared-ai/skills/`（単一実体・git追跡）。symlinkで Claude(`~/.claude/skills/<name>`)・Codex(`~/.codex/skills/<name>` 公式パス + `.agents/skills/<name>` 補助) からネイティブ起動。再生成は `bash _shared-ai/setup-symlinks.sh`。`~/.codex/skills` への書き込みは `~/.claude/settings.json` の sandbox `allowWrite` で許可済み（`/Users/Mac_air/.codex/skills` ピンポイント。`~/.codex` 全体は不可）。
- 配置基準: 1ツール→`~/.claude/skills/`(L1) / 両ツール→`_shared-ai/skills/`(L2) / 1プロジェクト→`.claude/skills/`(L3)
- 役割分担: 設計判断→Claude / 実装検証→Codex / 引き継ぎ→`codex-handoff` スキル
- 棚卸し: MCP=月1 or `/context` 5%超→`mcp-audit` / スキル未使用=隔週(手動) / cache=四半期(手動)
- 新スキル作成後は `skill-quality-checker` で8項目チェック。高コストな事実確認は `factcheck-ai-cross`
- 詳細: `_shared-ai/README.md`
