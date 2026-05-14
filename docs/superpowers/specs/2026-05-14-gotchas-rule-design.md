# Gotchas運用ルール化 — Design Spec

**Date**: 2026-05-14
**Author**: Hiro + Claude
**Status**: Draft (要レビュー)
**Origin**: note記事「育てるClaude Codeから"勝手に育つClaude Code"へ」の②代謝

---

## 1. 目的

既存 `feedback_*.md` メモリシステムを「**Gotchas運用**」として強化・公式化する。
人間のフィードバック1回で、関連するスキル/作業領域が永久に賢くなる仕組みを担保する。

### 解決する課題

- 「同じ指摘を2回受けたらCLAUDE.mdに追記」ルールはあるが、**徹底されているかの検証手段がない**
- feedback_*.md にスコープ情報がなく、「いつ・どこで」効くべきかが曖昧
- ユーザーが「これ覚えて」と言った時の追記行為が、Claudeの判断任せで漏れがある
- 廃止された前提（例: `feedback_line_deprecated.md`）が残り続けて文脈を汚染する

### 非目標（やらないこと）

- UserPromptSubmit hook によるパターン検出（誤検出多・YAGNI、Phase 2 据え置き）
- ngram類似度ベースの「同じ指摘」自動検出（同上）
- 既存49ファイルへの一括 scope frontmatter 追加（段階的に新規Gotchaから運用）

---

## 2. システム構成

### 2.1 配置の継承

現行の memory システムをそのまま使う:
```
~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/
├── MEMORY.md          # インデックス（自動ロード）
├── feedback_*.md      # 各Gotcha本体
├── project_*.md       # プロジェクト状態（Gotchaとは別管理）
├── ai-uranai.md       # 個別プロダクト詳細（Gotchaとは別管理）
└── ...
```

**変更なし**。1Gotcha = 1ファイル + MEMORY.md にポインタ1行、を継続。

### 2.2 frontmatter 拡張（新Gotchaから適用）

既存 frontmatter:
```yaml
---
name: <名前>
description: <一行説明>
type: feedback
---
```

拡張 frontmatter:
```yaml
---
name: <名前>
description: <一行説明>
type: feedback
scope: workspace                # 必須: workspace / skill:<name> / product:<name>
trigger_count: 1                # 任意: 何回指摘されたか（同じ系統の追加で +1）
last_confirmed: 2026-05-14      # 任意: 最後にこのGotchaが「まだ有効」と確認された日
deprecated: false               # 任意: 廃止フラグ（trueなら月次棚卸しで削除候補）
---
```

### 2.3 scope 設計

| scope値 | 意味 | 例 |
|---------|------|-----|
| `workspace` | 横断（既定）。あらゆる作業で参照 | `feedback_github_push.md`（毎回push必須） |
| `skill:<name>` | 特定スキル発動時に重み付け参照 | `feedback_note_publish.md` → `scope: skill:note-auto` |
| `product:<name>` | 特定プロダクトディレクトリ作業時 | `feedback_ai_uranai_deploy_rebuild.md` → `scope: product:ai-uranai` |

**将来の活用**:
- スキル発動時、関連 scope の Gotcha を冒頭でハイライト表示
- 作業ディレクトリ判定で product scope の Gotcha を優先表示

**Phase 1 では**: scope を**書くだけ**（ロード時の重み付け処理は YAGNI、Phase 2）。

---

## 3. 追記トリガー（CLAUDE.md 規約）

### 3.1 必須追記イベント

以下が発生した時、**Claudeは即 Gotcha 追記する**（or `/gotcha` 提案する）:

| トリガー | 例 | 追記レベル |
|---------|------|----------|
| ユーザーが「これ覚えて」「次回からやめて」と明示 | "次から `git push` 忘れないで" | **即追記** |
| 同じ系統の指摘を2回受けた（CLAUDE.md既存ルール） | 「note投稿で女性キャラ画像使うのを忘れた」が2回目 | **即追記** |
| 検証で意外な事実が判明 | `sed -i` がbind mountを壊す事象を発見 | **「Gotcha化する？」確認** |
| 不可逆事故の事後 | `--build` 忘れで8日間サイレント未稼働 | **即追記**（最優先） |

### 3.2 既存Gotchaの更新ルール

新規でなく**既存Gotchaに追記**で済む場合:
- frontmatter `trigger_count: N+1` にインクリメント
- 本文に新規ケースを追記（日付スタンプ付き）
- 例: `feedback_image_generation_japan.md` は 2026-04-07 のロゴ追記が good example

### 3.3 Gotcha化しないもの

- 一度きりの作業特殊事情（例: 「この案件だけpython3.11使う」）
- コードに残っている事実（CLAUDE.md不要、コードで自明）
- ephemeral なタスク詳細（進行中の作業状態）

---

## 4. `/gotcha` slash command

### 4.1 用途

Claudeが追記し忘れた時、または Hiro が能動的に Gotcha 化したい時のセーフティ。

### 4.2 文法

```
/gotcha [scope=<scope>] <内容>
```

- `scope=` 省略時は `workspace` 既定
- 内容は1-3文の簡潔記述
- 自動で `feedback_<auto_slug>.md` に保存 + MEMORY.md に1行追加

### 4.3 実装イメージ

`~/.claude/commands/gotcha.md`:
```markdown
---
description: Gotcha を即時メモリに追加
---

ユーザーが以下のGotchaを追加するよう指示しました。

引数: $ARGUMENTS

以下を実施:
1. 引数から scope と本文を抽出（`scope=foo 本文` 形式）
2. ファイル名 `feedback_<slug>.md` を生成（slugは内容から自動）
3. frontmatter付きでmemoryディレクトリに保存:
   - name, description, type=feedback, scope, trigger_count=1, last_confirmed=今日
4. MEMORY.md に 1行ポインタ追加
5. 確認メッセージ出力
```

### 4.4 例

```bash
/gotcha scope=skill:note-auto note投稿のヘッダー画像は必ず女性キャラ（hero-teleop系）使う
```
→ `feedback_note_female_character_header.md` を生成 + MEMORY.md 追記

---

## 5. 腐敗管理（spec #1 と連動）

### 5.1 廃止検出

月次棚卸し（spec #1）で以下を追加検査:
- frontmatter `deprecated: true` のGotcha → 削除候補
- 本文に「廃止」「停止」「使用禁止」キーワードがあるGotcha → 要確認
- 180日以上 `last_confirmed` が更新されていないGotcha → 鮮度警告

### 5.2 既存 deprecated ファイルの扱い

現在 deprecated 含むファイル（例: `feedback_line_deprecated.md`）:
- 月次棚卸しで「**archive/ に移動推奨**」と提示
- 完全削除はしない（履歴として残す価値あり）
- 移動先: `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/YYYY-MM/<item>/`
  - **月フォルダ構造**（spec #1 の skills `.archive` と統一）
  - 例: `memory/.archive/2026-05/feedback_line_deprecated/feedback_line_deprecated.md`
  - 1アイテム = 1サブディレクトリ（複数ファイル束ねたい場合に便利）
- 復元手順:
  ```bash
  mv ~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/2026-05/<item>/<file>.md \
     ~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/<file>.md
  ```
- MEMORY.md のポインタも archive 移動時に**削除**（復元時に追記）

---

## 6. 実装フェーズ

### Phase 1: 規約整備（軽量、即実装可）

- [ ] `~/.claude/CLAUDE.md` に「Gotcha追記トリガー」セクション追加
- [ ] `~/.claude/commands/gotcha.md` 作成
- [ ] frontmatter テンプレ仕様の README を memory/ に配置
- [ ] **新規 Gotcha から** scope frontmatter 採用開始

### Phase 2: 既存ファイル段階移行（時間ある時）

- [ ] 既存49ファイルに scope を順次付与（月次棚卸し時に1ヶ月数件ペース）
- [ ] `last_confirmed` を初期値設定

### Phase 3: 重み付けロード（YAGNI、要否判断）

- [ ] SessionStart hook で作業ディレクトリ判定 → 関連scope Gotchaをハイライト
- [ ] Skill発動時に scope-matched Gotcha を優先表示

**Phase 3 は「Phase 1+2 で運用してみて不満が出たら」**。先回りしない。

---

## 7. Gotchas / リスク

### リスク1: scope の判定が曖昧で書き手によってブレる

例: 「VPS全体」と「特定プロダクト」のどちらに分類すべきか迷う事例。

**対策**:
- 迷ったら `workspace`（広い方）を選ぶ。後から狭められる。
- 月次棚卸しで「scope=workspace で件数が多すぎる Gotcha」を確認し、適切なscope に分割提案

### リスク2: trigger_count を更新し忘れる

人間が手で書く必要があるため、忘れがち。

**対策**:
- Claudeが既存Gotchaに追記する時、frontmatter更新も**必須**として CLAUDE.md 規約に書く
- 月次棚卸しで「trigger_count=1 で 6ヶ月以上経過」のGotchaは鮮度確認対象

### リスク3: /gotcha コマンドの slug 生成が雑

似た名前のファイルが乱立する可能性。

**対策**:
- 既存 feedback_*.md 一覧を Claude が確認してから新規slug決定
- 既存と統合可能なら追記提案

---

## 8. 受け入れ基準

- [ ] `~/.claude/CLAUDE.md` に「Gotcha追記トリガー」明文化済み
- [ ] `/gotcha` slash command が動作（引数解析 → memory ファイル生成 → MEMORY.md 更新）
- [ ] 新規 Gotcha 1件を `/gotcha` 経由で作成・確認できる
- [ ] frontmatter スキーマが memory/ 内のREADMEに記載されている
- [ ] 月次棚卸し（spec #1）が deprecated Gotcha を検出できる

---

## 9. オープン質問

- frontmatter README は `memory/README.md` でよい？ それとも CLAUDE.md に直書き？
  → 暫定: `memory/SCHEMA.md` を作る（CLAUDE.md は肥大化させない）
