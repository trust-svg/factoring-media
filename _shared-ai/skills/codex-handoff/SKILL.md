---
name: codex-handoff
description: Use when handing a task from a design/decision AI (Claude) to an implementation AI (Codex), or vice versa. Produces a self-contained handoff brief with goal, constraints, acceptance criteria, reference files, and required completion-report format so the receiving agent needs no prior conversation context.
---

# Codex Handoff

設計・意思決定（主に Claude）から実装・検証（主に Codex）へ仕事を渡すときの引き継ぎテンプレート。受け取る側は会話履歴を持たない前提で、これ1枚で着手できる粒度にする。逆方向（Codex→Claude）でも同形式。

## いつ使うか

- Claude で方針を固め、実装を Codex に任せるとき
- 別案実装の検証を Codex に依頼するとき
- 受け取った成果物のレビューを別系統に回すとき

## 前提（このリポジトリの規律）

- Codex の編集可能範囲は原則 `products/codex-labs/` のみ。既存プロダクトを触らせる場合は対象ディレクトリ・目的・ブランチ名を明示指定する（`AGENTS.md` 準拠）
- main 直接編集・push 禁止。ブランチは `feature/codex-*` / `fix/codex-*` / `chore/codex-*`
- `.env`・APIキー・トークン・認証情報・秘密鍵は読ませない・書かせない・出力させない

## 引き継ぎ5要素

ハンドオフは必ず次の5項目を埋める。空欄を残さない（埋まらない＝渡す準備ができていない）。

1. **目的（Goal）** — 何を達成したいか。なぜやるか（背景）を1〜2行。
2. **制約（Constraints）** — 編集してよい範囲・触ってはいけない範囲、使用言語/バージョン、依存追加の可否、ブランチ名、セキュリティ境界。
3. **受け入れ基準（Acceptance Criteria）** — 「これが満たされたら完了」を検証可能な形で。テストが通る／特定コマンドの出力／UI挙動など。曖昧語（"いい感じに"）禁止。
4. **参照ファイル（References）** — 読むべきファイルの絶対パス、関連する既存実装、設計メモ。受け手が探さなくて済むように。
5. **完了報告形式（Report Format）** — 何を返してほしいか（変更ファイル一覧・実行したコマンド・テスト結果・残課題）。`AGENTS.md` の完了報告項目に準拠。

## 出力テンプレート

```markdown
# Handoff: <タイトル>  (Claude → Codex)

## 目的
<達成したいこと / 背景>

## 制約
- 編集可: <ディレクトリ>
- 編集不可: <触らない範囲>
- 言語/Ver: <...>  ブランチ: feature/codex-<...>
- セキュリティ: .env/認証情報は読まない・出力しない

## 受け入れ基準
- [ ] <検証可能な条件1>
- [ ] <検証可能な条件2>

## 参照ファイル
- /abs/path/...  — <何のため>

## 完了報告形式
- 変更ファイル一覧 / 実行コマンド / テスト結果 / 残課題
```

渡す前に「受け手が会話履歴ゼロでも着手できるか」を自問する。できないなら要素が足りていない。
