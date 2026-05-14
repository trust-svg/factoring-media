# Dreams 週次振り返り — Design Spec

**Date**: 2026-05-14
**Author**: Hiro + Claude
**Status**: Draft (要レビュー)
**Origin**: note記事「育てるClaude Codeから"勝手に育つClaude Code"へ」の②代謝（Dreams側）

---

## 1. 目的

直近1週間の作業ログを Claude が自動スキャンし、**自己観察由来のパターン**を抽出する。

spec #2（Gotchas）が「人間のフィードバック起点」なのに対し、本 spec は「**昨日の自分の動きを今日の自分が観察する**」（記事より）仕組み。両者で代謝が完成する。

### 解決する課題

- 同じ判断を3回繰り返しているのに、誰も気づかない
- 同じ系統のミスが繰り返されているのに、Gotcha化されない
- Tomorrow Next が3週連続で持ち越されているのに、構造的問題として可視化されない
- Daily/ に重要な確定事実が書かれたまま、stock に昇格しない

### 非目標

- 自動 stock 昇格（自動化すると誤判定の損害が大きい）
- 自動 Gotcha 化（同上）
- 全行動の網羅的記録（YAGNI、パターン化したものだけ）

---

## 2. システム構成

### 2.1 トリガー

- **macOS launchd** で毎週 **土曜 08:00 JST** に Telegram リマインダー送信 → Hiro が Claude Code で `/dreams` を手動起動（先週分の Daily/ が確定したタイミング）
- launchd plist: `~/Library/LaunchAgents/com.trustlink.dreams-weekly-reminder.plist`
- 起動指定: `StartCalendarInterval` で `Weekday=6` (土曜), `Hour=8`, `Minute=0`

**設計判断の根拠** (2026-05-14 実装時に判明):
- CronCreate は session-only + 7日 auto-expire のため、週次cronはギリギリ動くが「Claude Code 未起動週」で消滅するリスクあり
- `schedule` skill (Claude.ai Routines) は remote環境で動作するため、Mac ローカルファイル（`~/Obsidian/Daily/`, `~/.claude/projects/*.jsonl`, `.company/meetings/`）にアクセスできず、本spec の入力データを取得できない
- spec #1 と同じく launchd リマインダー + Hiro 手動起動方式を採用（既存 d-manager / Obsidian-sync の launchd 運用パターンと整合）

### 2.2 実行フロー

```
[launchd 土曜 08:00 JST]
  ↓
[Telegram 汎用メタ運用Bot に「週次振り返りの時間です」リマインダー送信]
  ↓
[Hiro が Claude Code で /dreams を手動起動]
  ↓
[入力データ取得]
  ├─ ~/Obsidian/Daily/<過去7日>.md
  ├─ .company/meetings/<過去7日>
  ├─ git log --since="7 days ago" (Workspace全体)
  └─ ~/.claude/projects/-Users-Mac-air-Claude-Workspace/*.jsonl (過去7日抜粋)
  ↓
[3種類のパターン検出]
  ├─ ① 判断パターン（同じ判断を3+回）
  ├─ ② ミスパターン（同じ系統のミスを2-3回）
  └─ ③ 未消化パターン（Tomorrow Next 持ち越し継続）
  ↓
[週次レポート生成]
  ↓
[~/Obsidian/Daily/dreams-YYYY-MM-DD.md に書き込み（flow）]
  ↓
[Telegram 汎用メタ運用Bot に完了通知（spec #1と同じBot）]
```

### 2.3 2層構造（重要）

| ファイル | 役割 | type | 更新方式 |
|---------|------|------|---------|
| `~/Obsidian/Daily/dreams-YYYY-MM-DD.md` | **週次レポート**（自動生成・提案） | **flow** | 新規ファイル毎週 |
| `~/Obsidian/context/dreams.md` | **確定パターンDB**（人間承認後のみ） | **stock** | 累積追記、ただし重複検出あり |

この2層分離により:
- 週次レポートが腐っても害なし（flow、月次archive可）
- 確定パターンDBは承認済みだけなので肥大化しにくい
- spec #3 の flow/stock 分離原則と整合

---

## 3. 3種類のパターン検出ロジック

### ① 判断パターン

**定義**: 同じ系統の意識的判断を直近で3回以上行っている。

**検出方法**:
- Daily/ 内の "Dev Log" セクションを grep
- `--build` `--force` `--verbose` 等のフラグ言及
- 「〜にした」「〜を選んだ」等の判断表現
- 3回以上検出 → 該当事項を引用

**出力例**:
```markdown
### 判断パターン
- **deploy時に明示的に `--build` をつけるケースが3回**
  - 2026-05-09 ai-uranai
  - 2026-05-12 saimu-media
  - 2026-05-13 messecoach
  → 既存Gotcha `feedback_ai_uranai_deploy_rebuild.md` の scope を `workspace` に拡張すべき？
```

### ② ミスパターン

**定義**: 同じ系統のミス・訂正が2-3回以上発生。

**検出方法**:
- Daily/ の "Reflection" セクションで「ミスった」「忘れてた」「指摘された」を grep
- セッションログの user message で「やめて」「次から」「違う」パターン抽出
- 2-3回以上 → Gotcha化提案

**出力例**:
```markdown
### ミスパターン
- **コミット後に push を忘れる事象が2回**
  - 2026-05-10, 2026-05-12
  - 既存Gotcha `feedback_github_push.md` あり → trigger_count を 2→4 に更新推奨
```

### ③ 未消化パターン

**定義**: Daily/ の "Tomorrow Next" に同一項目が3週連続持ち越されている。

**検出方法**:
- 過去3週分の Daily/ の "Tomorrow Next" セクションを抽出
- ngram 類似度（粗くて可）で同一項目を検出

**出力例**:
```markdown
### 未消化パターン
- **「note記事のヘッダー画像差し替え」が3週連続持ち越し**
  - 構造的問題のサイン → スキマ時間に処理する仕組みが必要か？
  - 推奨アクション: 月次棚卸しで再評価 or 一旦archiveに送る
```

---

## 4. 週次レポート出力フォーマット

`~/Obsidian/Daily/dreams-YYYY-MM-DD.md`:

```markdown
# Dreams 週次振り返り 2026-05-17 (土)

**期間**: 2026-05-10 〜 2026-05-16

## サマリー
- 判断パターン: 2件
- ミスパターン: 1件
- 未消化パターン: 1件
- 承認推奨: 計 3件

---

## 判断パターン
...

## ミスパターン
...

## 未消化パターン
...

## stock 昇格候補（spec #3 連動）
- 2026-05-12 ai-uranai 初成約事実 → `memory/ai-uranai.md` への昇格推奨
- 2026-05-13 saimu-media x-auto 追加実装 → `memory/MEMORY.md` のポインタ追加推奨

## アクション
- [ ] パターン1を承認 → `/gotcha` で確定
- [ ] パターン2を承認 → 既存Gotchaの trigger_count 更新
- [ ] stock昇格1を承認 → `memory/ai-uranai.md` 更新
- [ ] 未消化1を月次棚卸しに送る
```

---

## 5. 承認 → context/dreams.md 昇格フロー

Hiro がレポートを確認後の流れ:

```
週次レポート（Daily/dreams-YYYY-MM-DD.md）
  ↓
Hiroが「承認するパターン」をチェック
  ↓
承認したパターンを context/dreams.md に追記
  ↓
追記時に重複検出（既存エントリと類似なら trigger_count++）
  ↓
context/dreams.md に蓄積された確定パターン = Claude が常時参照
```

### context/dreams.md のエントリ形式

```markdown
## パターン #007: deploy時の --build 明示

- **type**: judgment
- **first_detected**: 2026-05-09
- **last_confirmed**: 2026-05-17
- **trigger_count**: 5
- **scope**: workspace (deploy系全般)

### 詳細
Docker Compose の volume mount なしプロダクトでは、`docker compose up -d` だけでは
コード変更が反映されない。`--build` 必須。

### 関連 Gotcha
- feedback_ai_uranai_deploy_rebuild.md
```

---

## 6. spec #1 / #2 / #3 との連動

### spec #1 (月次棚卸し) との連動
- 月次棚卸しに「先週のDreams提案、承認されてない3件」セクション追加
- 承認漏れキャッチ用

### spec #2 (Gotchas) との連動
- Dreams のミス/判断パターンが Gotcha 化提案を出す
- 承認後は `/gotcha` で memory に書き込み
- 既存Gotchaの trigger_count 更新も Dreams が提案

### spec #3 (SSoT) との連動
- Dreams が flow→stock 昇格候補を提示
- spec #3 で定義した SSoT Map に沿って正しい場所に昇格

---

## 7. 実装方式

| ファイル | 役割 | 場所 |
|---------|------|------|
| `dreams.md` (prompt) | 週次振り返りプロンプト本体 + `/dreams` slash command 定義 | `~/.claude/commands/dreams.md` |
| `dreams-weekly-reminder.sh` | launchd から呼ぶリマインダー送信スクリプト | `~/.claude/scripts/dreams-weekly-reminder.sh` |
| launchd plist | スケジュール本体（土曜 08:00 JST にリマインダー送信） | `~/Library/LaunchAgents/com.trustlink.dreams-weekly-reminder.plist` |

### prompt 仕様（抜粋）

```markdown
あなたは週次振り返り（Dreams）agent です。
入力データから以下3種類のパターンを検出してください:

1. 判断パターン: 同じ判断を3+回している
2. ミスパターン: 同じ系統のミスを2-3+回している
3. 未消化パターン: Tomorrow Next の3週連続持ち越し

入力データ:
- ~/Obsidian/Daily/<過去7日>.md
- .company/meetings/<過去7日>
- git log --since="7 days ago" (Workspace全体)

出力先:
- ~/Obsidian/Daily/dreams-YYYY-MM-DD.md（週次レポート、flow）

最後に Telegram 汎用Bot に通知してください。
context/dreams.md は直接更新しない（人間承認待ち）。
```

---

## 8. Gotchas / リスク

### リスク1: 過剰検出でノイズが増える

3回閾値を緩く取ると、トリビアルなパターンまで拾ってノイズになる。

**対策**:
- 初期は「3回以上」を厳格に運用
- 4週運用してみて、件数が多すぎたら 4回閾値に引き上げ（spec 改訂）

### リスク2: パターン検出が見当違いで誤った Gotcha 化提案

Claude のパターン認識は完璧ではない。誤検出は普通にある。

**対策**:
- 全ては「提案」止まり、人間承認まで stock 化しない
- 承認時の負荷を下げるため、レポートにアクションチェックリストを付ける（コピペで実行可能）

### リスク3: 1回も承認されない週がある

Hiroが週末に Dreams レポートを読まない週がある。

**対策**:
- 月次棚卸し（spec #1）で「未承認 Dreams レポート」を再提示
- 4週連続未承認なら「運用見直し提案」を出す

### リスク4: dreams-YYYY-MM-DD.md が増えすぎる

flow なので時系列追加されるが、52ファイル/年で増加する。

**対策**:
- 月次棚卸し（spec #1）で「3ヶ月前のdreamsレポート」を `Obsidian/Daily/archive/` に移動推奨
- 履歴は残す（後で振り返り可能）

---

## 9. 受け入れ基準

- [ ] launchd plist `com.trustlink.dreams-weekly-reminder.plist` が登録され、`launchctl list | grep dreams` で確認できる
- [ ] 土曜 08:00 JST にリマインダー Telegram が届く（手動 `launchctl start` で発火検証可）
- [ ] Hiro が `/dreams` を Claude Code で起動すると `Daily/dreams-YYYY-MM-DD.md` が出力される
- [ ] レポートが3セクション（判断/ミス/未消化）+ stock昇格候補 + アクションリスト構成
- [ ] 完了通知 Telegram が届く（汎用Bot経由）
- [ ] `/dreams` slash command で手動起動できる
- [ ] 初回手動実行で「最低1パターン」または「健全宣言」が出る
- [ ] `~/Obsidian/context/dreams.md` テンプレが用意されている
- [ ] 承認 → context/dreams.md 昇格手順が明文化されている

---

## 10. オープン質問

- 「ngram類似度で同一項目検出」のロジックは Claude のプロンプト内判定でよい？ 専用ツール不要？
  → 暫定: プロンプト内判定（粗くて可、誤検出は人間承認でフィルタ）
- 初週のbaseline作成（過去パターンの初期投入）はやる？
  → 暫定: やらない。運用開始後、累積で形成。

---

## 11. 依存関係

- 先行: spec #1（Telegram汎用Bot共用）、spec #3（SSoT Map と flow/stock分離）
- 並列: spec #2（Gotcha化提案の出力先として連携）
- 後続: なし
