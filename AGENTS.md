# AGENTS.md

## 基本方針

このワークスペースにおけるCodexの役割は、以下のいずれかとする。

1. `products/codex-labs/` 内での本番開発・運用
2. 既存プロダクトへのレビュー・提案・差分確認
3. Claude Codeとは別案の実装検証

Codexは実装可能なエージェントだが、無制限に既存プロダクトを編集してはいけない。

## 作業範囲

Codexが自由に編集してよい範囲は、原則として以下のみ。

- `products/codex-labs/`

既存プロダクトを編集する場合は、Hiroから明示的に対象ディレクトリ・目的・ブランチ名を指定された場合のみ行う。

本番利用するプロダクトを `products/codex-labs/` 内に作成する場合は、以下を必ず整備する。

- `README.md`
- 起動方法
- 環境変数一覧（値ではなく変数名・用途・設定例のみ）
- テスト方法
- デプロイまたは運用手順
- 既知の制約・注意点

## Gitルール

- mainブランチを直接編集しない。
- mainブランチへ直接pushしない。
- 作業時は必ず専用ブランチを作成する。
- ブランチ名は以下の形式を使う。
  - `feature/codex-*`
  - `fix/codex-*`
  - `chore/codex-*`
- 大きな変更を行う前に、まず変更方針を提示する。
- 既存のClaude Code / d-managerの作業を上書きしない。

## セキュリティルール

以下のファイル・情報は読まない、編集しない、出力しない。

- `.env`
- APIキー
- アクセストークン
- 認証情報
- 秘密鍵
- 個人情報を含むファイル

必要な環境変数がある場合は、値を推測せず、変数名・用途・設定例のみを `README.md` または `.env.example` に記載する。`.env.example` に実際の秘密情報を入れない。

## 開発ルール

- まずREADME.mdまたは既存ドキュメントを確認する。
- 新規プロジェクトでは、最初にREADME.mdと簡単な設計方針を作成する。
- 複雑な実装より、シンプルで保守しやすい実装を優先する。
- 可能な範囲でテストを追加する。
- 作業後に実行可能な確認コマンドを実行する。
  - test
  - lint
  - typecheck
  - build

実行できない場合は、その理由を報告する。

## 完了報告

作業完了時は、以下を報告する。

- 実装した内容
- 変更したファイル
- 実行したコマンド
- テスト結果
- 残っている課題

## 共通ワークスペース（Claude Code と共有）

このワークスペースは Claude Code と Codex の共通作業領域。スキルと横断事実を共有するが、
作業範囲・Gitルール・セキュリティルール（上記）は変わらない。

### 共通スキル

共通スキルの正本は `_shared-ai/skills/`（git追跡）。各スキルは `~/.codex/skills/<name>` に
symlink 済みで、Codex から認識・利用できる。

- `skill-quality-checker` — 新規スキルの作成・編集後に8項目で品質チェック
- `mcp-audit` — MCPサーバの棚卸し（年1回 or 消費過大時）
- `factcheck-ai-cross` — 高コストな事実（法律条文・事業数値・統計・API仕様）を
  Claude↔Codex の2系統で独立検証
- `codex-handoff` — 設計→実装の引き継ぎテンプレート

スキルの実体は `_shared-ai/skills/` のみ。symlink 先（`~/.codex/skills/`）を直接編集せず、
正本を編集する。スキルを追加したら `bash _shared-ai/setup-symlinks.sh` で symlink を再生成する。
置き場所判断: 片方のツール専用→ `~/.codex/skills/`(L1) / 両ツール共通→ `_shared-ai/skills/`(L2)
/ 1プロジェクト限定→ そのプロジェクトの `.claude/skills/`(L3)。frontmatter は name/description のみ。

### 横断事実（SSoT）の参照先

アカウントID・契約・自動実行ジョブなどの横断情報は、以下が正本。**Codex 側で複製・推測せず参照する**。

- 広告アカウント: `~/Obsidian/context/ad-accounts.md`
- 契約 / サブスク: `~/Obsidian/context/subscriptions.md`
- 自動実行ジョブ（cron / launchd / GitHub Actions）: `~/Obsidian/context/cron-inventory.md`

`~/Obsidian/` への読み取り権限が無い場合は、内容を推測せず Hiro に確認する。

恒常的な不変則（詳細は上記SSoT・CLAUDE.md・memory が正本）:

- 通知は Telegram / Discord を使う（LINE は全廃止・新規コードでの利用禁止）
- 内部時刻は JST（Asia/Tokyo）統一。naive datetime と UTC/JST 文字列の比較は禁止
- 破壊的・不可逆な操作（force push, reset --hard, 本番VPS変更, DB drop, 外部API本番送信）は
  実行前に Hiro へ確認する
