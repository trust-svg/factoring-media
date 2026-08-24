# ヤフオク入札予約アプリ (yahoo-auction-reserve)

ヤフオクの商品ページURLを登録しておくと、**終了直前に自動で入札する**(スナイプ入札)Webアプリ。
設計の正は [`docs/yahoo-auction-reserve-app/DESIGN.md`](../docs/yahoo-auction-reserve-app/DESIGN.md)、
競合調査は [`COMPETITORS.md`](../docs/yahoo-auction-reserve-app/COMPETITORS.md)。

> [!WARNING]
> **現在は MVP スケルトンであり、実際の入札は成功しない前提で扱うこと。**
> `apps/worker/src/bidder/selectors.ts` のセレクタは全て未検証のプレースホルダで、
> 実ページに対する P0 検証(設計 §13)が完了するまで入札フローは動作保証がない。
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
| `DATABASE_URL` | PostgreSQL 接続先 | `postgresql://yar:yar@localhost:5432/yar`(compose 起動時は compose 側で上書き) |
| `REDIS_URL` | Redis 接続先 | `redis://localhost:6379`(同上) |
| `AUTH_SECRET` | ログインセッション JWT の署名鍵 | `node -e 'console.log(require("crypto").randomBytes(32).toString("base64"))'` |
| `COOKIE_ENCRYPTION_KEY` | ヤフオク Cookie の AES-256-GCM 暗号鍵。**base64 で厳密に 32 バイト** | 同上 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | 通知メール送信(任意) | 未設定ならメール送信はスキップされ、通知内容は worker のログに出る |
| `MAIL_FROM` | 通知メールの From | `yar@example.com` |
| `CHROMIUM_EXECUTABLE_PATH` | Playwright が使う Chromium の明示指定(任意) | Docker イメージ同梱のものを使う場合は不要 |

> `COOKIE_ENCRYPTION_KEY` を変更すると **保存済みの連携 Cookie は全て復号できなくなる**。
> 鍵を入れ替えたら `YahooSession` を作り直すこと。

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

型チェックは全ワークスペース一括:

```bash
npm run typecheck
```

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
2. `/settings/yahoo` でヤフオクのログイン Cookie を貼り付けて連携を登録
3. `/reservations/new` で商品URLを貼り付け → プレビュー → 上限額・実行タイミングを入力 → **確認ステップ**で確定
4. `/dashboard` で予約一覧、`/reservations/<id>` で入札試行のタイムラインを確認

### ヤフオク Cookie の取得について

ログイン維持に使う Cookie (`T` / `Y` / `SSL` / `SSLK`) は **httpOnly** のため、
ブックマークレットや `document.cookie` では取得できない。ブラウザ拡張
(Cookie-Editor 等)の JSON エクスポート、または DevTools の Application →
Cookies から書き出した JSON を `/settings/yahoo` に貼り付ける。

貼り付けられた JSON はサーバ側で正規化され(`*.yahoo.co.jp` 以外は破棄、
`sameSite` / 有効期限を Playwright が受け付ける形へ変換)、認証用 Cookie が
欠けている場合は警告を返す。Cookie 本体は AES-256-GCM で暗号化して保存し、
**API レスポンス・ログには一切出さない**(設計 §8)。

## 既知の制約(MVP 時点)

- 入札フローのセレクタは P0 未検証(上記の警告を参照)
- 連携 Cookie の有効性チェックが未実装(登録時は形式のみ検証。設計 §13 の P0 でログイン判定方法を確定してから実装)
- 同一ヤフオクセッションの入札直列化(設計 §7.4)はフェーズ2
- スタイルは素の CSS。Tailwind CSS 4 への移行は P1(設計 §5)
- `npm audit` に high 3件が残る(いずれも `next` 15.x が依存する postcss / sharp)。
  解消には `next@16` へのメジャーアップグレードが必要なため MVP では見送っている。
  現状の到達性: postcss はビルド時のみで、処理対象は自前の CSS だけ。sharp は
  `next/image` の最適化経路でのみ使われるが、本アプリの画像は素の `<img>` で表示しており、
  `next.config.ts` に `images.remotePatterns` を設定していないため外部 URL の最適化は
  既定で拒否される。Next のバージョン上げは MVP とは別タスクで扱うこと。
