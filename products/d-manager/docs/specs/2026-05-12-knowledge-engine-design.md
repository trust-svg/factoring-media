# 知見エンジン（Knowledge Engine）設計スペック

- 日付: 2026-05-12
- 対象: `products/d-manager/`
- 着想元: Lancers 秋吉社長の「秋吉AI」（Notion + Claude Code でCEOの判断パターンをクローン化）。動画トランスクリプトから、d-manager に移植して効く要素を抽出して再設計したもの。
- ステータス: ドラフト（フェーズ1のみ詳細。フェーズ2〜4は方針レベル。フェーズ5は別スペック）

---

## 1. 背景と目的

Hiro は個人事業主で複数プロダクトを1人運営しており、CLAUDE.md にある通り「情報管理・収益最大化・自動化・意思決定」が常時課題。d-manager は既に7部門12名のAI社員を持つ仮想組織Botで、`learning/store.py` に CLI/API 両モードの全会話ターンを記録済み（SQLite WAL + FTS5）、`scheduler.py` に夜間QA・learning_review(23:00)・週次curator を持つ。

秋吉AIの本質は次の3段ループ:

1. **シグナル**: 日々の活動（会話・コミット・メール・カレンダー・録音…）から「意味ある情報だけ」を抽出して貯める（点）。
2. **ストーリー**: シグナルを因果チェーン（線）に束ね、成功/失敗パターンを蓄積する。自分でも気づいていない「型」をAIが発見する。
3. **判断の型 + コンサル/アラート**: 判断の型 + ストーリー + 最近のシグナルを参照し、「Hiroならこう考える」を返す／「このまま行くと〇〇のストーリーに乗る、今これが効く」とプロアクティブに知らせる。

これを d-manager に `knowledge/` モジュールとして実装する。CLAUDE.md の「組織化の真の利得＝未着手仕事の解放」基準に照らすと、これは「Hiroひとりでは絶対やらない（毎日全ソースを読んで意味ある点を拾い、線にして、過去の型と照合する）」に該当し、採用基準を満たす。

### 取り込まないもの（YAGNI / スコープ外）

- 24時間ライフログ録音の常時取り込み（ソロ運営には過剰。Plaud で「会議を録ったとき」だけ取り込めば十分）
- 全社員へのクローン横展開（社員＝仮想AIなので意味が薄い）
- Notion を新規データ基盤として導入すること（d-manager は Markdown + `.company/` で完結。ただし Plaud → Notion 連携を経由する場合は既存 `tools/notion_tool.py` を読むだけ）
- 採用→AI自動承認まで自動化すること（CLAUDE.md「不可逆操作は毎回確認」と衝突。提案止まりで運用）

---

## 2. 全体アーキテクチャ

d-manager 内に新モジュール `knowledge/` を作る（`learning/` と並列構成）。データはハイブリッド: **SQLite が正、Markdown はビュー**（秋吉AIと同じ思想 — 普段は人が直接DBを見ないが、Obsidian/git で追える形でも置く）。

```
products/d-manager/
  knowledge/
    __init__.py
    store.py          # SQLite (knowledge.db): digests / signals / stories / decision_patterns + FTS5
    digest.py         # フェーズ1: チャット→議事録化
    extractor.py      # フェーズ2: シグナル抽出
    storyteller.py    # フェーズ3: ストーリー抽出
    alerter.py        # フェーズ4: ストーリーアラート照合
    views.py          # SQLite → .company/secretary/knowledge/ への Markdown 書き出し（共通）
    sources/          # フェーズ2以降の入力アダプタ
      __init__.py     # 共通IF: fetch(date) -> list[RawItem]
      dmanager_log.py # その日の digests を読む
      git.py          # 全リポの commit message + diff stat
      obsidian.py     # Obsidian Daily / memory / context の当日差分
      gmail.py        # 重要メール（tools/gmail_tool.py 流用）
      calendar.py     # 当日の予定・会議（tools/calendar_tool.py 流用）
      ebay.py         # eBay 売上・新規/リピート購入（tools/ebay_sales.py 流用）
      ads.py          # Meta/Google 広告レポートの数値変化
      freee.py        # 入出金（tools/expense.py / freee MCP 流用）
      telegram.py     # bot ログ（取得経路は実装時に詰める。デフォルト=ログファイル監視）
      plaud.py        # 監視フォルダの文字起こし（デフォルト ~/Plaud/、config で差し替え可）
  learning/cli_runner.py   # 既存。claude -p ラッパとして再利用
  config.py                # KNOWLEDGE_DIR / KNOWLEDGE_DB_PATH / 各アダプタ ON-OFF / 閾値を追加
  scheduler.py             # 夜間バッチに knowledge_digest → knowledge_signals → alerter、週次に knowledge_stories
  main.py                  # !digest / !signals / !stories / !story / !ask-ceo コマンド、朝ブリーフィングに統合
  tests/                   # tmp_path で一時DB、claude -p は monkeypatch でモック（既存作法に準拠）

.company/secretary/knowledge/   # Markdown ビュー（別gitリポ。書き込み・コミットは d-manager の既存パターンに合わせる）
  digests/YYYY-MM-DD-<dept>-<channel>.md
  signals/YYYY-MM-DD.md
  stories/<slug>.md
  patterns/<slug>.md
```

### 共通の原則

- 各アダプタは `config` で個別 ON/OFF。最初は `dmanager_log` + `git` + `obsidian` だけ ON でも知見エンジンは回る。Telegram/Plaud/Gmail 等は後から1個ずつ足す。
- 冪等性: 日次バッチは同じ日付で再実行可（上書き）。
- サイレント故障対策: 各バッチは失敗件数を記録し、朝ブリーフィングに「digest N件 / 失敗 M件」「signals N件」のように出す。`claude -p` 失敗・空はそのアイテムをスキップしてログ＆次へ。
- シークレット保護: 全 `claude -p` プロンプトに「APIキー・パスワード等が入力に含まれても出力に含めずマスクする」を明記（CLAUDE.md準拠）。
- `.company/` への書き込み: `.company/` は別 git リポ。`tools/daily_note.py` / `tools/council.py` 等の既存の書き込み・コミット挙動を実装時に確認し、それに合わせる（新方式を勝手に作らない）。

---

## 3. フェーズ1: チャット→議事録化（詳細設計）

### 目的

d-manager の各チャンネル/councilスレッドでの AI社員⇔Hiro のやり取りを、日次で構造化議事録にする。秋吉AIの知見「AI↔人のテキストやり取りを議事録化して再投入すると、音声文字起こしより資産性が高い」をそのまま適用。これがフェーズ2（シグナル抽出）の主入力になる。

### 生データ

`learning/store.py` の `turns` テーブルに CLI/API 両モードの全ターンが `(channel_id, channel_name, department, review_date, turn_idx, role, content, engine, origin, ts)` で記録済み。`sessions` テーブルがレビュー台帳（キー = `(channel_id, review_date)`、`turn_count` あり）。

### コンポーネント

**`knowledge/store.py`** — 新 SQLite ファイル `knowledge.db`（`config.KNOWLEDGE_DB_PATH`、デフォルト `KNOWLEDGE_DIR / "knowledge.db"`）。WAL。

```sql
CREATE TABLE IF NOT EXISTS digests (
  id            INTEGER PRIMARY KEY,
  channel_id    TEXT NOT NULL,
  channel_name  TEXT,
  department    TEXT,
  date          TEXT NOT NULL,           -- YYYY-MM-DD
  source_kind   TEXT NOT NULL,           -- 'chat' | 'council'
  turn_count    INTEGER NOT NULL DEFAULT 0,
  summary_md    TEXT NOT NULL,           -- 構造化議事録（Markdown）。council の場合はファイルパス参照を含む短い索引
  topics_json   TEXT,                    -- ["...", ...]
  decisions_json TEXT,                   -- [{"text": "...", "by": "..."}]
  open_items_json TEXT,                  -- ["...", ...]
  next_actions_json TEXT,                -- [{"text": "...", "owner": "..."}]
  facts_json    TEXT,                    -- ["数字や固有名詞のメモ", ...]
  created_at    TEXT NOT NULL,
  UNIQUE(channel_id, date)
);
-- FTS5(trigram) on summary_md, topics（learning/store.py の FTS パターンに合わせる。3文字以上で部分一致）
```

`init_db()` / `upsert_digest()` / `get_digests(date)` / `search(query)` を提供。

**`knowledge/digest.py`** — `build_daily_digests(date: str, *, dry_run=False) -> DigestResult`

1. その日のセッション一覧を取得。`learning/store.py` に「指定日のセッション一覧」ヘルパが無ければ `list_sessions_for_date(db_path, date, min_turns)` を追加する（既存 `list_pending_reviews` の SQL を流用、`review_status` 条件は外す）。
2. フィルタ:
   - `turn_count >= MIN_DIGEST_TURNS`（config、デフォルト 4）
   - 通知専用チャンネル（4つ）の `channel_id` は除外（config の通知チャンネルリストを参照）
   - 中身がほぼコマンド出力だけのセッションは除外（簡易判定: ユーザー発言がすべて `!` で始まる短文 → スキップ。閾値は config）
3. 各対象セッションについて:
   - `learning/store.get_session_turns()` でターン取得
   - `learning/reviewer.py` の会話ログ整形ロジックを共有関数として切り出して使う（`learning/reviewer.py` と `knowledge/digest.py` の両方から呼ぶ）。整形のみ共有し、`claude -p` 呼び出しとプロンプトは別々。
   - `learning/cli_runner.py` の `claude -p` ラッパに「議事録化プロンプト」を渡す:
     - 出力: 参加者（どのAI社員）/ トピック / 決定事項（誰が） / 未決事項 / 次アクション（担当） / 出てきた数字・事実・固有名詞
     - フォーマット: 人が読む Markdown 本文（`summary_md`）+ 機械可読の JSON ブロック（`topics` / `decisions` / `open_items` / `next_actions` / `facts`）。両方を1回の出力で返させてパースする。
     - シークレットマスク指示を含める。
   - `knowledge/store.upsert_digest()` で保存
   - `knowledge/views.write_digest_md()` で `.company/secretary/knowledge/digests/YYYY-MM-DD-<dept>-<channel>.md` に書き出し
4. council スレッド（`.company/meetings/*.md` のうち日付が `date` のもの）は既に議事録形式 → 再生成しない。`source_kind="council"`、`summary_md` にファイルパスと冒頭要約だけ入れてインデックス化（FTS で引けるように）。
   - council スレッドの内容が `turns` テーブルにも入っている場合（thread の channel_id がある場合）は、その channel_id を chat 側の処理から除外して二重計上を避ける。
5. 結果（処理件数 / 失敗件数 / スキップ件数）を返す。

**`scheduler.py`** — 新ジョブ `knowledge_digest` を **夜間バッチに追加**（`learning_review`(23:00) の直後）。当日分（`date = today`）を処理。`learning_review` と同じ turns を別レンズ（reviewer = スキル遵守チェック、digest = 何を議論/決定したか）で2回読むのは意図的。

**`main.py`** — `!digest [YYYY-MM-DD]` で手動実行＆結果表示（省略時は今日）。朝ブリーフィングに「📋 昨日のダイジェスト N件 / 失敗 M件」+ 主要トピック数件を1行追加。

### エラー処理

- `claude -p` 失敗・空・JSONパース失敗 → そのセッションをスキップ、`logs/` にログ、失敗カウント++、次へ。
- DB ロック: `learning` と同じ WAL。`busy_timeout` を設定。
- `.company/` への書き込み失敗（リポ状態異常等）→ SQLite には保存済みなので致命ではない。ログして続行、朝ブリーフィングに警告。

### テスト

`pytest`、`tmp_path` に一時 `learning` DB と一時 `knowledge` DB を作り、ダミー turns を投入。`learning/cli_runner.py` の `claude -p` 呼び出しは `monkeypatch` で固定 JSON を返すモックに差し替え。検証項目:

- ターン数閾値未満のセッションが除外される
- 通知チャンネルが除外される
- コマンドのみセッションが除外される
- 正常セッションが `digests` テーブルと Markdown 両方に書かれる
- 同じ `(channel_id, date)` の再実行が上書きになる（冪等）
- `claude -p` がエラー/空のとき該当セッションだけスキップされ、他は処理される（失敗カウントが正しい）

既存 `tests/` の作法・`docs/plans/2026-05-12-learning-loop.md` の「サンドボックス向けテスト作法」に合わせる。

### フェーズ1のスコープ外

Telegram/Plaud/Gmail/Calendar 等の外部ソースはフェーズ1では扱わない（フェーズ2のシグナル抽出が直接食う）。フェーズ1は「d-manager 会話 + council スレッド」のみ。

---

## 4. フェーズ2: シグナルDB + シグナル抽出（方針）

### データ

`knowledge/store.py` に追加:

```sql
CREATE TABLE IF NOT EXISTS signals (
  id           INTEGER PRIMARY KEY,
  date         TEXT NOT NULL,            -- YYYY-MM-DD（シグナルが発生/観測された日）
  source_kind  TEXT NOT NULL,            -- 'dmanager' | 'git' | 'obsidian' | 'gmail' | 'calendar' | 'ebay' | 'ads' | 'freee' | 'telegram' | 'plaud'
  source_ref   TEXT,                     -- 元データへの参照（commit hash, file path, message id, digest id 等）
  product      TEXT,                     -- ebay-agent / ZINQ / FACCEL / saimu-media / d-manager / Sion / threads-auto / ... / null
  category     TEXT NOT NULL,            -- レポート | 仮説 | 学び | 意思決定 | 接触 | アイデア | 気づき | 数字・事実 | リスク
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  importance   INTEGER NOT NULL,         -- 1..5
  entities_json TEXT,                    -- ["人名", "会社名", "ツール名", ...]
  created_at   TEXT NOT NULL
);
-- FTS5 on title, body
```

### アダプタ（`knowledge/sources/`）

共通IF: `fetch(date: str) -> list[RawItem]`（`RawItem = {source_kind, source_ref, raw_text, hint_meta}`）。各アダプタは `config` の `KNOWLEDGE_SOURCES` で個別 ON/OFF。

- `dmanager_log.py`: その日の `digests` を読んで RawItem 化（議事録の本文 + 決定 + アクション + facts）
- `git.py`: 全リポ（`config` のリポ一覧 or workspace 配下を走査）の当日コミットの `git log --stat` + メッセージ
- `obsidian.py`: `~/Obsidian/Daily/YYYY-MM-DD.md` と `memory/` / `context/` の当日変更ファイルの差分
- `gmail.py` / `calendar.py` / `ebay.py` / `ads.py` / `freee.py`: 既存 `tools/` を流用して当日の関連データを取得
- `telegram.py`: bot のやり取りログ。取得経路（各 bot の DB を読む / bot から d-manager へ転送させる / Bot API getUpdates）は実装時に詰める。デフォルトは「ログファイル監視」。経路が決まるまでこのアダプタは OFF。
- `plaud.py`: 監視フォルダ（`config.PLAUD_WATCH_DIR`、デフォルト `~/Plaud/`、iCloud パス可）に置かれた txt/md/docx の文字起こし・要約を読む。処理済みは別ディレクトリへ移動 or マーク。Plaud のエクスポート手段（アプリから書き出し / Notion 連携経由）は別途確認 → 連携経由になったら `plaud_notion.py` を追加して差し替え。

### 抽出

`knowledge/extractor.py` — `build_daily_signals(date)`:

1. ON のアダプタすべてから `fetch(date)` で RawItem を集める
2. `claude -p` に「シグナル抽出プロンプト（= 秘伝のタレ）」+ RawItem 群を渡す:
   - 挨拶・定型・コマンド出力・無意味な雑談は捨てる
   - 残ったものを `category` / `importance(1-5)` / `product` / `entities` を付けて構造化（複数シグナルを JSON 配列で返させる）
   - シークレットマスク指示を含める
3. `signals` テーブルに保存 + `knowledge/views.write_signals_md()` で `.company/secretary/knowledge/signals/YYYY-MM-DD.md`（カテゴリ別に並べた人が読める形）に書き出し
4. 結果件数を朝ブリーフィングへ

### スケジュール / コマンド

- 夜間バッチ: `knowledge_signals`（`knowledge_digest` の直後）
- `!signals [today|week|product:<name>|category:<name>]` で一覧表示
- 朝ブリーフィング: 「💡 昨日の主要シグナル: …（importance >= 4 を3件まで）」

---

## 5. フェーズ3: ストーリーDB + ストーリー抽出（方針）

### データ

```sql
CREATE TABLE IF NOT EXISTS stories (
  id                   INTEGER PRIMARY KEY,
  title                TEXT NOT NULL,
  kind                 TEXT NOT NULL,    -- 'success' | 'failure' | 'pattern'
  causal_chain_json    TEXT NOT NULL,    -- [{"when": "...", "event": "...", "decision": "...", "action": "...", "result": "..."}, ...]
  time_span            TEXT,             -- 'week' | 'month' | 'quarter' | 'year' | 'multi-year'
  products_json        TEXT,             -- ["ebay-agent", ...]
  evidence_signal_ids_json TEXT,         -- [12, 34, ...]
  lesson               TEXT NOT NULL,    -- 「だからこうすべき」
  status               TEXT NOT NULL,    -- 'draft' | 'confirmed' | 'archived'
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);
```

### 初期投入（seed）

Obsidian の `memory/` にある既存教訓（ai-uranai 初成約の経緯 / 5/1施策が8日間サイレント未稼働だった事故 / Caddyfile を sed -i で壊した事故 / FACCEL→saimu-media の横展開 / GEO対策の skill 化と他プロダクト適用 / 等）を `claude -p` で causal chain 形式に構造化し、`status='draft'` で `stories` に投入。Hiro が Discord で `!story confirm <id>` して `confirmed` に上げる。

### 抽出

`knowledge/storyteller.py` — 週次で `signals` を **複数の時間軸（直近1週 / 1ヶ月 / 1四半期 / 1年）でそれぞれスキャン**し、`claude -p` に「この期間のシグナル群からストーリー（因果チェーン）になりそうなものを抽出。既存ストーリーの追加証拠なら既存に紐付け、新規なら draft 提案」させる。秋吉AIの「投資家Aの助言は3ヶ月に1回だが必ず実装していて業績に効く → Aには自分から聞きに行け」型のパターンを狙う。時間軸を変えると出るストーリーが変わる（短期 = 戦術、長期 = 構造）。

新規 draft は朝ブリーフィング/Discord で提示。

### スケジュール / コマンド

- 週次: `knowledge_stories`（既存 weekly curator の隣）
- `!stories [confirmed|draft]` / `!story confirm <id>` / `!story archive <id>` / `!story show <id>`

---

## 6. フェーズ4: コンサルmode + プロアクティブアラート（方針）

### 判断の型（decision patterns）

`decision_patterns` テーブル（または `.company/secretary/knowledge/patterns/<slug>.md`）。CLAUDE.md（不可逆操作は確認 / 同じ指摘2回でルール化 / 組織化は未着手仕事の解放 / サイレント故障は実物確認 / …）と `~/.claude/projects/.../memory/feedback_*.md` 群から `claude -p` で「Hiro の意思決定の型 A〜N」を抽出して seed。Hiro が編集・追記できる（Markdown を正にしても良いが、ハイブリッド方針に合わせるなら SQLite + Markdown ビュー）。

### コンサル

Discord `!ask-ceo <相談内容>` → Steve（CEO/秘書）が `decision_patterns` + 関連 `stories`（FTS で相談内容にマッチするもの）+ 最近の `signals` を参照し、次の形で返す:

- 現状 → 課題ギャップ
- 「ここはHiroの型○○に照らすとこう」（型の指摘）
- 段階モデル/役割分担の提案
- 根拠（どのストーリー/シグナルに基づくか）

実装は `tools/council.py` の仕組みの軽量版（マルチエージェント議論はせず、Steve 1名が知見DBを参照して1スレッドで返す）。出力は `.company/meetings/` ではなく `.company/secretary/knowledge/consults/YYYY-MM-DD-<slug>.md` に残す（後でシグナル化される）。

### プロアクティブアラート

`knowledge/alerter.py` — 夜間バッチの最後（`knowledge_stories` がある日はその後、無い日は直近の confirmed stories を使う）に「直近のシグナル群 vs confirmed ストーリーDB」を `claude -p` で照合:

- 「直近のシグナルは『○○という成功ストーリー』の初期パターンに合致している → 今これをやると効く」
- 「直近のシグナルは『△△という失敗ストーリー』の前兆に似ている → 注意」

検出結果を朝ブリーフィングに「⚠️ ストーリーアラート: …」として出す。**採用/却下は人間。AI が自動でアクションを実行することはしない**（CLAUDE.md「不可逆操作は確認」準拠）。`!alerts` で一覧再表示。

---

## 7. フェーズ5: eBay リアルタイム戦略アップデート（別スペック・後日）

フェーズ1〜4 が動いてから別途ブレストする。方針メモのみ:

- d-manager の `knowledge/sources/ebay.py` が「eBay 接触シグナル」を流す: バイヤーが他出品者を検討中 / 失注理由 / リピート購入の予兆 / メッセージから読み取れる不満。
- それを ebay-agent（`products/ebay-agent/`）または b-manager（`products/b-manager/`）側が消費して「次の打ち手」を提案。d-manager は知見の供給源、実行は eBay 側プロダクトの責務（CLAUDE.md のディレクトリ分離）。
- リピーター開拓: リピート購入バイヤーを検出 → フォローアップ（クーポン / 新着案内）のタイミングと文面を提案。送信は人間が承認。
- これは `b-manager.md` / `ebay-agent.md` のメモリと整合させる必要があるので、スペックは d-manager ではなく eBay 側プロダクト配下に置く可能性が高い。

---

## 8. 実装順序

各フェーズで「設計（このスペック） → 実装プラン → 実装 → スモーク/pytest 検証 → 次へ」を1サイクル回す。

1. **フェーズ1（議事録化）** — まずこれだけ実装して走らせ、digest が溜まる手応えを確認
2. **フェーズ2（シグナルDB）** — コアアダプタ（dmanager_log / git / obsidian）から。抽出プロンプトを2週間チューニング。その後 Gmail/Calendar/eBay/ads/freee、最後に Telegram/Plaud
3. **フェーズ3（ストーリーDB）** — フェーズ2 のシグナルが1〜2ヶ月溜まってから
4. **フェーズ4（コンサル/アラート）** — 判断の型を言語化してから
5. **フェーズ5（eBay）** — 別スペック

各フェーズの実装プランは、そのフェーズに着手するタイミングで `writing-plans` で個別に作る。

---

## 9. リスク・留意点

- **コスト**: 夜間バッチで毎日 `claude -p` を複数回（digest はセッション数ぶん、signals は1回、週次で stories）。フェーズ1のフィルタ（ターン数 / 通知ch除外 / コマンドのみ除外）でセッション数を絞る。料金が読めなければ最初は対象チャンネルを限定して開始。
- **サイレント故障**: バッチ失敗を朝ブリーフィングに必ず出す。月1の end-to-end 疎通確認（CLAUDE.md）に「knowledge_digest が前日分を生成しているか」を追加。
- **`.company/` の git 肥大**: digest/signals の Markdown を毎日コミットすると履歴が膨らむ。`.company/` 側で `knowledge/` を `.gitignore` するか、週次でまとめてコミットするか、コミットしない（SQLite が正なので Markdown はビューと割り切る）かを実装時に決める。デフォルトは「コミットしない（`.gitignore` に追加）」を推奨。
- **プライバシー**: digest/signals に機微情報が入りうる。`claude -p` プロンプトのマスク指示に加え、`knowledge.db` と `.company/secretary/knowledge/` は外部に出さない（push しない）。
- **学習ループとの責務分離**: `learning/` = スキル運用の品質改善ループ。`knowledge/` = 経営知見の蓄積。turns を共有するだけで、互いのテーブル・台帳は独立。`learning/store.py` に混ぜない。
