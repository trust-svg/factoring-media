# Gotchas運用ルール化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 既存 `feedback_*.md` メモリシステムを Gotchas 公式運用に格上げし、scope 付き frontmatter と `/gotcha` slash command で「同じ指摘を2度受けない」体質を実装する。

**Architecture:** 既存の memory ディレクトリ・ファイル構造には手を入れず、(1) frontmatter スキーマを SCHEMA.md で定義、(2) CLAUDE.md に追記トリガー規約を追加、(3) `/gotcha` slash command でセーフティ提供、の3点を Phase 1 として段階導入する。既存49ファイルへの scope 付与は月次棚卸し（spec #1）で段階消化。

**Tech Stack:** Markdown (Gotcha本体・SCHEMA・CLAUDE.md), Claude Code slash commands (`~/.claude/commands/*.md`), 既存 memory システム (`~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/`)

**Spec:** [`docs/superpowers/specs/2026-05-14-gotchas-rule-design.md`](../specs/2026-05-14-gotchas-rule-design.md)

---

## File Structure

| ファイル | 役割 | 状態 |
|---------|------|------|
| `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/SCHEMA.md` | frontmatter スキーマ定義 (新Gotchaが従う仕様の単一情報源) | 新規作成 |
| `~/.claude/CLAUDE.md` | グローバル規約。Gotcha追記トリガー節を追加 | 既存に追記 |
| `~/.claude/commands/gotcha.md` | `/gotcha` slash command 実装 | 新規作成 |
| `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/` | 廃止Gotcha格納先（gitkeep含む） | 新規ディレクトリ |

---

### Task 1: memory/SCHEMA.md を作成（frontmatter 仕様の単一情報源）

**Files:**
- Create: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/SCHEMA.md`

- [ ] **Step 1: SCHEMA.md を作成**

以下の内容で Write:

```markdown
# Memory frontmatter Schema (Gotchas)

このディレクトリ配下の `feedback_*.md` (=Gotchas) は、以下の frontmatter スキーマに従う。
新規 Gotcha は本スキーマで作成、既存49ファイルは月次棚卸しで段階的に移行。

## Required fields

```yaml
---
name: <人間可読の短いタイトル>
description: <一行説明・MEMORY.md のポインタにも転記>
type: feedback
scope: workspace | skill:<name> | product:<name>
---
```

## Optional fields

```yaml
trigger_count: 1                # 同じ系統の指摘で +1
last_confirmed: 2026-05-14      # このGotchaが「まだ有効」と最後に確認された日
deprecated: false               # true なら月次棚卸しで archive 候補
```

## scope 値の使い分け

| 値 | 意味 | 例 |
|---|---|---|
| `workspace` | 横断 (既定)。あらゆる作業で参照 | `feedback_github_push.md` |
| `skill:<name>` | 特定スキル発動時に重み付け参照 | `feedback_note_publish.md` → `scope: skill:note-auto` |
| `product:<name>` | 特定プロダクト作業時 | `feedback_ai_uranai_deploy_rebuild.md` → `scope: product:ai-uranai` |

迷ったら `workspace` (広い方)。後から狭められる。

## trigger_count 更新ルール

既存Gotcha に新規ケース追記時:
1. frontmatter `trigger_count` を +1
2. `last_confirmed` を今日の日付に更新
3. 本文に日付スタンプ付きで新規ケース追記

## deprecated とアーカイブ

- 廃止前提が確定したら `deprecated: true` に変更
- 月次棚卸し (spec #1) で `.archive/YYYY-MM/<item>/` への移動を提示
- 移動先構造: `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/2026-05/feedback_line_deprecated/feedback_line_deprecated.md`
- MEMORY.md のポインタは archive 時に削除

## 関連 spec

- [`docs/superpowers/specs/2026-05-14-gotchas-rule-design.md`](../../../../Claude-Workspace/docs/superpowers/specs/2026-05-14-gotchas-rule-design.md)
- [`docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md`](../../../../Claude-Workspace/docs/superpowers/specs/2026-05-14-monthly-cleanup-ritual-design.md)
```

- [ ] **Step 2: 内容を目視確認**

Run: `wc -l /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/SCHEMA.md`
Expected: 50-70行程度

- [ ] **Step 3: Commit**

```bash
git -C /Users/Mac_air/.claude add projects/-Users-Mac-air-Claude-Workspace/memory/SCHEMA.md
git -C /Users/Mac_air/.claude commit -m "feat(memory): add Gotchas frontmatter SCHEMA.md (spec #2)"
```

注: `~/.claude` が git 管理外の場合は commit step をスキップ。Workspace 側の spec が単一情報源として残る。

---

### Task 2: ~/.claude/CLAUDE.md に「Gotcha追記トリガー」セクション追加

**Files:**
- Modify: `/Users/Mac_air/.claude/CLAUDE.md`

- [ ] **Step 1: 既存 CLAUDE.md の末尾構造を確認**

Run: `tail -30 /Users/Mac_air/.claude/CLAUDE.md`
Expected: "通知ルート" セクションあたりが末尾。Gotcha関連 section がまだ無いことを確認。

- [ ] **Step 2: 末尾に新セクション追加（Edit ツール使用）**

`/Users/Mac_air/.claude/CLAUDE.md` の末尾に以下を追記:

```markdown

## Gotcha追記トリガー（spec #2 / 2026-05-14）

以下が発生したら**Claudeは即 Gotcha 追記または `/gotcha` 提案する**:

| トリガー | 例 | 追記レベル |
|---------|------|----------|
| ユーザーが「これ覚えて」「次回からやめて」と明示 | "次から `git push` 忘れないで" | **即追記** |
| 同じ系統の指摘を2回受けた | 「note投稿で女性キャラ画像忘れた」2回目 | **即追記** |
| 検証で意外な事実が判明 | `sed -i` がbind mountを壊す事象 | **「Gotcha化する？」確認** |
| 不可逆事故の事後 | `--build` 忘れで8日間サイレント未稼働 | **即追記**（最優先） |

### 既存Gotcha更新ルール（必須）

新規ファイル作成より既存追記が望ましい場合:
1. frontmatter `trigger_count` を +1
2. `last_confirmed` を今日の日付に更新
3. 本文に日付スタンプ付きで新規ケース追記

frontmatter スキーマ詳細: `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/SCHEMA.md`

### Gotcha化しないもの

- 一度きりの作業特殊事情（例: 「この案件だけpython3.11」）
- コードに残っている事実（CLAUDE.md不要）
- ephemeral なタスク詳細
```

- [ ] **Step 3: 内容確認**

Run: `wc -l /Users/Mac_air/.claude/CLAUDE.md && grep -n "Gotcha追記トリガー" /Users/Mac_air/.claude/CLAUDE.md`
Expected: 行数増加、grep がヒット

- [ ] **Step 4: Commit**

```bash
git -C /Users/Mac_air/.claude add CLAUDE.md
git -C /Users/Mac_air/.claude commit -m "feat: add Gotcha追記トリガー section to global CLAUDE.md (spec #2)"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 3: /gotcha slash command 実装

**Files:**
- Create: `/Users/Mac_air/.claude/commands/gotcha.md`

- [ ] **Step 1: ~/.claude/commands/ の構造確認**

Run: `ls /Users/Mac_air/.claude/commands/ 2>/dev/null | head -5`
Expected: 既存のslash command（ある場合）。空でもOK、その場合は ディレクトリ作成 `mkdir -p`。

- [ ] **Step 2: gotcha.md を作成（Write ツール）**

以下の内容で `/Users/Mac_air/.claude/commands/gotcha.md` を作成:

```markdown
---
description: Gotcha を即時メモリに追加（spec #2）
---

ユーザーが以下のGotchaを memory に追加するよう指示しました。

引数: $ARGUMENTS

以下を順に実行してください:

## 1. 引数パース

引数の形式: `[scope=<scope>] <本文>`

- `scope=workspace` / `scope=skill:<name>` / `scope=product:<name>` を抽出
- 省略時は `scope: workspace` 既定
- 残りを本文として扱う

例:
- `/gotcha scope=skill:note-auto note投稿のヘッダー画像は必ず女性キャラ` → scope=skill:note-auto, 本文="note投稿のヘッダー画像は必ず女性キャラ"
- `/gotcha git push を忘れがち` → scope=workspace, 本文="git push を忘れがち"

## 2. 既存Gotchaとの重複チェック

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_*.md` の一覧を取得。
本文と似た既存Gotchaがあれば、**新規作成せず既存に追記**することを提案して停止。

## 3. ファイル名（slug）生成

- 本文から英数字スラグを生成（小文字、ハイフン区切り、20文字以内）
- 例: "note投稿のヘッダー画像は必ず女性キャラ" → `feedback_note_female_character_header.md`
- 既存ファイル名と衝突する場合は数字サフィックス（`_2`, `_3`）

## 4. ファイル生成（Write ツール）

保存先: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_<slug>.md`

frontmatter:
```yaml
---
name: <本文を要約した1行タイトル>
description: <本文を一行に圧縮>
type: feedback
scope: <パース結果>
trigger_count: 1
last_confirmed: <今日の日付 YYYY-MM-DD>
---
```

本文セクション:
```markdown
## <本文タイトル>

<引数本文>

### 履歴

- YYYY-MM-DD: 初回登録
```

## 5. MEMORY.md 更新

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md` の `## Feedback` セクションに1行ポインタを追加:

```markdown
- [<タイトル>](feedback_<slug>.md) — <description>
```

frontmatter スキーマ詳細: `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/SCHEMA.md`

## 6. 確認メッセージ

以下を出力して終了:
- 作成ファイルパス
- scope と trigger_count
- MEMORY.md 更新箇所（diff 1行）
```

- [ ] **Step 3: slash command が認識されるか確認**

新規 Claude Code セッションを開く、または `/help` で `/gotcha` が一覧に出るか確認。
（slash command は再起動なしで認識されるはずだが、出ない場合は Claude Code 再起動が必要）

- [ ] **Step 4: Commit**

```bash
git -C /Users/Mac_air/.claude add commands/gotcha.md
git -C /Users/Mac_air/.claude commit -m "feat: add /gotcha slash command (spec #2)"
```

注: `~/.claude` が git 管理外ならスキップ。

---

### Task 4: .archive/ ディレクトリ準備

**Files:**
- Create: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/.gitkeep`

- [ ] **Step 1: ディレクトリ作成**

```bash
mkdir -p /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive
touch /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/.gitkeep
```

- [ ] **Step 2: 確認**

Run: `ls -la /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/`
Expected: `.gitkeep` だけが存在

- [ ] **Step 3: Commit（任意）**

```bash
git -C /Users/Mac_air/.claude add projects/-Users-Mac-air-Claude-Workspace/memory/.archive/.gitkeep
git -C /Users/Mac_air/.claude commit -m "chore: prepare memory/.archive/ for deprecated Gotchas (spec #2)"
```

---

### Task 5: 動作確認 — 既存 feedback_line_deprecated.md を archive 移動でリハーサル

**Files:**
- Move: `/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_line_deprecated.md` → `.archive/2026-05/feedback_line_deprecated/`

- [ ] **Step 1: 月フォルダ作成**

```bash
mkdir -p /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/2026-05/feedback_line_deprecated
```

- [ ] **Step 2: 移動**

```bash
mv /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/feedback_line_deprecated.md \
   /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/2026-05/feedback_line_deprecated/feedback_line_deprecated.md
```

- [ ] **Step 3: MEMORY.md のポインタ削除**

`/Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md` から `feedback_line_deprecated` への参照行を Edit ツールで削除。

具体的な対象行（既存 MEMORY.md 内）:
```
旧情報（参照のみ・使用禁止）: チャネルID `2009394928` / Bot `@047diogm`
```
の上にある `feedback_line_deprecated.md` リンク行を削除（line 直接参照: 該当箇所を grep で先に確認）

```bash
grep -n "feedback_line_deprecated" /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md
```

- [ ] **Step 4: 行数確認（MEMORY.md が縮んだか）**

Run: `wc -l /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/MEMORY.md`
Expected: 移動前より1-2行短い

- [ ] **Step 5: 復元テスト**

```bash
# 復元が1コマンドでできることを確認
ls /Users/Mac_air/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/.archive/2026-05/feedback_line_deprecated/
```
Expected: ファイルが存在する。`mv` で元に戻せる状態。

- [ ] **Step 6: Commit（任意）**

`~/.claude` が git 管理ならコミット、そうでなければスキップ。

---

## 受け入れ基準の検証

spec #2 セクション8の受け入れ基準と対応:

- [ ] Task 2 で `~/.claude/CLAUDE.md` に「Gotcha追記トリガー」明文化済み
- [ ] Task 3 で `/gotcha` slash command が動作
- [ ] Task 3 + 後続セッションで新規 Gotcha 1件を `/gotcha` 経由で作成・確認できる
- [ ] Task 1 で frontmatter スキーマが memory/SCHEMA.md に記載されている
- [ ] spec #1 のプランで「deprecated Gotcha検出」が実装される（このプラン外、依存先）

---

## Self-Review Checklist（plan作成者用）

- [x] spec の全セクション（1-9）がタスクにマッピングされているか確認済み
- [x] 既存49ファイル移行は Phase 2 として spec で除外 → このプランも対応せず
- [x] Phase 3（重み付けロード）は YAGNI でスコープ外
- [x] memory archive 構造 `.archive/YYYY-MM/<item>/` が spec #1 と統一
