# ヤフオク入札予約アプリ (yahoo-auction-reserve)

ヤフオクの商品ページURLを登録しておくと、**終了直前に自動で入札する**(スナイプ入札)Webアプリ。
設計の正は [`docs/yahoo-auction-reserve-app/DESIGN.md`](../docs/yahoo-auction-reserve-app/DESIGN.md)、
競合調査は [`COMPETITORS.md`](../docs/yahoo-auction-reserve-app/COMPETITORS.md)。

> [!WARNING]
> **実入札を通したのは 2026-08-29 の1件(11円)だけ。連続稼働の実績は無い。**
> `apps/worker/src/bidder/selectors.ts` の P0 検証(設計 §13)の進捗:
> `loginLink` / `bidButton` / `priceInput` / `bidConfirmButton` / `bidSubmitButton` は
> 実測で確定済み(✅)。確定クリックまで押して `placeBid` が SUCCESS を返し、
> `<h1>あなたが最高額入札者です</h1>` を読み戻すところまで取れている。
> 勝敗判定は**入札履歴ページ**で行う(終了後の商品ページには何も出ない。設計 §13)。
> ⚠️ ただし **自分が落札した側の入札履歴はまだ見ていない**(その1件は競り負けた)。
> WON 側の判定は他人の行を陽性対照にして組んである。
> どれが確定済みかは `selectors.ts` 冒頭の表が正(README より表を信じること)。
> P0 検証は人手で実施する。CI や自動テストからヤフオクへ実アクセスしないこと。
> **経路の確認は「テスト実行」(下記)で、実入札ゼロのまま予約〜通知まで通せる。**

## 構成

| ワークスペース | 役割 |
|---|---|
| `apps/web` | Next.js 15 (App Router)。画面 + `/api/v1/*` の Route Handler |
| `apps/worker` | BullMQ ワーカー + スケジューラ。商品情報の更新と入札実行(Playwright) |
| `packages/db` | Prisma スキーマ / PrismaClient |
| `packages/shared` | 定数・型・ヤフオクページのパーサ・Cookie正規化・暗号化 |

予約の真実は DB (`BidReservation`)。Redis 上のジョブはスケジューラが 30 秒ごとに
DB から再構築するため、Redis 消失や worker 再起動から自己修復する(設計 §4, §7.3)。

## 必要環境

- Node.js **22 以上**(`engines.node: >=22`)
- Docker / Docker Compose(PostgreSQL・Redis・本番相当の起動確認に使用)

## 環境変数

`.env.example` をコピーして `.env` を作る。`.env` は git 管理外。

| 変数 | 用途 | 例・生成方法 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 接続先 | `postgresql://yar:yar@localhost:5432/yar` |
| `REDIS_URL` | Redis 接続先 | `redis://localhost:6379` |
| `AUTH_SECRET` | ログインセッション JWT の署名鍵 | `node -e 'console.log(require("crypto").randomBytes(32).toString("base64"))'` |
| `COOKIE_ENCRYPTION_KEY` | ヤフオク Cookie の AES-256-GCM 暗号鍵。**base64 で厳密に 32 バイト** | 同上 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | 通知メール送信(任意) | 未設定ならメール送信はスキップされ、通知内容は worker のログに出る |
| `MAIL_FROM` | 通知メールの From | `yar@example.com` |
| `TELEGRAM_BOT_TOKEN` | Telegram 通知・増額承認ボタンの Bot トークン(任意) | @BotFather で**新規に**作成。未設定なら Telegram 経路はスキップ |
| `CHROMIUM_EXECUTABLE_PATH` | Playwright が使う Chromium の明示指定(任意) | Docker イメージ同梱のものを使う場合は不要 |
| `ALLOW_REGISTRATION` | 新規登録の開閉(任意) | `true` のときだけ開く。**未設定なら利用者0人のときだけ許可**され、1人登録された時点で自動的に閉じる |

> `COOKIE_ENCRYPTION_KEY` を変更すると **保存済みの連携 Cookie は全て復号できなくなる**。
> 鍵を入れ替えたら `YahooSession` を作り直すこと。

`.env` はモノレポのルートに1つだけ置く。docker compose は `env_file: .env` で読み、
ローカル実行時は以下がそれぞれ起動時に読み込む。**既に定義済みの環境変数は上書きしない**
ので、compose の `environment:` で渡す `DATABASE_URL` / `REDIS_URL` が常に優先される。

| 実行経路 | 読み込み口 |
|---|---|
| `npm run dev:worker` / `npm run p0:probe` | `apps/worker/src/env.ts`(最初の import) |
| `npm run dev:web` / `build` / `start` | `apps/web/next.config.ts` |
| `npm run db:push` / `db:generate` | `scripts/with-root-env.mjs`(Prisma CLI のラッパ) |

> Prisma CLI は cwd(`packages/db`)から `.env` を探すため、ルートの `.env` には
> 自力では届かない。`packages/db` の npm script を直に `prisma db push` へ戻すと、
> **compose では動くのに `npm run db:push` だけ `Environment variable not found` で落ちる**。

> compose は `DATABASE_URL` / `REDIS_URL` をサービス名(`postgres` / `redis`)で上書きするため、
> `.env` 側にはローカル実行用の `localhost` を書いておけばよい。この2つが `.env` に無いと
> **docker では動くのにローカルの `npm run db:push` / `dev:worker` だけ落ちる**。

## セットアップ(ローカル開発)

```bash
cd yahoo-auction-reserve
cp .env.example .env      # 上表に従って値を埋める
npm install

# PostgreSQL / Redis だけ起動
docker compose up -d postgres redis

# スキーマ適用 + PrismaClient 生成
npm run db:push

# 別ターミナルでそれぞれ起動
npm run dev:web           # http://localhost:3000
npm run dev:worker
```

型チェックとテストは全ワークスペース一括:

```bash
npm run typecheck
npm test
```

テストは DB も Redis もヤフオクも要らない純粋関数だけを対象にしている
(`packages/shared` のスナイプ実行タイミング計算・入札単位・判断材料の判定・
落札相場のパース)。**このテストは「壊したら落ちる」ことを確認済み**で、
`monitorLeadSeconds` を旧実装の固定値 90 に戻すと 5 件中 3 件が落ちる。
判断材料側も同じ確認を取ってある(`judgeSeller` の `unknown` を `ok` に丸める /
送料不明を 0 として足す / `median([])` が 0 を返す、のいずれもテストが落ちる)。
**落ちないテストを足さないこと。**

## 一式を Docker で起動

```bash
docker compose up -d --build          # postgres / redis / web / worker
docker compose exec web npx prisma db push --schema packages/db/prisma/schema.prisma
docker compose logs -f worker
```

`web` は http://localhost:3000 。停止は `docker compose down`(データも消すなら `-v`)。

> `apps/worker/package.json` の `playwright` と `apps/worker/Dockerfile` の
> `PLAYWRIGHT_VERSION` は**必ず同じバージョンに固定**する。ズレるとブラウザ実体が
> 見つからず、**入札実行の瞬間にだけ**失敗する。

## 使い方

1. `/register` でアカウント作成 → `/login`
2. `npm run yahoo:cookies` で Cookie を取得 → `/settings/yahoo` に貼り付けて連携を登録
3. `/reservations/new` で商品URLを貼り付け → プレビュー → 上限額・実行タイミングを入力 → **確認ステップ**で確定
4. `/dashboard` で予約一覧、`/reservations/<id>` で入札試行のタイムラインを確認
5. `/watchlist` でヤフオクのウォッチリストから直接予約(60分ごとに取り込み・一方向)
6. `/settings` から通知(`/settings/notifications`)と判断材料(`/settings/judgement`)を設定

### テスト実行(実際には入札しない)

予約の作成画面と詳細画面に **「テスト実行にする」** のチェックがある。
入れておくと、予定時刻に本番と全く同じ経路で動き、**最後の確定ボタンだけ押さない**。

```
予約登録 → スケジューラ → 終了N秒前に worker が起動 → Cookie 復号 → セッションロック
  → 入札ボタン → 入札額入力 → 確認画面へ → 【4点ガード】 → ここで止まる → 通知
```

確かめられるのは、**予定時刻に本当に動いたか**・予定との遅れ(秒)・Cookie が生きているか・
入札額が最低入札価格を満たしているか・確認画面に到達できるか・通知が届くか。
確かめられないのは確定ボタンを押した先だけで、そこは実入札1件でしか埋まらない。

- 結果は予約の状態が `テスト実行(入札していません)` になり、Telegram にも必ず届く
  (結果通知を切っていても届く。静かに終わると「動いていない」と区別が付かないため)
- 確認画面に着けなかった場合は `DRY_RUN` にならず **失敗として** 記録される。
  つまり `DRY_RUN` が返ったなら4点ガードを全部通っている
- フラグは**予約ごと**。環境変数の全体スイッチにしていないのは、切り忘れ(全予約が空振り)と
  入れ忘れ(実入札が飛ぶ)がどちらも全件に効いてしまうため
- 待機中(`SCHEDULED`)の間は詳細画面から後付けで切り替えられる

⚠️ **テスト実行では落札できない。** 本番のつもりでチェックを入れたままにすると、
予定時刻に静かに何もせず終わる。ダッシュボードの行頭に `テスト` の札が出るので、
入札させたい予約に札が付いていないか確認すること。

### ヤフオク Cookie の取得について

ログイン維持に使う Cookie (`T` / `Y` / `SSL`) は **httpOnly** のため、
ブックマークレットや `document.cookie` では取得できない。付属のヘルパーを使う:

```bash
npm run yahoo:cookies
```

まっさらな Chromium が1つ開くので、そこで Yahoo! JAPAN にログインし
(2段階認証もそのウィンドウで済ませる)、ターミナルへ戻って Enter を押す。
`yahoo.co.jp` の Cookie だけがクリップボードへ入るので、`/settings/yahoo` の
テキストエリアに貼り付けて登録する。**Cookie の値は画面にもファイルにも出さない**
(取得できた名前・ドメイン・失効時刻の表だけ出る)。普段使いの Chrome の
プロファイルには触らないので、Cookie 編集系のブラウザ拡張を入れる必要はない。

クリップボードが使えない環境では `npm run yahoo:cookies -- --print` で
標準出力に出せる(この場合は値が画面に出るので扱いに注意)。

貼り付けられた JSON はサーバ側で正規化され(`*.yahoo.co.jp` 以外は破棄、
`sameSite` / 有効期限を Playwright が受け付ける形へ変換)、認証用 Cookie が
欠けている場合は警告を返す。Cookie 本体は AES-256-GCM で暗号化して保存し、
**API レスポンス・ログには一切出さない**(設計 §8)。

## 通知と自動増額 (Telegram)

worker は 30 秒ごとの走査で以下を回す。いずれも DB を真実とするので、Redis 消失や
worker 再起動から自己修復する(BullMQ の遅延ジョブに載せていないのは、載せると
再起動で消えたリマインドが**二度と来ないのに正常に見える**ため)。

| 走査 | 間隔 | 中身 |
|---|---|---|
| `scanOnce` | 30秒 | 予約から refresh / monitor ジョブを再構築 |
| `runReminderSweep` | 30秒 | 終了 N 分前のリマインド(`ReminderSent` の一意制約で二重送信を防ぐ) |
| `runDailySummarySweep` | 30秒 | 設定時刻を過ぎたら当日分の稼働サマリを1回だけ送る |
| `sweepApprovals` | 30秒 | 期限切れの承認依頼を TIMEOUT にする(押されないボタンで増額が永久に詰まるのを防ぐ) |
| `runEnrichSweep` | 30秒 | 未取得の予約に落札相場を後追いで入れる(1回5件。失敗しても `marketCheckedAt` は進める) |
| `runWatchlistSweep` | 60分 | ヤフオクのウォッチリストを取り込む(一方向・Yahoo → アプリ) |
| `runVerifySessionSweep` | 15分 | 連携 Cookie の生存確認。実際に開くのは前回試行から6時間経った連携だけ(1回3件) |

これとは別に、増額承認ボタンの受け口として `startApprovalPoller()` が
`getUpdates` の長時間ポーリングを1本張る。

### Bot の用意

1. Telegram の @BotFather で **新規に** Bot を作る(既存 Bot の使い回しは不可。下記)
2. 発行されたトークンを `.env` の `TELEGRAM_BOT_TOKEN` に入れる
3. 作った Bot に自分から1通送り、`https://api.telegram.org/bot<token>/getUpdates` の
   `message.chat.id` を控えて、通知設定の `telegramChatId` に登録する

> [!WARNING]
> **`getUpdates` は 1 Bot につき消費者1つだけ**。同じトークンを他のツールでも
> ポーリングしていたり、その Bot に webhook が設定されていると 409 Conflict になり、
> **通知は届くのに承認ボタンだけ無反応**という形で出る(押しても何も起きない)。
> worker のログに 409 の警告が出るので、出たら消費者が二重になっていないか確認する。

> [!IMPORTANT]
> `.env` を編集したら **`docker compose up -d web worker`(作り直し)** で反映する。
> `docker compose restart` では環境変数を読み直さない —— 既存コンテナをそのまま
> 起動し直すだけなので、`.env` に入れたトークンが無いまま `telegram=off` で立ち上がり、
> **設定したつもりで通知だけ飛ばない** 状態が続く。反映できたかは worker の起動ログ
> (`[worker] started: ... telegram=on`)で確かめること。web も `TELEGRAM_BOT_TOKEN` を
> 見ている(設定画面の未設定警告)ので両方作り直す。

`TELEGRAM_BOT_TOKEN` 未設定でも動作する(Telegram 経路がスキップされ、メールとログだけになる)。
その場合 **承認制の自動増額は成立しない** — 承認依頼を送れないので増額しない側に倒れる。

### 自動増額の安全側の倒れ方

`autoRaiseMode` が `AUTO` なら即時、`APPROVAL` なら Telegram のボタンで承認された時だけ
上限額を引き上げる。以下はすべて「増額しない」に倒れる: 絶対上限 `absoluteMaxAmount` 到達 /
回数 `autoRaiseMaxCount` 使い切り / 承認の無回答・拒否・送信失敗 / 増額してもなお
現在価格の次の入札単位に届かない(= 増額しても負ける額)。

承認は**入札直前ではなく価格更新を見た時点(refresh)で聞く**。入札直前(既定 T-30秒)に
聞いても人間が答える時間が無く、必ずタイムアウトするため。承認の締切は予約の編集締切
(= monitor 起動の手前)に合わせてある。

## 判断材料(送料・落札相場・出品者評価)

予約の一覧と確認画面に、入札額を決めるための材料を出す。**取れなかった項目は
空欄にせず「取得できませんでした」と書く**(空欄は「送料無料」「評価に問題なし」と読まれる)。

| 項目 | いつ取るか | 未取得のときの扱い |
|---|---|---|
| 送料 | 商品情報の取得時。`refresh` で未取得のものだけ後追い補完 | `null`。**0(送料無料)と混同しない**。総額は出さず「送料不明」と表示 |
| 出品者の評価(%・件数) | 同上 | `null`。足切り判定は `unknown` になり、**ブロックはしない** |
| 落札相場(中央値・母数) | worker の `runEnrichSweep` が後追い(1回5件) | 母数 `0` = 該当なし、`null` = 取得失敗。表示しないだけ |

`/settings/judgement` で出品者の足切りを設定できる(既定は未設定 = 判定しない)。
条件に該当したときの挙動は「警告のみ」が既定で、`blockLowRatedSeller` を ON にすると
登録自体を断る。**評価が読み取れなかった商品は ON でもブロックしない** —
パーサが壊れた日に全部の予約が登録不能になるのを避けるため。

> [!WARNING]
> 送料・評価・落札相場のセレクタと `closedsearch` の URL は **P0 未検証のプレースホルダ**。
> 実ページで確認するまで「取れない項目がある」前提で扱うこと。取れなければ表示が
> 消えるだけで、予約の登録・実行そのものは止まらない設計にしてある。

### グループ予約

同じグループに束ねた予約は、**1件落札した時点で残りを自動で取りやめる**
(「同じレンズをA店・B店で押さえたが欲しいのは1本」用)。予約登録画面で
既存グループの選択か新規作成ができる。

取りやめるのは待機中・監視中のものだけで、**既に入札実行中(`BIDDING`)のものには
触らない**。こちらが取り消しても向こうで入札が成立している可能性があり、
取り消せたつもりで二重落札するため。飛ばした分は警告ログと通知に必ず出る。

## P0 検証プローブ

`apps/worker/src/bidder/selectors.ts` のセレクタを実ページで埋めるための道具
(設計 §13)。**実行するのは人間**。CI や worker からは呼ばない。

```bash
# 事前に一度だけ(ローカルの Chromium を取得。バージョンは playwright に一致させる)
npx playwright install chromium

# Stage 1: 商品ページを開いて読むだけ。クリック・入力は一切しない
npm run p0:probe -- 'https://page.auctions.yahoo.co.jp/jp/auction/xxxxx'

npm run p0:probe -- '<URL>' --headless        # bot検知の比較用(§13-4)
npm run p0:probe -- '<URL>' --anonymous       # 未ログインの対照(下記)
npm run p0:probe -- '<URL>' --watch 20        # 終了間際に張り付いて自動延長を観測(§13-3)
npm run p0:probe -- '<URL>' --session '<連携ラベル or id>'

# ウォッチリストの URL 候補とセレクタを確定させる(商品URL不要)
npm run p0:probe -- --watchlist
npm run p0:probe -- --watchlist --anonymous    # ログイン壁(watchlistLoginWall)の陽性対照
```

`--watchlist` は `WATCHLIST_URL_CANDIDATES` を順に開き、候補セレクタの当たりに加えて
**本番と同じ `scrapeWatchlistPage()` の返り値**(`OK` / `SESSION_EXPIRED` / `UNPARSEABLE`)を
レポートに書く。プローブ用の別ロジックで判定すると、本番コードだけ外れたままでも
「当たった」と読めてしまうため。商品リンクが実在するのに `UNPARSEABLE` なら
`watchlistItemLink` が外れている、と切り分けられる。

出力は `tmp/p0/<auctionId>-<timestamp>.md` と同名の `.png`(git 管理外)。中身は

- 使用した連携の **Cookie 名と失効時刻**(値は出さない)。§13-1 の実測はこれを日をおいて取る
- 候補セレクタの総当り結果(どれが当たったか / 全滅か)
- **当たった候補の実体** — 当たった要素の tag / id / class / href。ここまで見ないと
  「当たってはいるが別の要素」を見抜けない(下記)
- **実物ダンプ** — 可視のクリック要素・input・data-testid の一覧。候補が全滅したときはここから拾う
- パーサ結果(終了時刻・現在価格・自動延長)

> [!IMPORTANT]
> **見出しの ✅ を鵜呑みにして `selectors.ts` へ写さないこと。**
> 2026-08-24 の実測で `a[href*='/jp/show/bid']` が入札履歴リンク(`/jp/show/bid_hist`)に
> 前方一致で当たった。件数と可視だけを見ていると当たったように見えるが、押すと履歴ページへ飛ぶ。
> 当たった候補が別々の要素を指しているときはレポート側が ⚠️ を出すので、
> **実体の表で href / tag を突き合わせてから**写す。

ログイン中のページからは `loginLink` が取れず、`loggedInIndicator` が本当にログイン状態を
追っているのか(ログアウトすると消えるのか)も確かめられない。この2つは `--anonymous`
(Cookie を一切載せない対照実行)で取る。`--stage2` とは併用できない。

Stage 2 は入札フォーム〜確認画面まで進む。**確定ボタンはスクリプトからは絶対に押さない**
(確認画面で止めてブラウザを開いたまま待つので、確定するかは人が画面上で判断する)。

```bash
npm run p0:probe -- '<URL>' --stage2 --amount 1200
```

Stage 2 はステップごとの所要時間も出す。これが §13-2(実行秒数のデフォルト値)の根拠になる。

## 連携 Cookie の生存確認

登録時にできるのは Cookie 名が揃っているかの構造チェックだけで、**ログインが
切れていても登録は通る**。何もしないと、切れていると分かるのは入札の瞬間になる。

`runVerifySessionSweep` は前回の試行から6時間経った ACTIVE な連携を1回3件まで開き、
`judgeSession()`(`apps/worker/src/sessionVerdict.ts`)で判定する。

| 判定 | 根拠 | すること |
|---|---|---|
| `EXPIRED` | ログイン画面へのリダイレクト、または `loginLink` が**存在する** | 失効にして `SESSION_EXPIRED` を通知 |
| `ACTIVE` | `loginLink` が無く `loggedInIndicator` が出ている | `lastVerifiedAt` を進める |
| `UNKNOWN` | どちらも検出できない / 取得に失敗 | **何もしない**(失効にもしない) |

⚠️ **`loggedInIndicator` の不在を失効の根拠にしない。** ログイン中の1回でしか
確認できていない指標なので、ヘッダの実装が変わっただけで「全セッションが失効」に化ける。
失効は予約が全部止まる操作なので、陽性の証拠があるときだけ出す。

⚠️ その代わり `UNKNOWN` が続くとこの確認は「静かに何もしない」のと同じになる。
`lastVerifiedAt` を進めないことでそれを検出可能にしてあり、24時間更新されないと
日次サマリの連携行に ⚠️ が付く。ここが唯一の異常サインなので消さないこと。

確認先の URL は 予約中の商品ページ → ウォッチリストの商品 → ヤフオクトップ の順で選ぶ。
ログイン有無の差を実測できているのは商品ページの `loginLink` だけのため。

## 外出先からアクセスする

### 前提: worker は Mac から動かすしかない

ヤフオクは **VPS(データセンター IP)からのアクセスを 403 で弾く**。
アプリごと VPS へ載せると、画面は開くのに入札だけ落ちる。
そのため「web も worker も Mac で動かし、外からは Mac の画面に届かせるだけ」にする。

⚠️ **Mac がスリープすると入札は動かない。** これは外出時に限らず今もそうで、
外から画面が見えるようになると「見えているのに動いていない」に化けやすくなる。
入札を任せる日は電源に繋いでスリープを切っておくこと。

```bash
caffeinate -dimsu          # 実行中はスリープしない(終了で元に戻る)
```

生きているかどうかは日次サマリ(Telegram)で外出先からも分かる。**サマリが来ない日は
worker が止まっている**と読むこと(設定 > 通知 で送信時刻を決める)。

### 到達方法(公開面を増やさない順)

| 方法 | 公開されるか | HTTPS | 備考 |
|---|---|---|---|
| **Tailscale + `tailscale serve`**(推奨) | されない(自分の端末だけ) | ○ | iPhone に Tailscale を入れるだけ。PWA としてホーム画面に置ける |
| Cloudflare Tunnel + Access | 公開URLだが Access で認証必須 | ○ | 独自ドメインを当てたいとき。Access を外すと**世界中から到達可能**になる |
| VPS の Caddy → Mac への SSH リバーストンネル | 公開 | ○ | 既存インフラに乗るが、VPS が落ちるとアプリも見えない |

推奨の手順(Tailscale):

```bash
brew install --cask tailscale-app && open -a Tailscale   # 初回だけ。iPhone にも同じアカウントで入れる
scripts/remote-serve.sh                              # 起動 → 公開 → スリープ抑止まで一括
```

cask 名は `tailscale-app`(`tailscale` は CLI だけの formula)。
インストールは **sudo のパスワードを聞かれる** ので、自分のターミナルで実行すること。

初回だけ tailnet 側の設定も要る(https://login.tailscale.com/admin/dns):

- **MagicDNS** を有効化
- **HTTPS Certificates** を有効化

どちらかが無効だと `tailscale serve` が通らない。スクリプトはこの失敗を
検出して手順を出すので、メッセージに従って有効化してから実行し直す。

`scripts/remote-serve.sh` がやること:

0. `tailscale` の存在と **ログイン済みかどうか** を先に確かめる
   (ログインしていないと公開だけ失敗し、docker を起動しきった後に落ちて原因が見えにくい)
1. `docker compose up -d --build`(本番ビルド。`NODE_ENV=production` なので Cookie の `secure` が効く)
2. `http://localhost:3000/login` が応答するまで待つ(**待たずに公開すると、繋がらないのが
   Tailscale のせいなのかアプリのせいなのか切り分けられなくなる**)
3. `tailscale serve --bg 3000` で tailnet だけに公開し、URL を表示する
4. `caffeinate -dimsu` で常駐(**この窓を閉じるとスリープ抑止も解除される**)

表示された `https://<machine>.<tailnet>.ts.net` を iPhone の Safari で開き、
共有 > ホーム画面に追加 で PWA になる。公開を取り下げるのは `scripts/remote-serve.sh off`。

### 毎回ターミナルを開かずに済ませる(ログイン時の自動起動)

```bash
scripts/install-autostart.sh            # 登録して即起動
scripts/install-autostart.sh status     # 状態・ログ・再起動コマンドを出す
scripts/install-autostart.sh uninstall  # 解除(コンテナは止めない)
```

`~/Library/LaunchAgents/com.trustlink.yar-autostart.plist` を置き、ログイン時に
`scripts/autostart.sh`(remote-serve.sh の無人版)を走らせる。ログは
`tmp/autostart/autostart.log`。

登録後に `scripts/remote-serve.sh` を実行するのは **イメージを作り直すとき**
(コードを変えたとき)だけでよい。

`autostart.sh` が `remote-serve.sh` と違う点は3つ。**どれも無人で走ることに由来する**。

| 違い | 理由 |
|---|---|
| `--build` しない | ログイン時に数分かかるうえ、ネットワークがまだ繋がっていない時間帯に当たると失敗する |
| Docker デーモンの起動を最大3分待ち、駄目なら `exit 1` | ログイン直後は Docker Desktop がまだ上がっていない。**待たずに進むと「起動した気になって終了」し、KeepAlive も再試行しない** |
| 公開(`tailscale serve`)に失敗しても `exit 1` しない | 公開できなくても **入札は動く**。外から見えないだけなので、止める方が被害が大きい |

コンテナ側にも `restart: unless-stopped` を付けてあるので、Docker Desktop さえ
上がれば個々のコンテナは自力で復帰する。

⚠️ **登録している間、Mac はスリープしない**(`caffeinate` 常駐)。入札の実行に
必要な代償で、蓋を閉じても止まらない。電源に繋いでおくこと。一時的に止めたい
だけなら解除ではなく `launchctl kill TERM gui/$(id -u)/com.trustlink.yar-autostart`。

⚠️ **Docker Desktop 自体の「ログイン時に起動」は別途チェックが要る**
(Docker Desktop の Settings > General)。`autostart.sh` は `open -a Docker` で
起動を試みるが、Docker 側の設定で入れておく方が速い。

### パスワードを忘れたとき

```bash
npm run user:password -- info@trustlink-tk.com
```

新規登録は **ユーザーが0人のときだけ** 自動的に開く(`packages/shared/src/access.ts`)。
初回セットアップが済んだ時点で閉じるので、パスワードを忘れると画面からは
何もできなくなる。

⚠️ `ALLOW_REGISTRATION=true` で開けて別アカウントを作るのは解決にならない。
ヤフオク連携もウォッチリストも予約も、既存ユーザーに紐づいたままになる。

パスワードは端末上でだけ入力する(エコーしない)。引数に書くとシェル履歴と
`ps` の出力に残るので、このスクリプトは引数からは受け取らない。

### 外出先で「動いていない」に気づく仕組み

外から画面が開けるようになると、**Mac のスリープが「画面は正常なのに入札だけ実行されない」
という無症状の故障**になる。これを2箇所で見えるようにしてある。

| 仕組み | いつ気づけるか | 実装 |
|---|---|---|
| 画面上部の赤い警告 | アプリを開いたとき | `app/WorkerAlert.tsx`(worker の鼓動が3分途絶えたら表示) |
| 日次サマリ(Telegram) | サマリが来ない日 | `jobs/dailySummary.ts` |

worker はスケジューラの走査ごと(30秒)に `WorkerHeartbeat` を1行上書きする。
**鼓動は「走査が回っていること」であって「ジョブが成功したこと」ではない** —
予約が1件も無い日と worker が死んでいる日を区別できなくしないため(設計 §14.8)。

### 外に出す前に必ず確認すること

- **新規登録が閉じているか。** 既定では利用者が1人でも居れば `/register` は 403 を返す。
  開けたいときだけ `ALLOW_REGISTRATION=true` を立て、**終わったら消す**
- ログイン試行は 15 分に 5 回まで(メールアドレス単位 / IP 単位)。超えると 429。
  記録はプロセス内メモリなので、web を再起動すると解除される
- `AUTH_SECRET` と `COOKIE_ENCRYPTION_KEY` が開発用の使い回しになっていないか
- このアプリは **ヤフオクのログイン Cookie を預かっている**。到達できる範囲を広げることは、
  その Cookie に到達できる範囲を広げること。公開URLにするなら認証を前段に置く

## 既知の制約(MVP 時点)

- 入札フローのセレクタは確定クリックまで実測済み(2026-08-29 / 実入札1件)。
  残るのは**落札できた側の画面**で、これは実際に競り勝つまで埋まらない。
  製品の経路そのもの(予約 → スケジューラ → 自動起動 → 入札 → 通知)は
  「テスト実行」で実入札ゼロのまま通せる。
  `--stage2` は実商品に実額を入力するが、確認ボタンを押す前に
  「それは確定ボタンではないか」を判定して止める(`apps/worker/src/bidder/probeSafety.ts`)。
  セレクタが ✅ になってもこのガードは外さない(UI が変われば同じ罠に戻るため)。
  止まった場合は画面上で自分で押すこと
- **入札フォームの金額が税抜か税込かは未確定**。`price != taxinPrice` のストア出品で
  `--stage2` を回してフォームの「最低入札価格」と突き合わせるまで、`currentPrice` は
  税抜側(`price`)のまま動かさない(設計 §13)
- 送料・出品者評価・落札相場のパーサも P0 未検証(上記「判断材料」を参照)
- 連携 Cookie の有効性チェックは **登録後の非同期確認**(登録時は形式チェックだけ)。
  worker が6時間ごとに実ページを開いて判定し、失効なら `SESSION_EXPIRED` を通知する
  (`apps/worker/src/jobs/verifySession.ts`)。登録直後のものだけ 30 秒以内に確認し、
  結果は設定画面の「最終確認」欄に出る。登録リクエスト自体は確認を待たない
  (待つとタイムアウトが「登録に失敗した」ように見えて、実際には登録済みになる)
- ウォッチリストは 2026-08-29 に実測済み(`watchlistLoginWall` ✅ / `watchlistItemLink` は
  カルーセル除外とセットでのみ ✅)。`watchlistNextPage` だけは**判定不能**のまま
  — 実物が9件でページャが出ない。10件を超える日に `npm run p0:probe -- --watchlist` を
  回すこと。それまで2ページ目以降は黙って落ちる可能性がある
- 同一ヤフオクセッションの入札直列化(設計 §7.4)は **1 worker プロセス内でのみ有効**
  (`apps/worker/src/sessionLock.ts` のメモリ上のロック)。worker を複数立てると効かない。
  直列化するのは入札の送信だけで、終了時刻が近いと最長 20 秒待って諦め、並行実行する
  (入札しないより並行してでも入札する方が損失が小さいため。諦めた場合はログに警告が出る)
- スタイルは素の CSS。Tailwind CSS 4 への移行は P1(設計 §5)
- `npm audit` に high 3件が残る(いずれも `next` 15.x が依存する postcss / sharp)。
  解消には `next@16` へのメジャーアップグレードが必要なため MVP では見送っている。
  現状の到達性: postcss はビルド時のみで、処理対象は自前の CSS だけ。sharp は
  `next/image` の最適化経路でのみ使われるが、本アプリの画像は素の `<img>` で表示しており、
  `next.config.ts` に `images.remotePatterns` を設定していないため外部 URL の最適化は
  既定で拒否される。Next のバージョン上げは MVP とは別タスクで扱うこと。
