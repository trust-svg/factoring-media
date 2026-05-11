# d-manager 学習ループ — 設計

- 日付: 2026-05-12
- 対象: `products/d-manager/`
- 起点: note記事「OpenClaw / Hermes Agent × Claude Managed Agents」を受けて、Hermes Agent の自己改善ループ（the agent that grows with you）を d-manager に取り込む
- 関連: `.company/research/output/2026-05-08_openclaw-vs-trustlink.md`（Elon の OpenClaw/Hermes 比較。結論「補完関係」）
- ライセンス: Hermes Agent / OpenClaw とも MIT。プロンプトやロジックの移植は出典コメント付きで可

---

## 0. 背景と前提

### d-manager の現状（学習ループに関係する範囲）

- d-manager は通常 **CLIモード**（`ENGINE_MODE=cli` 既定）で動く。`ai_engine._process_cli` が `claude -p`（Claude Code CLI、subscription枠・API課金なし）をサブプロセスで叩く。`cwd=COMPANY_DIR`（=`.company/`）、`--dangerously-skip-permissions`、`--max-turns 20`、`--session-id`/`--resume` でチャンネルごとにセッション継続（`.company/secretary/.cli_sessions.json`、12hアイドルでTTL切れ）。
  - 「中の人」はすでに Read/Write/Edit/Bash を持った Claude Code 本体で、`.company/` の中で動いている。
  - API モード（`_process_api`、Anthropic SDK 直叩き）はフォールバック/異常系（ログに「💰 API MODE FIRED」）。
- 12名のAI社員 / 7部門は CLAUDE.md ペルソナファイルの連結で表現。`departments.load_department_prompt` が `.company/CLAUDE.md` + `.company/<dept>/CLAUDE.md` + `.company/<dept>/agents/*.md` + **全 `.company/skills/*.md`** を system prompt に連結（progressive disclosure 無し）。
- 3階層メモリ `.company/secretary/memory/{raw,facts,digest}/` は `tools/memory.py` に実装があるが、**自動注入されない**（`IDENTITY_PREFIX` で「ここにあるよ」と教えるだけ）。`tools/memory.py` の関数は API tool として公開されていない。
- 既存スケジューラ（APScheduler）: `nightly_commit_review` / `morning_briefing`(7:30) / `evening_review`(21:00) / `weekly_review` / 夜間QA。`.company/` は `nightly_commit_review` が日次コミットしている。
- ミス指導フロー: `IDENTITY_PREFIX` に「2回同じ指摘を受けたら `.company/secretary/rules.md` に追記」が既にある（= 既存の軽量学習ループ）。社訓7「学びを記録せよ」が規範的根拠。
- 知見の蓄積パイプ: `.company/scripts/company-log.sh` → `Company/Logs/YYYY-MM-DD.md` ＋ `--topic` で `{dept}/knowledge/{topic}.md`。
- `tools/agent_call.py` = 同期サブエージェント呼び出し（depth limit 2、synthetic channel `agent-call-{uuid}`）。`council` フロー = マルチエージェント Discord-Thread 議論 → 議事録 `.company/meetings/YYYY-MM-DD_<slug>.md`。

### 学習ループにとってのギャップ（埋めるもの）

1. 会話の直後にその会話から学ぶ「自動振り返り」が無い（あるのは夜間/朝/週次の定型ジョブだけ）。
2. 会話が検索可能な形で永続化されていない（Claude Code セッションは12h TTL、API モードの履歴は揮発）。
3. スキル形式が原始的（フラット単一 .md、全件 system prompt 連結、`references/` 無し）→ スキルが増えるとプロンプトが膨張。**本設計の対象外（Tier B 別サイクル）**だが、本設計はこれを悪化させない。
4. スキル/メモリの定期棚卸し（curator）が無い。
5. メモリが自動注入されない／文字数上限での自己統合が無い／メモリツールが未公開。**本設計の対象外（別サイクル）**。

### スコープの確定

- **やる**: 会話ログの永続化（SQLite+FTS5）、夜間バッチによる振り返りレビュー、`!session reset` での即レビュー、フロー完了時のレビュー登録、週次キュレーター、`.company/` の所定の場所への直接書き込み、`!learning` 系コマンド、段階導入。さらに **(a) スキル肥大メトリクス**（`!learning status` に「スキル数 / 連結時の総文字数 / 増加ペース」を表示、閾値超で Tier B 検討アラート）、**(b) `references/` デュアルローダー**（`departments.py` を「`<name>.md` 従来形式」と「`<name>/SKILL.md` + `references/`（連結しない）」の両対応に。既存スキルの一括移行はしない＝それは Tier B）。(a)(b) は学習ループがスキルを増やす副作用（プロンプト膨張・移行債務）を最初から抑える最小限の前倒し。
- **やらない（別サイクル）**: スキル形式の SKILL.md **一括移行** と progressive disclosure の本格運用・利用統計 `.usage.json`（Tier B）、per-Nターンのリアルタイムレビュー、メモリの自動注入/自己統合、`tools/memory.py` の API tool 化、外部スキル taps。
- **方針**: Hermes の設計思想（the agent that grows with you）に忠実だが、CLIモードでは `claude -p` の spawn が重いので、レビューの発火を「1日1回相当」に間引く（コスト＝subscription レート制限を守る）。「行き先」は Hermes と同じ、間引いた版。

---

## 1. データモデル

新規ディレクトリ `products/d-manager/learning/`。新規 SQLite DB `products/d-manager/learning/conversations.db`（WAL モード）。`.gitignore` に追加（会話ログはコミットしない）。

```sql
-- 1ターン = ユーザー1発言 or エージェント1応答
CREATE TABLE turns (
    id            INTEGER PRIMARY KEY,
    channel_id    TEXT NOT NULL,
    channel_name  TEXT,
    department    TEXT,
    cli_session_id TEXT,                -- .cli_sessions.json のUUID（API/agent-callはNULL）
    turn_idx      INTEGER NOT NULL,     -- そのセッション内連番（0始まり）
    role          TEXT NOT NULL,        -- 'user' | 'assistant'
    content       TEXT NOT NULL,
    engine        TEXT NOT NULL,        -- 'cli' | 'api'
    ts            TEXT NOT NULL         -- ISO8601 (JST)
);
CREATE INDEX idx_turns_session ON turns(channel_id, cli_session_id, turn_idx);
CREATE INDEX idx_turns_chan_date ON turns(channel_id, ts);

-- レビュー台帳。キー = (channel_id, review_date)。「セッション = チャンネル+日付」
CREATE TABLE sessions (
    channel_id    TEXT NOT NULL,
    review_date   TEXT NOT NULL,        -- 'YYYY-MM-DD'（JST）
    channel_name  TEXT,
    department    TEXT,
    origin        TEXT NOT NULL,        -- 'chat' | 'flow:<flow_name>' | 'scheduler:<job>'
    first_turn_at TEXT NOT NULL,
    last_turn_at  TEXT NOT NULL,
    turn_count    INTEGER NOT NULL DEFAULT 0,
    reviewable    INTEGER NOT NULL DEFAULT 1,   -- 0 = agent-call 等、レビュー対象外
    review_status TEXT,                 -- NULL(未) | 'running' | 'done' | 'skipped' | 'error'
    review_started_at TEXT,
    reviewed_at   TEXT,
    review_note   TEXT,                 -- done時=何を書いたか / skipped='too_short' / error詳細
    PRIMARY KEY (channel_id, review_date)
);

-- 日本語部分一致検索（Hermes の messages_fts + trigram に相当）
CREATE VIRTUAL TABLE turns_fts USING fts5(
    content, content='turns', content_rowid='id', tokenize='trigram'
);
-- turns ↔ turns_fts を同期するトリガ（INSERT / DELETE / UPDATE）を併設
```

注記:
- FTS5 trigram は **クエリ3文字未満だとマッチしない**（SQLite 仕様、3.53で確認済み）。`store.search()` はクエリ長 < 3 なら `turns.content LIKE '%q%'` の素朴スキャンにフォールバック、3文字以上は FTS5 trigram。検索はレビュージョブ＋時々の手動参照用なのでフォールバックのフルスキャンで実用上問題なし。
- 「セッション」を `(channel_id, review_date)` で定義することで、`.cli_sessions.json` の12hアイドル判定（無関係な話題が暦をまたいで連結される／毎日触るチャンネルが永久に閉じない問題）を回避する。`cli_session_id` は `turns` 側にだけ残し、参考情報とする。

### 新規モジュール `learning/store.py`

- `record_turn(channel_id, channel_name, department, cli_session_id, role, content, engine, origin, reviewable=True)` — `turns` に1行 append、`sessions` の `(channel_id, today)` 行を upsert（`last_turn_at`/`turn_count` 更新、無ければ `first_turn_at`/`origin`/`reviewable` も）。`turn_idx` は **`(channel_id, review_date)` 内の連番**（cli_session_id は参考メタデータとして列に持つだけ）。
- `prune(retention_days=TURNS_RETENTION_DAYS=180)` — `turns` の `ts` が `retention_days` より古い行を削除（`turns_fts` もトリガで連動削除）。`sessions` 台帳は `review_date` が古くても残す（件数が少ないので。集計・`!learning status` 用）。`weekly_review` から呼ぶ。`learning/skill_hits.jsonl` も同様に古い行を間引く。
- `list_pending_reviews(limit, max_age_days=2)` — `review_status` が NULL かつ `review_date` が今日より前（= その日の活動はもう増えない）かつ `reviewable=1` かつ `turn_count >= MIN_TURNS` の `sessions` 行を、`max_age_days` 以内に絞って返す。
- `requeue_stuck()` — `review_status='running'` かつ `review_started_at` が30分超のものを `review_status=NULL` に戻す（d-manager 再起動でレビューが殺されたケース）。
- `get_session_turns(channel_id, review_date)` — その日のチャンネルの全ターンを `turn_idx`→`ts` 順で返す。
- `mark_review_start(channel_id, review_date)` / `mark_reviewed(channel_id, review_date, status, note)`。
- `search(query, limit=50)` — FTS5（≥3字）/ LIKE（<3字）。`(channel_name, department, ts, role, snippet)` を返す。
- `mark_short_skipped(...)` — `turn_count < MIN_TURNS` で閉じた日を `review_status='skipped', review_note='too_short'`。
- SQLite 接続は per-call open/close（discord.py の async とスレッド跨ぎを避ける。レビュージョブは `loop.run_in_executor` のスレッドから呼ぶ）。

### 書き込み点（`ai_engine.py` への唯一の侵襲）

- `_process_cli` の正常終了直前: `store.record_turn(..., role='user', ...)` と `store.record_turn(..., role='assistant', ...)`。通常のチャンネルは `origin='chat'`、`reviewable=True`。**scheduler 由来チャンネル（`scheduler-*`）は `origin='scheduler:<job>'`、v1 では一律 `reviewable=False`**（morning_briefing は読み上げで学び無し、evening_review/nightly_commit_review は既に自前の出力先がある＝二重記録を避ける）。必要になったら個別ジョブを True に上げるのは後続で。
- `_process_api` も同様（`engine='api'`、`cli_session_id=NULL`）。
- 失敗時（タイムアウト・例外）は記録しない。`record_turn` 自体が例外なら握りつぶしてログのみ（学習ログの失敗で本処理を止めない）。ただし**連続10回失敗**で Discord に1回通知（サイレント化させない、CLAUDE.md「サイレント故障対策」）。

### `agent-call-*` / `council` の扱い

- `tools/agent_call.py` の synthetic channel（`agent-call-{uuid}`）と council の thread は `record_turn(reviewable=False)` で記録（検索対象にはなるがレビュー対象外）。理由: agent-call は一過性の内部呼び出し、council は既に `.company/meetings/` に議事録を残している。
- ただし council フローの**完了時**には `flows.run_flow` 側から「この council 実行をレビュー対象に登録」する（`origin='flow:council'`、議事録ファイルパスも `review_note` の元情報として渡せるように）。

---

## 2. レビュー発火フロー

### 主トリガ: 夜間バッチ（既存 `evening_review` の後ろに相乗り）

新規ジョブ `learning_review`（`scheduler.py` に追加、`CronTrigger(hour=LEARNING_REVIEW_HOUR=23)`、`max_instances=1`、`coalesce=True`）。

```
learning_review() 毎晩23:00:
  if not LEARNING_REVIEW_ENABLED: return            # Phase 1 では false
  store.requeue_stuck()                              # 死んだ running を戻す
  for session in store.list_pending_reviews(limit=LEARNING_MAX_PER_RUN=3):
      run_review(session, dryrun=LEARNING_REVIEW_DRYRUN)
  for session in <turn_count < MIN_TURNS で閉じた日>:
      store.mark_short_skipped(session)              # skipped(too_short) は失敗ではない
  Discord に「今夜の学習ラン: N件レビュー / M件で学びあり / 内容…」を投稿
```

- 1回の実行で最大 `LEARNING_MAX_PER_RUN`(=3) 件まで。残りは翌晩。
- 学びの反映は「その日の夜」まで遅れる（即時ではない）。秒単位の即時性は学習ループに不要、という判断。即時に学ばせたい時は `!session reset`（下記）。

### 即トリガ: `!session reset`

`main.py` の `!session reset` ハンドラから、そのチャンネルの「今日の `sessions` 行」を `run_review` に1件分だけ即キック（`loop.run_in_executor` でバックグラウンド、結果は元チャンネルに返す）。Hiro が明示的にリセットする＝「その話題は終わり／何か上手くいった or 失敗した」のシグナルなので、学びを抜く絶好のタイミング。`.cli_sessions.json` から該当 session の存在を確認できる（このパスだけ `.cli_sessions.json` に依存）。

### 補助トリガ: フロー完了時

`flows.run_flow` の最後（ticket クローズ前後）で、そのフロー実行が使ったチャンネル/スレッドの `sessions` 行を「レビュー対象」にマーク（`origin='flow:<name>'`）。実際のレビューは夜間バッチで拾われる（フロー完了直後に走らせると重い場合があるため。`!session reset` のような即時性は不要）。council は議事録パスも添える。

### `run_review(session_row, dryrun=False)` — `learning/reviewer.py`

```
1. store.mark_review_start(channel_id, review_date)   # review_status='running'
2. turns = store.get_session_turns(channel_id, review_date)
   会話ログを時系列に組み立て:
     "## 会話ログ — {channel_name} / {department} / {review_date}\n[user] …\n[assistant] …\n…"
   フロー由来なら .company/meetings/… や ticket 本文も添える
   LEARNING_CONTEXT_CHAR_LIMIT(=40000) 超なら「先頭20% + 末尾60%、中略マーカー」で詰める
     （末尾＝結論・つまずき解決が出やすいので末尾を厚く）
3. 直近7日に記録済みの学び一覧（Company/Logs/ + memory/{facts,digest}/ から抜粋）をプロンプトに注入（重複防止）
4. claude -p をサブプロセス起動:
     claude -p "<REVIEW_PROMPT 本体 + 会話ログ + 既存学び一覧>"
       --append-system-prompt "<レビュアー人格（最小限）>"
       --model {REVIEW_MODEL_CLI}                    # 既定 = 現行 Sonnet
       --allowedTools "Read Write Edit Glob Grep"     # whitelist。Bash は渡さない
       --disallowedTools "Bash WebFetch WebSearch Task"  # 明示的に blocklist（外部API・サブエージェントを禁止）
       --dangerously-skip-permissions                 # 柵は allowedTools/disallowedTools の方
       --max-turns 15
       cwd = COMPANY_DIR                              # .company/ の中
     timeout = 300s
   dryrun=True の場合: --allowedTools を "Read Glob Grep" に絞る（Write/Edit を外す＝プロンプトだけに頼らない）
     ＋ プロンプトに「ファイルは書くな。何を書く予定だったかを <summary> に詳細列挙せよ」を追加
5. 出力末尾の <summary>…</summary> をパース
6. git -C COMPANY_DIR status --short をログ
   許可宛先（.company/skills/, .company/secretary/memory/, .company/secretary/rules.md,
            .company/<dept>/knowledge/）の外が触られていたら:
     git -C COMPANY_DIR checkout -- <該当> で巻き戻し + Discord警告（どのレビューが暴れたか付き）
7. <summary> が 'done' なら、呼び出し元（run_review）が company-log.sh --topic を必要に応じて実行
   （副作用＝外向き操作は呼び出し元に集約。レビュアー自身は外部API/コマンドを叩かない）
8. store.mark_reviewed(channel_id, review_date, status, note)
   - timeout / 非0終了 / <summary> 無し → status='error'（reviewed_at をセット＝無限再試行を防ぐ）
   - 'no_learnings' → status='done', note='no_learnings: 理由'（失敗ではない、正常終了）
```

### 手動コマンド（`main.py` に追加）

- `!learning status` — 未レビュー/エラー件数、直近のレビュー結果サマリ、`no_learnings` 率（signal/noise の可視化）
- `!learning review <channel> [date]` — 即レビュー（夜間バッチを待たない）
- `!learning retry <channel> <date>` — `error` で終わったレビューを再試行
- `!learning search <query>` — `turns_fts` 検索（Hermes の `session_search` 相当の手動版）
- `!learning curate` — 週次キュレーターを随時起動
- `!learning healthcheck` — 月1疎通確認（下記 §5）

### 設定（`config.py` に追加）

`LEARNING_DB_PATH`, `LEARNING_REVIEW_ENABLED`, `LEARNING_REVIEW_DRYRUN`, `LEARNING_REVIEW_HOUR`(=23), `LEARNING_MIN_TURNS`(=2), `LEARNING_MAX_PER_RUN`(=3), `LEARNING_REVIEW_MAX_AGE_DAYS`(=2), `LEARNING_CONTEXT_CHAR_LIMIT`(=40000), `TURNS_RETENTION_DAYS`(=180), `REVIEW_MODEL_CLI`(既定 Sonnet), `CURATOR_MODEL_CLI`(既定 Opus), `LEARNING_NOTIFY_CHANNEL`(既定 開発チャンネル), `SKILL_BLOAT_CHAR_THRESHOLD`, `SKILL_BLOAT_COUNT_THRESHOLD`.

---

## 3. レビュープロンプトと書き込み先

### レビュアー人格（`--append-system-prompt`、最小限）

- 「あなたは TrustLink の学習レビュアー。12名の人格は持たない。1つの会話ログを読み、再利用価値のある学びだけを `.company/` の所定の場所に書き込む単機能エージェント。」
- 社訓フル注入はしない（軽量化）。社訓1（嘘・捏造禁止）・社訓4（古い情報の使い回し禁止）・社訓7（学びを記録せよ）の3つだけ明示。
- ツールは Read/Write/Edit/Glob/Grep のみ（Bash 無し）。`cwd=.company/` なので相対パスで届く。
- 「ファイル更新以外のことはするな（メール送信・eBay API・広告API・git push 等は禁止）」を明示。

### `REVIEW_PROMPT` 本体（Hermes の `_COMBINED_REVIEW_PROMPT` をベースに移植、MIT・出典コメント付き）

骨子:

1. **タスク**: 「以下は {channel_name}（{department}）で {review_date} に交わされた会話。ここから *次回以降の再現性* につながる学びを抽出し、`.company/` の適切な場所を更新せよ。学びが無ければ何もせず `<summary>no_learnings: 理由</summary>` だけ返せ。」

2. **書き込み先の振り分け**:

| 学びの種類 | 書き込み先 | 形式 |
|---|---|---|
| 再現性のある手順（「Xをやるときはこの順で」） | `.company/skills/<name>.md` | 既存 skill フォーマット（frontmatter: name/owner/trigger + 本文: 使うべき場面/手順/品質チェックリスト/失敗時の対応）。**既存スキルに追記できるなら新規作成しない（Edit優先）** |
| 確定した事実（「クライアントAの請求書は月末締め」） | `.company/secretary/memory/facts/<topic>.md` | `tools/memory.upsert_fact` と同形式（1行ずつ、重複は substring チェック）。**宣言形**で書く |
| 振り返り知見（「この施策はこういう理由で効いた」） | `.company/secretary/memory/digest/<topic>.md` | `## YYYY-MM-DD\n\n{learning}` |
| 「2回以上同じ指摘」級の運用ルール | `.company/secretary/rules.md` | 既存ミス指導フローと同じ追記形式 |
| 部門固有の業務知識 | `.company/<dept>/knowledge/<topic>.md` | 500行超えたら分割（共通ルール準拠）。`company-log.sh --topic` と同じ宛先 |

3. **「保存してはいけないもの」ブロックリスト**（Hermes の "do NOT capture" をほぼそのまま移植）:
   - 環境依存の失敗（APIキー切れ・ネット断・特定マシン固有の事象）→ 自己引用の拒否理由に固めない
   - ツールへの否定的主張（「Xは動かない」を恒久ルール化しない）
   - 一過性のエラー・リトライで直ったもの
   - 一回限りのタスクの語り（「今日Aさんに返信した」自体は記録不要。そこから学んだ *やり方* だけ）
   - 既に `.company/skills/` や `rules.md` に書いてあること（重複）
   - **新しい狭いスキルを作るより、既存の包括スキルにパッチを当てる方を常に優先**
   - メモリ／事実は宣言形（「〜せよ」ではなく「〜である」）

4. **出力契約**: 作業後、必ず `<summary>` を1つ返す。
   - 例: `<summary>done: .company/skills/ebay-research.md に「メルカリ仕入れ時の重複チェック手順」を追記、.company/research/knowledge/ebay-categories.md に新カテゴリ1件を追加</summary>`
   - 例: `<summary>no_learnings: 在庫状況の確認のみで再利用知見なし</summary>`

### モデル

- 日次レビュー: `REVIEW_MODEL_CLI`（既定 = 現行 Sonnet）。「会話ログから再利用できる学びを抜く＋既存スキルに上手くパッチを当てる」は Sonnet が素直に得意。Opus にしても質はほぼ変わらずコスト（subscription枠）だけ増える。大半の会話は `no_learnings` で終わるので Opus は無駄。
- 週次キュレーター: `CURATOR_MODEL_CLI`（既定 Opus）。スキルライブラリ全体を見る繊細な作業で、間違えるとライブラリが壊れる。頻度は月4回だけなので Opus コストは誤差。**高リスク・低頻度＝Opus**。
- 二段構え（Haiku で「学びある？」を選別 → あれば Sonnet で本処理）は **今は作らない**（YAGNI）。単一 Sonnet で回し、`!learning status` の `no_learnings` 率を見て「Sonnet が空振りに浪費されてる」とわかったら、その時にトリアージ段を足す（設計上は将来挟める）。

### `tools/memory.py` の API tool 化

このサイクルではやらない（CLIモードのレビュアーは直接ファイルを書けるので不要）。

---

## 4. 週次キュレーター

既存 `weekly_review` ジョブに1ステップ追加（新規ジョブは作らない）。実体は `learning/curator.py` の `run_curation()`。

```
run_curation():
  1. スナップショット:
     - tar czf .company/skills/.snapshots/skills-YYYY-MM-DD.tar.gz -C .company skills/
       （.snapshots/ は git 管理外。直近8世代だけ残してローテーション）
     - git -C COMPANY_DIR rev-parse HEAD をログ（巻き戻し基準）
  2. claude -p:
       claude -p "<CURATOR_PROMPT + スキル一覧+各冒頭 + 直近90日のヒットしたスキル一覧>"
         --append-system-prompt "<キュレーター人格（最小限）>"
         --model {CURATOR_MODEL_CLI}                 # 既定 Opus
         --allowedTools "Read Write Edit Glob Grep"
         --disallowedTools "Bash WebFetch WebSearch Task"
         --dangerously-skip-permissions
         --max-turns 25
         cwd = COMPANY_DIR
       timeout = 600s
  3. git -C COMPANY_DIR status --short をログ
     範囲外（.company/skills/ と .company/skills/.archive/ 以外）が触られていたら git checkout で巻き戻し + Discord警告
  4. Discord（開発チャンネル）に投稿:
     「今週のスキル棚卸し: 12→9スキル（3件を ebay-research に統合 / 2件を .archive へ / 1件新設）」
     + diff 要約 + コミットハッシュ（Hiro が git revert できるように）
```

### `CURATOR_PROMPT`（Hermes の `CURATOR_REVIEW_PROMPT` をベースに移植、MIT・出典コメント付き）

- 「`.company/skills/` 全体を見て健全性を保つ。やることは3つだけ: (1) 内容が重なる狭いスキルを **クラスレベルの包括スキル** に統合する、(2) 明らかに陳腐化・未使用のスキルを `.company/skills/.archive/` に **移動** する（削除ではない）、(3) frontmatter（name/owner/trigger）が崩れているものを直す。」
- 「**削除はするな。アーカイブ＝移動のみ**。判断に迷ったら触るな（保守的に）。」
- 「統合するときは、元スキルの手順・品質チェックリスト・失敗時の対応を **取りこぼさず** 包括スキルに織り込む。統合後に元ファイルを `.archive/` へ。」
- 「`.company/skills/README.md` のスキル一覧も実態に合わせて更新する。」
- 「1回の棚卸しで触るスキルは **最大5件まで**（一気にやらない）。残りは来週。」
- 出力契約: 末尾に `<summary>before=12 after=9 merged=[…] archived=[…] created=[…] fixed=[…]</summary>`

### 「使われていない」の判定材料（安価版）

`run_review`（日次）が「このセッションでどのスキルが参照された/役立った」を `learning/skill_hits.jsonl`（`{skill, channel, date}` 1行）に追記。キュレーターのプロンプトに「直近90日でヒットしたスキル一覧」を注入する。ヒット記録が無い＝最近使われていない候補（あくまで判断材料、即アーカイブではない）。`.usage.json` 方式のちゃんとした利用統計は Tier B（SKILL.md化）の時に。

### 頻度

週次（`weekly_review` 相乗り）のみ。Hermes の「2hアイドルでも」は d-manager に「アイドル検出スキャナ」を足すことになるので採らない。`!learning curate` で随時起動可。

### git 管理

- `.company/skills/.archive/` は git 管理に含める（いつ何をアーカイブしたか git log で追える）。
- `.company/skills/.snapshots/*.tar.gz` は git 管理外（バイナリ・一時的）。

---

## 4.5 スキル肥大対策（Tier B からの最小前倒し）

学習ループは `.company/skills/` を増やす機能なので、その副作用（`departments.py` の全件連結プロンプトが膨張する／後の Tier B 一括移行の債務が増える）を最初から抑える最小限だけを前倒しする。Tier B 本体（全スキル移行・利用統計 `.usage.json`・progressive disclosure の本格運用・外部スキル tap）は別サイクルのまま。

### (a) スキル肥大メトリクス

- `!learning status` に「スキル数 / `departments.load_department_prompt` で連結したときの skills 部分の総文字数 / 直近30日のスキル数・総文字数の増加ペース」を表示。
- 閾値（例: skills 連結総文字数 ≥ `SKILL_BLOAT_CHAR_THRESHOLD`、または月 + `SKILL_BLOAT_COUNT_THRESHOLD` 件）を超えたら、夜間 `learning_review` の Discord 報告に「⚠️ スキルライブラリが膨らんでいます（現在 N 件 / M 文字）。Tier B（SKILL.md化・progressive disclosure）の検討時期です」を出す。
- 集計は `learning/skill_hits.jsonl`（§4「使われていないの判定材料」と同じファイル）＋ `.company/skills/` の実ファイルサイズから。実装 ~20-30 LOC。

### (b) `references/` デュアルローダー

- `departments.load_department_prompt` を「2形式併存」に変更:
  - 従来形式: `.company/skills/<name>.md` → 従来どおり全文を system prompt に連結。
  - 新形式: `.company/skills/<name>/SKILL.md` が存在する場合 → **`SKILL.md` の本文だけ**連結する。同ディレクトリの `references/*.md` は**連結しない**（`SKILL.md` 本文に「詳細は `references/X.md` を参照（必要なら Read せよ）」と書いてあるだけ）。
  - 同名で両方ある場合は新形式（`<name>/SKILL.md`）を優先。
- 既存6スキルの一括移行はしない（それは Tier B）。**レビュアー（§3）と キュレーター（§4）が、かさばる内容の新規スキルを作る／統合する時だけ新形式を使う**ようプロンプトで指示する。具体的には「スキル本文が概ね 80-100 行を超えそうなら、手順の骨子だけ `SKILL.md` に残し、詳細な手順・サンプル・チェックリストの長い版は `references/` に分けよ」。
- これにより、学習ループがスキルを増やしてもプロンプト膨張が抑えられ、Tier B の一括移行も「`## References` 的な肥大スキルを `references/` に切り出す」だけの機械的作業で済む。実装 ~50-80 LOC（ローダー + プロンプト1段落 + テスト）。

---

## 5. エラー処理・テスト・ロールアウト

### エラー処理（CLAUDE.md「サイレント故障対策」準拠 — 黙って動き続けない）

| 失敗点 | 挙動 |
|---|---|
| `turns` への記録が例外 | ログのみ、本処理は止めない。**連続10回失敗で** Discord に1回通知 |
| `learning_review` ジョブ自体が例外 | APScheduler のジョブ例外ハンドラでキャッチ → Discord通知 + 翌夜再実行（`reviewed_at` 未セットなので拾い直される） |
| `claude -p`（レビュー）が timeout(300s) | `review_status='error', review_note='timeout'`、`reviewed_at` セット（無限再試行防止）。`!learning retry` で手動再試行 |
| `claude -p` が非0終了 / `<summary>` 無し | `review_status='error'`、stderr 末尾をログ・`review_note` に保存 |
| レビュアーが範囲外を書いた | `run_review` 後の `git status` 差分チェックで検出 → `git checkout -- <該当>` で巻き戻し → Discord警告（どのセッションのレビューが暴れたか付き） |
| レビュー中に d-manager 再起動 | `review_status='running'` のまま残る → 次回 `learning_review` 起動時に `requeue_stuck()`（`running` かつ30分超 → NULL に戻す） |
| 週次キュレーターが暴れた / 失敗 | 範囲外チェックで巻き戻し or `tar.gz` スナップショットから復元手順を Discord に提示。コミットハッシュ添付で `git revert` 可能に |
| `.cli_sessions.json` が読めない | 致命的でない（夜間バッチは `turns` テーブルから対象を割り出す。`!session reset` 即レビュー経路だけ使えなくなる）→ ログのみ |

### 月1の end-to-end 疎通確認（CLAUDE.md 準拠）

`!learning healthcheck` — ダミー会話を `turns` に入れて `run_review`（dryrun）を即実行し、`<summary>` が返るまで通るか確認 → Discord に合否。`weekly_review` の月初回に自動実行する案も（任意）。

### 既知の制約（v1 で許容するもの）

- **in-bounds の同時書き込み競合**: レビュアー/キュレーターが `.company/skills/X.md` 等を編集している最中に、別チャンネルの本処理エージェントが同じファイルを編集すると競合し得る。「範囲外書き込みの自動 revert」は許可宛先内の競合までは捕まえない。発生確率は低く（レビューは夜間に集中、本処理は日中が中心）、`run_review`/`run_curation` 後の `git status --short` ログで事後に気づける。本格的なロックは v1 ではやらない。
- **長期ダウン時の取りこぼし**: d-manager が `TURNS_RETENTION_DAYS` 近く（既定180日）止まることは想定しないが、`list_pending_reviews` は `max_age_days`（既定2日）より古いセッションを拾わない。数日の停止なら、その間のセッションは振り返られない（古い会話は学び価値が低いとして許容）。`max_age_days` は config 可変。
- **scheduler 由来の学び**: v1 では `scheduler-*` セッションを `reviewable=False` にしているため、夜間ジョブ（evening_review 等）の中で生まれた知見は学習ループでは拾わない（それらは元々 Discord 投稿や自前ファイルに出力されている）。必要なら後続サイクルで個別に対象化。

### テスト — `products/d-manager/tests/test_learning.py`（pytest）

- `store.py`: `record_turn`→`get_session_turns` の往復、`turn_idx` が `(channel_id, review_date)` 内連番になること、`turns_fts` 検索（trigram ≥3字 / <3字 LIKE フォールバック）、`list_pending_reviews`（今日の分は対象外・`max_age_days` 超過は対象外）、`mark_reviewed`、`(channel_id, review_date)` upsert、`reviewable=False` が `list_pending_reviews` に出ないこと、`requeue_stuck`、`prune`（古い `turns` と `turns_fts` 連動削除、`sessions` 台帳は残ること）
- `reviewer.py`: subprocess を**モック**して — (a) `<summary>done: …>` → `mark_reviewed(done)`、(b) `<summary>no_learnings>` → `mark_reviewed(done, no_learnings)`、(c) timeout → `error`、(d) `<summary>` 無し → `error`、(e) git status に範囲外 → `git checkout` が呼ばれること、(f) dryrun で `--allowedTools` から Write/Edit が外れ、プロンプトに「書くな」指示が入ること、(g) `--disallowedTools` に Bash が含まれること
- `departments.py`: `<name>.md` のみ → 従来どおり全文連結、`<name>/SKILL.md` あり → 本文だけ連結し `references/*.md` は連結しない、両方ある → 新形式優先、スキル連結総文字数を返す補助関数
- `scheduler.learning_review`: `turns` に当日分（実際は前日扱いに）を仕込む → 対象が正しく抽出、`turn_count < MIN_TURNS` は `skipped(too_short)`、1回 `LEARNING_MAX_PER_RUN` 件まで、`LEARNING_REVIEW_ENABLED=false` で何もしない
- `curator.py`: subprocess モックで `<summary>` パース、範囲外 revert、スナップショット作成（tmpdir）、8世代ローテーション
- `!learning status`: スキル肥大メトリクス（件数・総文字数・増加ペース）が出ること、閾値超でアラート文言が付くこと
- 既存 `ai_engine` テストが壊れていないこと（`_process_cli`/`_process_api` に `record_turn` を1行足すだけ。`record_turn` をモックすれば既存テストは無傷のはず）

### ロールアウト（段階導入）

`.company/` を AI が自動で書き換える機能なので、いきなり本番は危険。

1. **Phase 1 — 観測のみ**: `turns` 記録だけ有効化。`learning_review` ジョブは登録するが `LEARNING_REVIEW_ENABLED=false` で実行しない。数日〜1週間、会話ログが正しく溜まるか・容量増加ペース・`reviewable` の振り分けが妥当かを `!learning status` / `!learning search` で確認。
2. **Phase 2 — ドライラン**: `LEARNING_REVIEW_DRYRUN=true`。`run_review` は実行するが「ファイルは書くな、何を書く予定だったかを `<summary>` に詳細列挙せよ」。`.company/` は無変更。Discord に「もし本番なら〇〇に△△を書いていた」が出る → Hiro が「その学び要る/要らない」を見てプロンプト（特に「保存してはいけないもの」リスト）を調整。1週間。
3. **Phase 3 — 本番**: `LEARNING_REVIEW_ENABLED=true`、ドライラン解除。最初の数回は範囲外チェック＆git diff を毎回 Discord に流して目視。安定したら通知を「学びがあった時だけ」に絞る。
4. **Phase 4 — キュレーター**: 日次レビューが2〜3週間安定稼働してスキルが何件か増えてから、`weekly_review` にキュレーターステップを追加（先に増やしてから棚卸しを足す順）。

### `.gitignore` 追加

```
products/d-manager/learning/*.db
products/d-manager/learning/*.db-wal
products/d-manager/learning/*.db-shm
products/d-manager/learning/skill_hits.jsonl
.company/skills/.snapshots/
```

---

## 6. 新規/変更ファイル一覧

新規:
- `products/d-manager/learning/__init__.py`
- `products/d-manager/learning/store.py` — SQLite ラッパ（§1）
- `products/d-manager/learning/reviewer.py` — `run_review()` ＋ `REVIEW_PROMPT`（§2, §3）
- `products/d-manager/learning/curator.py` — `run_curation()` ＋ `CURATOR_PROMPT`（§4）
- `products/d-manager/tests/test_learning.py`（§5）
- `products/d-manager/docs/specs/2026-05-12-learning-loop-design.md`（本書）

変更:
- `products/d-manager/ai_engine.py` — `_process_cli` / `_process_api` の正常終了時に `store.record_turn` を2行（user/assistant）。連続失敗カウンタ。
- `products/d-manager/scheduler.py` — `learning_review` ジョブ追加（23:00）、`weekly_review` に `run_curation()` ＋ `store.prune()` ステップ追加、ジョブ例外ハンドラ。
- `products/d-manager/flows.py` — `run_flow` 完了時にそのセッションをレビュー対象にマーク、council は議事録パスを添える。
- `products/d-manager/main.py` — `!session reset` ハンドラから即レビューをキック、`!learning` コマンド群（status/review/retry/search/curate/healthcheck）。`status` にスキル肥大メトリクス（§4.5a）。
- `products/d-manager/departments.py` — `load_department_prompt` を `references/` デュアルローダー化（§4.5b）。`<name>/SKILL.md` があれば本文だけ連結、`references/` は連結しない。既存 `<name>.md` 形式は従来どおり。スキル連結総文字数を返す補助関数（メトリクス用）。
- `products/d-manager/config.py` — `LEARNING_*`（`LEARNING_DB_PATH` / `LEARNING_REVIEW_ENABLED` / `LEARNING_REVIEW_DRYRUN` / `LEARNING_REVIEW_HOUR` / `LEARNING_MIN_TURNS` / `LEARNING_MAX_PER_RUN` / `LEARNING_REVIEW_MAX_AGE_DAYS` / `LEARNING_CONTEXT_CHAR_LIMIT` / `LEARNING_NOTIFY_CHANNEL`）/ `TURNS_RETENTION_DAYS` / `REVIEW_MODEL_CLI` / `CURATOR_MODEL_CLI` / `SKILL_BLOAT_CHAR_THRESHOLD` / `SKILL_BLOAT_COUNT_THRESHOLD`。
- `.gitignore` — 上記。

範囲外（別サイクル）: Tier B 本体（`.company/skills/*.md` の **一括** `<name>/SKILL.md` 化 + progressive disclosure の本格運用 + 利用統計 `.usage.json` + 審査ゲート付き外部スキル tap）、メモリ自動注入/自己統合、`tools/memory.py` の API tool 化、per-Nターンのリアルタイムレビュー。※ 本設計には Tier B の「最小前倒し」（§4.5: 肥大メトリクス + `references/` デュアルローダー）だけ含まれる。

---

## 7. 元記事との対応（何を取り込み、何を見送ったか）

| 元記事 / Hermes・OpenClaw の要素 | 本設計での扱い |
|---|---|
| Hermes の自己改善ループ（会話を振り返って skill/memory を自動更新） | **取り込む**（§2, §3）。発火は per-Nターン → 「1日1回相当」に間引き（CLIモードの spawn コスト対策） |
| Hermes の "do NOT capture" ブロックリスト・宣言形メモリ | **取り込む**（§3）。MIT・出典コメント付きで移植 |
| Hermes の curator（狭いスキルを上位に統合・古いものをアーカイブ・スナップショット） | **取り込む**（§4）。週次（`weekly_review` 相乗り）のみ |
| Hermes の state.db（SQLite + FTS5 + trigram で日本語部分一致）・session_search | **取り込む**（§1）。`!learning search` が手動版 session_search |
| Hermes の per-Nターンのリアルタイム背景レビュー | **見送り**。CLIモードでは `claude -p` spawn が重く、忙しい日に20〜40回の余分な呼び出しになり subscription レート制限に直結。`!session reset` 即レビューでオンデマンドの即時性は確保 |
| Hermes/OpenClaw の SKILL.md 形式・progressive disclosure・references/ | **最小前倒し**（§4.5）: `departments.py` を `<name>/SKILL.md` + `references/`（連結しない）にも対応させ、肥大メトリクスを `!learning status` に出す。既存スキルの**一括移行・利用統計・本格運用は別サイクル（Tier B）**。本設計は新規スキルが肥大化しそうなら最初から `references/` に分けさせ、プロンプト膨張と移行債務を抑える |
| Hermes の MEMORY.md/USER.md 常時注入・文字数上限での自己統合 | **別サイクル**。本設計はメモリ「書き込み」だけ整え、「自動注入」は触らない |
| OpenClaw の ClawHub / agentskills.io（コミュニティスキル取り込み） | **見送り**。無審査の外部スキル取り込みは Workspace のセキュリティ方針（非公式スキルは差分確認必須）に反する。必要なら審査ゲート付きで別サイクル |
| OpenClaw の "dreaming" メモリ統合 | curator（§4）がスキル側の "dreaming" 相当。メモリ側の統合は別サイクル |
