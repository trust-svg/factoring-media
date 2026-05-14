# X (Twitter) ポスト取り込みパイプライン — Design Spec

**Date**: 2026-05-14
**Author**: Hiro + Claude
**Status**: Draft (要レビュー)
**Origin**: note記事「育てるClaude Codeから"勝手に育つClaude Code"へ」の①摂取

---

## 1. 目的

Xに流れる Claude Code 関連ノウハウを「即取り込み」する仕組みを作る。
URLを渡すだけで、要約→分類→既存スキル追記/新規スキル草案/context追記まで自動化する。

### 解決する課題

- X で流れる良質なノウハウが「スクショ・ブックマーク」止まりで死蔵される
- 取り込み判断（既存反映 vs 新規スキル化 vs context追記）が曖昧
- 「あとで試そう」と思って試さないループ
- コミュニティ最新情報がリポジトリに継続的に注入されない

### 非目標

- X 全般のリサーチ（spec とは別、`sns-research` skill が担当）
- 投稿・返信機能（一方通行、Hiro主導）
- リアルタイム監視・自動収集（Hiroが意図的にURLを渡した時のみ動作）

---

## 2. アーキテクチャ選択 — 重要判断

X コンテンツの取得方法に3つの選択肢がある。**ここが本 spec の最大の判断ポイント**。

| 方式 | コスト | 安定性 | 制約 |
|------|--------|--------|------|
| **A. X API (Free tier)** | $0 | △（厳しいレート制限） | 月100reads/月、認証必須、tweet読み取りOK |
| B. X API (Basic $100/月) | $100/月 | ◎ | 10k reads/月、個人用途として過剰 |
| C. Playwright MCP（既存セットアップ） | $0 | △（X側仕様変更に弱い、ログイン要件で不安定化中） | 公開ツイートのみ取得可、認証壁が増えている |
| **D. Hiroが URL + 本文を貼る** | $0 | ◎ | API・自動化なし、ただし Hiro の手作業 5秒 |

### 採用判断: A (X API Free) を主軸、D を緊急代替

記事のメッセージは「**URLを渡すだけで自動**」が肝心。Hiroの選択（フルスペック・記事忠実）に従う。

- **主軸: A方式 (X API Free tier)**
  - 月100reads/月（Free tier 上限）を Hiro の取り込み頻度として想定
  - 1日3件相当。これを超えそうなら Basic ($100/月) 検討
  - X API credentials は spec #6 完了後 Bitwarden に保管、それまでは `.env` 暫定
- **緊急代替: D方式 (コピペ)**
  - X API レート制限到達時 or X 側障害時
  - `/x-intake-manual` で手動本文付与モード

**主軸 = A、サブ = D の構成で実装する**。Phase 概念は廃止（記事忠実で最初から自動）。

---

## 3. パイプライン全体像

```
[Hiro が /x-intake 起動]
   ↓
   引数: URL のみ（+ 任意のメモ）
   ↓
[X API で tweet 取得]
   - Bearer Token は .env (Phase 1) → Bitwarden (spec #6 完了後)
   - レート制限到達時は /x-intake-manual に切り替え案内
   ↓
[① 要約agent]
   - 投稿の主旨を3行で要約
   - キーワード抽出（Skill名、ツール名、技法名）
   ↓
[② 分類agent]
   - 既存スキル43個のSKILL.md descriptionと突き合わせ
   - 分類結果: skill_update / new_skill / context_only / discard
   ↓
[③ 提案agent]
   - 分類に応じて具体提案を生成
   ↓
[④ 出力]
   - ~/Obsidian/inbox/x-intake-YYYY-MM-DD-<slug>.md に保存
   - Telegram 通知（汎用Bot、spec #1と共用）
   ↓
[⑤ Hiro レビュー → 承認]
   - 提案を見て承認した内容のみ反映:
     - skill_update → 既存SKILL.md追記
     - new_skill → 新規skill scaffold
     - context_only → memory/ or context/ 追記
     - discard → 削除
```

---

## 4. 分類ロジック（②分類agent）

### 4.1 分類カテゴリ

| カテゴリ | 判定基準 | アクション |
|---------|---------|----------|
| `skill_update` | 既存スキルのSKILL.md description と関連度高い | 該当スキルへの追記案を生成 |
| `new_skill` | 既存スキルにマッチしないが、再利用可能なパターン | 新規skill草案を生成 |
| `gotcha` | 既存スキル/作業のハマりポイント | spec #2 の Gotcha化提案 |
| `context_only` | 一回限りの情報、参考メモ程度 | `memory/reference/` に追記 |
| `discard` | 重複・低価値・既知 | 削除提案（理由付き） |

### 4.2 既存スキル突き合わせ

```bash
# 全SKILL.mdのdescription frontmatterを取得
for skill in ~/.claude/skills/*/SKILL.md; do
  name=$(basename $(dirname $skill))
  desc=$(awk '/^description:/{flag=1;next}/^[a-z_]+:/{flag=0}flag' $skill | tr '\n' ' ')
  echo "$name: $desc"
done
```

これを Claude に渡し、「投稿内容と最も関連度高いスキル」を判定させる。

### 4.3 重複検出

新規スキル草案を生成する前に:
- 既存スキル名と類似していないか
- 過去のx-intake で同じ投稿を既に処理していないか（URLハッシュで判定）

重複検出時は「skill_update に変更推奨」と提案。

---

## 5. 出力フォーマット

### 5.1 `~/Obsidian/inbox/x-intake-YYYY-MM-DD-<slug>.md`

```markdown
# X-Intake 2026-05-14: <slug>

## 元投稿
- URL: https://x.com/user/status/123456
- 投稿者: @example
- 取得日: 2026-05-14

### 本文
（Hiroが貼り付けた本文）

## ① 要約
- (3行要約)

## ② 分類
- カテゴリ: skill_update
- 関連スキル: brainstorming
- 関連度: 高

## ③ 提案
### skill_update 提案
**対象**: `~/.claude/skills/brainstorming/SKILL.md`

**追記案**（diff）:
\`\`\`diff
+ ## Visual Companion との連携時の Gotcha
+ - companion の offer は必ず単独メッセージとして送信、clarifying question と混ぜない
+ - 受諾後も「per-question で使うか判定する」原則を忘れない
\`\`\`

## ④ アクション
- [ ] 提案を承認 → 該当ファイルに反映
- [ ] 不採用 → このファイルを `Obsidian/inbox/archive/` に移動
- [ ] 修正してから採用 → 編集後 [ ] チェック

## ⑤ メタデータ
- 処理時間: 2026-05-14 15:23:00 JST
- 使用モデル: claude-opus-4-7
```

### 5.2 Telegram 通知（汎用Bot）

```
📥 X-Intake処理完了
分類: skill_update (brainstorming スキル)
レポート: ~/Obsidian/inbox/x-intake-2026-05-14-visual-companion-gotcha.md
```

---

## 6. Slash command 仕様

### 6.1 `/x-intake` (主軸・X API自動取得)

`~/.claude/commands/x-intake.md`:
```markdown
---
description: XポストURLから自動取得してスキル/contextに反映候補を作成
---

ユーザーが以下の引数で呼び出しました:

$ARGUMENTS

引数の構造:
- 1行目: URL（必須）
- 末尾(任意): "メモ: ..." 形式でHiroのコメント

実施:
1. URL から tweet ID 抽出
2. X API (GET /2/tweets/:id) で本文・投稿者取得
   - 認証: X_API_BEARER_TOKEN（.env / Bitwarden）
   - レート制限エラー時: /x-intake-manual への切替を案内
3. 投稿を3行要約
4. 全SKILL.mdのdescriptionを取得して既存スキル一覧化
5. 関連スキル判定（skill_update / new_skill / gotcha / context_only / discard）
6. 該当カテゴリの提案を生成
7. ~/Obsidian/inbox/x-intake-YYYY-MM-DD-<slug>.md に出力
8. Telegram汎用Botに通知
9. Obsidianパスを返答
```

### 6.2 `/x-intake-manual` (緊急代替・コピペ)

X API障害・レート制限到達時の緊急代替手段。

```markdown
---
description: Xポストを手動コピペで取り込み（API使えない時の代替）
---

引数:
- 1行目: URL
- 2行目以降: 投稿本文（コピペ）
- 末尾(任意): "メモ: ..."

実施: /x-intake と同じパイプライン（X API 取得ステップだけスキップ）
```

### 6.3 使用例

```
/x-intake https://x.com/0xfene/status/2042047157767926056 メモ: spec #2 と一致するアイディア
```

→ X API で取得 → 要約 → 分類 → inbox 出力 → Telegram 通知

---

## 7. X API セットアップ手順

### 7.1 X Developer Portal でアプリ作成

1. https://developer.x.com/ にログイン（Hiroのアカウント）
2. 「Create Project」→ プロジェクト名 `claude-x-intake`
3. App を作成 → Bearer Token を取得
4. Free tier の制約確認: 月100 reads/月

### 7.2 credentials の保管

- **暫定 (Bitwarden 移行前)**: `~/.claude/.env.x-api`（gitignore）
  - `X_API_BEARER_TOKEN=...`
- **本格 (spec #6 完了後)**: Bitwarden `shared/x-api/BEARER_TOKEN` に移管

### 7.3 取り込み量超過時の判断基準

- 月100reads/月の制限に達し始めたら:
  - **Basic ($100/月) 検討**: 10k reads/月、Hiroの取り込み量×100倍の余裕
  - または **取り込み対象を厳選**（YAGNI、まず Free tier で運用）

### 7.4 API障害・廃止時の代替

- 一時的: `/x-intake-manual` で運用継続
- 恒久的: Playwright MCP or Bright Data 等の代替検討（spec改訂）

---

## 8. spec #1 / #2 / #3 / #5 との連動

### spec #1 (月次棚卸し)
- 月次棚卸しで `Obsidian/inbox/` の未処理 x-intake を検出
- 30日以上放置 → archive 提案

### spec #2 (Gotchas)
- x-intake で `gotcha` 分類されたものは `/gotcha` コマンドへルーティング
- Gotcha化提案として MEMORY.md / feedback_*.md に反映

### spec #3 (SSoT Map)
- `Obsidian/inbox/` は flow カテゴリ
- inbox → 処理完了で削除（spec #3 のルール）

### spec #5 (Dreams)
- Dreams 週次振り返り内で「inbox に未処理が溜まっている」を検出
- 取り込み習慣の継続性を可視化

---

## 9. Gotchas / リスク

### リスク1: 月100reads/月の上限到達

Hiroの取り込み頻度が想定を超えると Free tier 不足。

**対策**:
- 30件超えた時点で Basic 移行を提案
- レート制限到達時は `/x-intake-manual` でフォールバック運用可能

### リスク2: 既存スキル多すぎて分類精度が落ちる

47スキルもあると、Claude の関連度判定が雑になる。

**対策**:
- 月次棚卸し（spec #1）で未使用スキル隔離 → 関連度判定の対象数を抑える
- 分類agentに「迷ったら `context_only` に倒す」と明示

### リスク3: 重複した new_skill 草案を量産

似たような新規スキルが複数出来てしまう。

**対策**:
- 草案生成前に既存スキル全文と類似度確認
- 「新規スキル化が必要か3回確認してから」とプロンプトに明記

### リスク4: X 側の仕様変更

X API は頻繁に仕様変更・値上げがある（過去にAPI制限変更で多くの自動化が死んだ）。

**対策**:
- `/x-intake-manual` を恒久的に並走（API死んでも運用継続可）
- X API 廃止時の代替: Playwright MCP・他 SaaS（Bright Data等）を spec改訂で追加

### リスク5: 著作権・引用要件

X投稿の本文を Obsidian に保存することの法的グレー。

**対策**:
- 本文はあくまで「自分の学習素材」として保存、外部公開しない
- 引用元URL必須、投稿者名記載
- 商用利用しない（Phase 2 で 自動配信機能を作るなら要再検討）

---

## 10. 受け入れ基準

- [ ] X Developer Portal で Bearer Token 取得済み
- [ ] `/x-intake` slash command が動作（URL → 自動取得 → inbox に出力）
- [ ] `/x-intake-manual` slash command が動作（API障害時の代替）
- [ ] 既存47スキルの description 突き合わせができる
- [ ] 4分類（skill_update / new_skill / gotcha / context_only）が正しく機能
- [ ] Telegram 通知が届く（汎用Bot経由、spec #1と共用）
- [ ] inbox 出力ファイルが spec #3 の flow ルールに沿っている
- [ ] レート制限到達時に `/x-intake-manual` への切替案内が出る
- [ ] 初回テスト: 任意のX投稿URL1件を処理し、提案が出力される

---

## 11. 依存関係

- 先行: spec #1（汎用Telegram Bot）、spec #3（inbox flow定義）
- 並列: spec #2（Gotcha分類でルーティング）、spec #5（inbox未処理検出）
- 後続: なし

---

## 12. オープン質問

- Phase 1 のコピペフォーマット、テンプレ化して `/x-intake-template` を別途用意する？
  → 暫定: なし。コピペ慣れたら自然にフォーマット固定化される
- Phase 2 の X API Free tier、本当に Hiro の用途で足りる？
  → 月100reads = 1日3件。Hiroの取り込み頻度がそれ以上ならBasic($100/月)検討
- 取り込み履歴の検索機能（過去のx-intakeを横断検索）は必要？
  → 暫定: Phase 1 ではObsidian標準検索で十分、YAGNI
