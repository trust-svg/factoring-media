# 月次リポジトリ棚卸し Ritual — Design Spec

**Date**: 2026-05-14
**Author**: Hiro + Claude
**Status**: Draft (要レビュー)
**Origin**: note記事「育てるClaude Codeから"勝手に育つClaude Code"へ」の③排泄

---

## 1. 目的

Claude Code リポジトリ（`~/.claude/` + `~/Claude-Workspace/`）の**汚れを月次で可視化する**。
判断・削除そのものは自動化せず、「**現状を見せて人間に判断材料を渡す**」までを担当。

### 解決する課題

- スキルが47個まで増えた。どれが使われてないか把握できていない
- メモリ40+ファイル中、半年以上更新されていないものがある（feedback_line_deprecated等）
- 処理速度低下を感じても原因が分からない（MEMORY.md膨張？hooks肥大？）
- 「掃除しなきゃ」と思うが、判断負荷が高くて先送りされる

### 非目標（やらないこと）

- 自動削除・自動アーカイブ（誤検出時の損害が大きすぎる）
- スキル品質評価（観点が広すぎて月次プロセスに乗らない）
- VPS側の整理（Macローカルとは別問題）

---

## 2. システム構成

### 2.1 トリガー

- **CronCreate routine** で毎月1日 09:00 JST に発火
- スケジュール式: `0 9 1 * *`（TZ=Asia/Tokyo）

### 2.2 実行フロー

```
[Cron 09:00 JST 月初]
  ↓
[remote agent 起動] (claude-opus-4-7 デフォルト)
  ↓
[3つの監査を直列実行]
  ├─ ① 未使用スキル検出
  ├─ ② 古いメモリ/contextファイル検出
  └─ ③ 処理速度ボトルネック診断
  ↓
[Markdownレポート生成]
  ↓
[Obsidian/Daily/repo-cleanup-YYYY-MM-DD.md に書き込み]
  ↓
[Telegram @bmanager_trustlink_bot に「棚卸しレポート出ました」通知]
```

### 2.3 出力先

- **メイン**: `/Users/Mac_air/Obsidian/Daily/repo-cleanup-YYYY-MM-DD.md`
- **通知**: 新規Telegram Bot（仮称 `@hiro_meta_bot` または `@claude_cleanup_bot`）
  - BotFatherで新規作成が必要（実装時の最初のステップ）
  - 既存 `@bmanager_trustlink_bot` はeBay用のため分離
  - 後の Gotchas / Dreams 通知も同じBot使い回し可能（汎用メタ運用Bot）
  - 通知内容: 「📋 月次棚卸しレポート出ました: <Obsidianパス>」+ サマリー3行

---

## 3. 3つの監査ロジック

### ① 未使用スキル検出 + Quarantine実行

**入力データ**:
- `~/.claude/projects/-Users-Mac-air-Claude-Workspace/*.jsonl`（直近90日分のセッションログ）
- `~/.claude/skills/*/SKILL.md`（インストール済みスキル一覧）
- `~/.claude/skills/.archive/`（先月の隔離済みスキル）

**判定ロジック**:
1. JSONLログを grep して `Skill(\w+)` または `<skill-name>` パターンを抽出
2. 過去90日で呼び出されていないスキルをリストアップ
3. **内部呼び出し検出**: 他の `SKILL.md` 内に当該スキル名が言及されているか grep
   - 言及あり → `要確認（内部依存の可能性）` フラグ
   - 言及なし → `隔離候補` フラグ

**Quarantineフロー（削除実行はしない、移動のみ）**:
```
判定: 90日未使用 + 内部呼び出しなし
  ↓
レポートに「隔離候補: <skill>」と記載
  ↓
ユーザーがレポートを確認して許可した場合のみ、次月の棚卸し時に隔離実行:
  ~/.claude/skills/<skill>/  →  ~/.claude/skills/.archive/2026-MM/<skill>/
  ↓
隔離後さらに30日（次々月）誰も復活させなかったら → 完全削除候補としてレポート
```

**注意**: 月次棚卸しエージェント自身は**ファイル移動を実行しない**。レポートに「以下のコマンドを叩けば隔離されます」と書くだけ。実行はHiroの手動承認後。

**出力例**:
```markdown
## ① 未使用スキル（直近90日）

### 新規隔離候補（90日未使用 + 内部依存なし）
| スキル | 最終呼び出し | 内部依存 |
|--------|------------|----------|
| ads-linkedin | なし | なし |
| remotion-to-hyperframes | なし | なし |

実行コマンド（コピペ）:
\`\`\`bash
mkdir -p ~/.claude/skills/.archive/2026-06/
mv ~/.claude/skills/ads-linkedin ~/.claude/skills/.archive/2026-06/
mv ~/.claude/skills/remotion-to-hyperframes ~/.claude/skills/.archive/2026-06/
\`\`\`

### 要確認（90日未使用だが内部依存あり）
| スキル | 依存元 |
|--------|--------|
| ads-microsoft | ads-audit/SKILL.md で言及 → 残置推奨 |

### 隔離済み（先月分・誰も呼ばなかった）
- ~/.claude/skills/.archive/2026-05/<skill> — 30日経過、完全削除候補
  実行: `rm -rf ~/.claude/skills/.archive/2026-05/<skill>`
```

### ② 古いメモリ/contextファイル検出

**入力データ**:
- `~/.claude/projects/-Users-Mac-air-Claude-Workspace/memory/*.md`
- `~/Obsidian/context/*.md`

**ロジック**:
1. `git log -1 --format=%ai <file>` で最終更新日取得（gitignoreファイルは `stat -f %m`）
2. 180日以上更新されていないファイルをリスト化
3. ファイル内容の冒頭3行を併記して「廃止宣言済み」「TODO残置」を判定

**出力例**:
```markdown
## ② 古いメモリ/context（180日+ 未更新）
- `feedback_line_deprecated.md` — 2026-04-22 廃止宣言済み → **削除可**
- `meta-ads-setup.md` — Olive campaign削除済み → **要更新 or 削除**
```

### ③ 処理速度ボトルネック診断

**入力データ**:
- `~/.claude/CLAUDE.md`（行数）
- `~/Claude-Workspace/CLAUDE.md`（行数）
- `MEMORY.md`（行数 — 200行超で truncate される仕様）
- `~/.claude/hooks/*.sh`（hook処理時間の推定）
- `~/.claude/settings.json` の `permissions.allow` 件数

**ロジック**:
- 各ファイルの行数チェック → 閾値超過を警告
- hook の `time` 計測（過去ログから推定可能なら）
- permissions.allow が散らかってないか（重複・古い指定）

**閾値**（2026-05-14 実測ベースで設定）:

| ファイル | warning | critical | 理由 |
|---------|---------|----------|------|
| `~/.claude/CLAUDE.md` | 200行 | 300行 | 経験則: 200行超で読み飛ばし発生 |
| `Workspace/CLAUDE.md` | 200行 | 300行 | 同上 |
| `MEMORY.md` | **150行** | **180行** | 200行で auto-truncate(現在171行=危険水域) |
| `permissions.allow` | 80件 | 150件 | 重複・古い指定が増えてくる目安 |

**出力例**:
```markdown
## ③ 処理速度ボトルネック
- ✅ `~/.claude/CLAUDE.md`: 35行（健全）
- ✅ `Workspace/CLAUDE.md`: 110行（健全）
- 🔴 `MEMORY.md`: 171行（CRITICAL、180行超で auto-truncate圏内）
  → 古い feedback_* を `memory/.archive/YYYY-MM/<item>/` に移動推奨（spec #2 で構造定義）
- ⚠️ `permissions.allow`: 110件（warning、重複ありか確認）
```

---

## 4. 実装方式

### 4.1 構成要素

| ファイル | 役割 | 場所 |
|---------|------|------|
| `monthly-cleanup.md` (prompt) | 監査プロンプト本体 | `~/.claude/commands/monthly-cleanup.md` |
| `monthly-cleanup-routine.sh` | 補助スクリプト（ログ集計） | `~/.claude/scripts/monthly-cleanup.sh` |
| CronCreate登録 | スケジュール本体 | Claude Code 内（永続） |

### 4.2 prompt 仕様（抜粋）

```markdown
あなたは月次リポジトリ棚卸し agent です。以下の3つを実施してください:

## ① 未使用スキル検出
- ~/.claude/projects/-Users-Mac-air-Claude-Workspace/*.jsonl を grep
- 過去30日に呼び出されていない skill を列挙

## ② 古いメモリ検出
- memory/*.md / Obsidian/context/*.md の最終更新日を確認
- 180日以上未更新のものを列挙

## ③ ボトルネック診断
- CLAUDE.md / MEMORY.md / settings.json の行数チェック
- 閾値超過を警告

最終出力は /Users/Mac_air/Obsidian/Daily/repo-cleanup-YYYY-MM-DD.md に書き込み、
Telegram bmanager_trustlink_bot に通知してください。
```

### 4.3 Slash command として併用可能に

`/monthly-cleanup` を Slash command 化することで、月初を待たず**任意のタイミングで手動実行可能**にする。これによりCron発火失敗時のフォールバックも兼ねる。

---

## 5. Gotchas / リスク

### リスク1: Cron発火失敗をサイレント故障させない

**対策**:
- 棚卸し agent が「実行開始」と「実行完了」の両方をTelegram通知
- 月の3日になっても通知が来てなければ、月次棚卸し未実行 → 別チェック機構が必要かは要検討（YAGNI判断）

### リスク2: jsonl ログ削除でスキル使用履歴が欠落

`.claude/projects/` のログは Hiro が手動削除する可能性あり。
- 削除されたら「ログ無いので未使用判定スキップ」と明示する
- 嘘の「未使用」判定で削除してしまうのを防ぐ

### リスク3: 偽陽性（使ってるのに「未使用」判定）

例: `frontend-design` を直接呼ばずに別スキル経由で内部呼び出し → ログに残らない可能性。

**構造的対策（quarantine pattern）**:
1. **削除ではなく移動**: 候補スキルは `~/.claude/skills/.archive/YYYY-MM/` に移動するだけ
2. **観察期間**: 隔離後30日（次月の棚卸し）誰も復活させなかったら、初めて完全削除候補にあがる
3. **復活はワンコマンド**: `mv ~/.claude/skills/.archive/2026-06/<skill> ~/.claude/skills/`

**補助対策**:
- 月次棚卸しエージェント自身は**ファイル移動を実行しない**（Hiro承認後コピペで実行）
- 内部呼び出し検出: 他SKILL.md内の言及をgrep → 言及あれば「要確認」フラグで隔離見送り
- 隔離フォルダはClaude Codeの skill discovery 対象外になるかは要検証（実装時に確認）

---

## 6. 受け入れ基準

- [ ] 新規Telegram Bot が作成され、Chat IDとTokenが安全に保管されている
- [ ] CronCreate で routine が登録され、`CronList` で確認できる
- [ ] 月初1日 09:00 JST に発火し、レポートが Obsidian/Daily/ に出る
- [ ] レポートが3セクション（①②③）構成で出力される
- [ ] Telegram 通知が届く（要約3行 + Obsidian path）
- [ ] `/monthly-cleanup` slash command で手動起動できる
- [ ] 初回手動実行で「最低1件の隔離候補」または「健全宣言」のどちらかが出る
- [ ] レポートに「実行コマンド（コピペ）」が含まれ、Hiroが承認後に手動実行できる
- [ ] 隔離フォルダ `~/.claude/skills/.archive/` がClaude Codeの skill discovery 対象外であることが確認できている

---

## 7. オープン質問

なし。実装に進める。
