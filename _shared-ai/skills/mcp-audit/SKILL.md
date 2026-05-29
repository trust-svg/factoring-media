---
name: mcp-audit
description: Use to audit installed MCP servers and decide which to keep, replace with a CLI, or remove. Run yearly, or whenever MCP tool definitions consume more than ~5% of the context window (visible via /context), or before adding a new MCP server.
---

# MCP Audit

MCP サーバは便利だが、ツール定義が常時コンテキストを食う。使っていない／CLI で代替できるサーバを定期的に棚卸しして、コンテキスト予算を守る。Claude Code・Codex 両方で同じ判断基準を使う。

## いつ使うか

- 年1回の定期棚卸し
- `/context` で MCP のツール定義が全体の 5% を超えたとき
- 新しい MCP サーバを足す前（本当に MCP が必要かの判断）

## 手順

### 1. 現状の MCP サーバを列挙

- Claude Code: `~/.claude/settings.json` の `enabledPlugins`、プロジェクト直下の `.mcp.json`、`/context` の MCP 行を確認
- Codex: `~/.codex/config.toml` の MCP 設定を確認
- 各サーバについて「サーバ名 / 提供ツール数 / 直近30日で実際に呼んだか」を表にする

### 2. 各サーバを3分類

| 判定 | 条件 | アクション |
|------|------|-----------|
| **KEEP** | 頻繁に使う・CLI 代替が無い／非現実的（例: ブラウザ操作の playwright、会計の freee） | 残す。理由を1行記録 |
| **REPLACE** | 同じことが CLI / API スクリプトで安定して出来る（例: 単純な GET 系 API） | CLI 化手順を書いて MCP を無効化 |
| **REMOVE** | 直近で未使用・導入目的が消えた | 無効化（設定から外す。即削除はせず1サイクル様子見） |

### 3. CLI 代替の判定基準

MCP を CLI へ寄せるべきなのは次のとき:
- 呼び出しが読み取り中心で、決まったエンドポイントを叩くだけ
- 認証がトークン1本で完結する
- レスポンスを自前で整形したい

逆に MCP のままが良いのは: 対話的・状態を持つ・複雑なスキーマ・公式が MCP を推奨している場合。

### 4. 記録

棚卸し結果を残す（KEEP/REPLACE/REMOVE と理由）。横断台帳がある場合は `~/Obsidian/context/` の該当ファイル、無ければこの監査の出力をそのままコミットメッセージか README に残す。

## 出力形式

```
MCP Audit (YYYY-MM-DD)
- <server>: KEEP   — 理由
- <server>: REPLACE — CLI代替: <コマンド/スクリプト案>
- <server>: REMOVE  — 未使用(直近30日0回)
コンテキスト占有: 監査前 xx% → 想定後 yy%
```

破壊的変更（サーバ削除）は実行前にユーザー確認。無効化→1サイクル観察→問題なければ削除、の順。
