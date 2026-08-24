# ヤフオク入札予約アプリ (yahoo-auction-reserve)

ヤフオクの商品ページURLを登録しておくと、**終了直前に自動で入札する**(スナイプ入札)Webアプリ。
設計の正は [`docs/yahoo-auction-reserve-app/DESIGN.md`](../docs/yahoo-auction-reserve-app/DESIGN.md)、
競合調査は [`COMPETITORS.md`](../docs/yahoo-auction-reserve-app/COMPETITORS.md)。

> [!WARNING]
> **現在は MVP スケルトンであり、実際の入札は成功しない前提で扱うこと。**
> `apps/worker/src/bidder/selectors.ts` の P0 検証(設計 §13)は**途中まで**しか終わっていない。
> 2026-08-24 の実測で `loginLink` / `bidButton` は確定したが、入札フォーム以降
> (`priceInput` / `bidConfirmButton` / `bidSubmitButton`)と結果判定の3つは
> **未検証のプレースホルダのまま**で、入札フローは動作保証がない。
> どれが確定済みかは `selectors.ts` 冒頭の表が正。
> P0 検証は人手で実施する。CI や自動テストからヤフオクへ実アクセスしないこと。

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
| `CHROMIUM_EXECUTABLE_PATH` | Playwright が使う Chromium の明示指定(任意) | Docker イメージ同梱のものを使う場合は不要 |

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
(現状は `packages/shared` のスナイプ実行タイミング計算)。**このテストは
「壊したら落ちる」ことを確認済み**で、`monitorLeadSeconds` を旧実装の固定値
90 に戻すと 5 件中 3 件が落ちる。落ちないテストを足さないこと。

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
```

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

## 既知の制約(MVP 時点)

- 入札フローのセレクタは P0 未検証(上記の警告を参照)。埋める手順は「P0 検証プローブ」を参照
- 連携 Cookie の有効性チェックが未実装(登録時は形式のみ検証。設計 §13 の P0 でログイン判定方法を確定してから実装)
- 同一ヤフオクセッションの入札直列化(設計 §7.4)はフェーズ2
- スタイルは素の CSS。Tailwind CSS 4 への移行は P1(設計 §5)
- `npm audit` に high 3件が残る(いずれも `next` 15.x が依存する postcss / sharp)。
  解消には `next@16` へのメジャーアップグレードが必要なため MVP では見送っている。
  現状の到達性: postcss はビルド時のみで、処理対象は自前の CSS だけ。sharp は
  `next/image` の最適化経路でのみ使われるが、本アプリの画像は素の `<img>` で表示しており、
  `next.config.ts` に `images.remotePatterns` を設定していないため外部 URL の最適化は
  既定で拒否される。Next のバージョン上げは MVP とは別タスクで扱うこと。
