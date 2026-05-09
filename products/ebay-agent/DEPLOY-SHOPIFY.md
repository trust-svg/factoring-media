# Shopify統合デプロイ手順書
**作成日**: 2026-05-08
**対象**: ebay-agent Shopify統合（2026-04-12実装、未デプロイ）
**前提**: コード実装＋テスト13本パス済（git log `feat(shopify):` 11コミット）

---

## ⚠️ デプロイ前の重要な確認事項

このコミットはローカルブランチ `feature/zinq-suite-mvp` に滞留しており、**他の大量コミット（video-ad-generator phase 2a、d-manager 動画分析、ebay-agent eShip機能など、計30本以上）も同じブランチに混在**しています。

VPSがどのブランチを `git pull` するかで、副作用が大きく変わります。Hiroさん要判断の項目:

### 判断1: デプロイ範囲

| 選択肢 | 内容 | リスク |
|---|---|---|
| **A. Shopifyだけ** | 11 shopify コミットだけを `main` に cherry-pick → push → VPSが main pull | 履歴複雑化、cherry-pickミス可能性 |
| **B. ブランチ全部** | `feature/zinq-suite-mvp` を `main` にマージ → push → VPSが main pull | 30本以上の他機能も同時に本番反映（巨大なblast radius） |
| **C. feature branch直** | VPSの追跡ブランチを `feature/zinq-suite-mvp` に切替 | 一時的な分岐運用、後続マージが必要 |

→ **推奨: B（ブランチマージ）**。理由は (1) video-ad-generator/d-manager の他コミットも本番に反映する想定であろうこと、(2) 5/3〜5/8 の最新機能はもう本番投入したい段階のはず。**ただし他チャットで他機能をテスト中でないか必ず確認**。

### 判断2: VPSの実パスと構成

私（Claude Code）からは以下が見えていません。Hiroさんに確認お願いします:

```bash
# VPS上で実行して結果を教えてください
ssh root@46.250.252.99 'find /root /opt -maxdepth 3 -name "docker-compose.yml" -path "*ebay*" 2>/dev/null'
ssh root@46.250.252.99 'cd <ebay-agentのVPSパス> && git remote -v && git branch --show-current'
```

期待される結果:
- VPS上のebay-agentパス（おそらく `/root/services/ebay-agent` か `/root/ebay-agent`）
- 追跡ブランチ（`main` か `feature/zinq-suite-mvp` か）
- リモート（同じ `claude-workspace` monorepo か、別の独立リポか）

---

## 全体フロー

```
[他チャット側]                       [このチャット側]
─────────────────                  ─────────────────
1. Shopify Starter契約     ←→
2. Custom App作成・トークン発行
3. Webhook URL登録                  ↓ Hiroさんからトークン受領
4. Claude.aiコネクタ接続
                                    5. .env追加（Hiroさん手作業・私は書けない）
                                    6. ブランチ戦略決定（判断1）
                                    7. push & VPS deploy
                                    8. 動作確認
                                    9. sync_all_to_shopify 実行
                                    10. Caddyリダイレクト設定
```

---

## A. Hiroさん側で他チャット担当（Shopifyブラウザ作業）

### Step 1: Shopify Starterサインアップ

- URL: https://www.shopify.com/jp/starter
- 3日無料トライアル → 月$5
- ストア名（仮）: `trustlink-japan-finds.myshopify.com`（要決定）
- 国/通貨: 日本/USD（eBay合わせ）
- 確認事項: **独自ドメインは設定しない**（StarterはURLが `shop.app/[store]/products/[SKU]` 固定。CaddyでリダイレクトするのでOK）

### Step 2: Custom App作成 → アクセストークン発行

1. Shopify管理画面 → Apps → Develop apps → Create an app
2. 名前: `ebay-agent-sync`
3. Configuration → Admin API access scopes:
   - ✅ `write_products`
   - ✅ `read_orders`
   - ✅ `write_inventory`
4. Install app → Reveal token once → コピーして保管（`shpat_xxx...` 形式）
5. **Webhook secret（HMAC検証用）**: Settings → Notifications → Webhook section の "Signing secret" をコピー（`xxx...` 形式）

### Step 5: Webhook登録（Step 4のVPSデプロイ完了後）

Settings → Notifications → Webhooks → Create webhook

| 項目 | 値 |
|---|---|
| Event | Order creation |
| Format | JSON |
| URL | `https://ebay.trustlink-tk.com/shopify/webhook/order-created` |
| API version | 2024-01 |

### Step 7: Claude.ai 公式コネクタ接続

URL: https://claude.ai/directory/connectors/shopify
- Shopifyログイン → 接続承認
- 用途: スマホからの売上確認・商品検索（バックエンド自動化はebay-agent側、こちらはUI補完）

---

## B. このチャット側で実行

### Step 3: `.env` に4変数追加（Hiroさん手作業）

私（Claude Code）はサンドボックス制限で `.env` に書き込めません。Hiroさん側で以下を追加してください:

```dotenv
# === Shopify ===
SHOPIFY_SHOP_DOMAIN=trustlink-japan-finds.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_<step2でコピーした値>
SHOPIFY_WEBHOOK_SECRET=<step2でコピーした値>
SHOPIFY_DISCOUNT_RATE=0.05
```

確認コマンド（値は出さずキー名のみ）:
```bash
grep -E "^SHOPIFY_" products/ebay-agent/.env | cut -d= -f1
# 期待: 4行（SHOPIFY_SHOP_DOMAIN / SHOPIFY_ACCESS_TOKEN / SHOPIFY_WEBHOOK_SECRET / SHOPIFY_DISCOUNT_RATE）
```

### Step 6: ブランチ戦略の実行（判断1で選択した方法）

#### Option B（ブランチマージ）の場合 — 推奨

```bash
# ローカルで作業ツリーをきれいにする
git stash push -m "wip: Dockerfile playwright deps + handlers.py uncommitted changes"

# main にマージ
git checkout main
git pull origin main
git merge --no-ff feature/zinq-suite-mvp -m "merge feature/zinq-suite-mvp: shopify integration + video-ad-generator phase 2a + d-manager updates"

# プッシュ
git push origin main

# 元のブランチに戻る
git checkout feature/zinq-suite-mvp
git stash pop
```

#### Option A（cherry-pickのみ）の場合

```bash
git checkout main
git pull origin main
# 11 shopify コミットだけを順番に
git cherry-pick 2faf422 430b4e7 0fc14b5 20f4eb1 27a9f14 60863b3 8546ea1 3c362bc 1855af1 dc14342 35815d0
git push origin main
git checkout feature/zinq-suite-mvp
```

### Step 4: VPSデプロイ実行

⚠️ **不可逆操作**。実行前に必ずHiroさんに確認。CLAUDE.mdの「不可逆操作前の確認」ルール適用。

```bash
# VPS上のebay-agentパスを X とする（要確認）
ssh root@46.250.252.99 "cd <X> && git pull && docker compose up -d --build ebay-agent"
# ※ サービス名は要確認。`docker compose ps` で確認
```

**ヘルスチェック**:
```bash
# 1. コンテナ起動確認
ssh root@46.250.252.99 "cd <X> && docker compose ps ebay-agent"
# 2. /health エンドポイント
curl -fsS https://ebay.trustlink-tk.com/health
# 3. ログでShopify同期スケジューラ起動を確認
ssh root@46.250.252.99 "cd <X> && docker compose logs --tail=50 ebay-agent | grep -i shopify"
# 期待: 'Shopify sync job' のログ（30分以内に1回出る）
```

### Step 6（再）: 既存eBay出品をShopifyに一括同期

```bash
# ebay-agentダッシュボード経由
curl -X POST https://ebay.trustlink-tk.com/api/tool/sync_all_to_shopify
# または管理画面 http://ebay.trustlink-tk.com からエージェントに自然言語指示:
# 「未同期のeBay出品を全部Shopifyに同期して」
```

⚠️ レート制限: 0.5秒/req × 587商品 = 約5分。バックグラウンドで進行。完了通知をTelegramに飛ばすか、手動でログ確認。

### Step 8: Caddyリダイレクト設定

VPSの既存Caddyfile（`/etc/caddy/Caddyfile` または `/root/caddy/Caddyfile` のどこか）に以下を追加:

```caddyfile
# Shopify Starter URLへのリダイレクト（同梱カード用短縮URL）
trustlink.shop {
    # /[SKU] パスを Shopify Starter商品ページへ301
    @sku path_regexp sku ^/([A-Za-z0-9_-]+)$
    redir @sku https://shop.app/<store-handle>/products/{re.sku.1} 301

    # ルートはShopifyトップへ
    redir / https://shop.app/<store-handle> 301

    # IGアカウント用ショートカット
    redir /ig https://www.instagram.com/<ig_handle> 301
    redir /pin https://www.pinterest.com/<pin_handle>/made-in-japan 301
}
```

**置換が必要**:
- `<store-handle>` — Shopifyストアハンドル（`trustlink-japan-finds` 等）
- `<ig_handle>` / `<pin_handle>` — 後でSNSアカウント開設時に決定

**反映**:
```bash
ssh root@46.250.252.99 "caddy reload --config /etc/caddy/Caddyfile"
```

**疎通確認**:
```bash
curl -I https://trustlink.shop/<test_sku>
# 期待: 301 Location: https://shop.app/<store-handle>/products/<test_sku>
```

---

## C. ロールバック手順

### コンテナのみロールバック（最軽量）
```bash
ssh root@46.250.252.99 "cd <X> && git reset --hard <デプロイ前のコミットhash> && docker compose up -d --build ebay-agent"
```

### Shopify同期を一時停止
```bash
# .env の SHOPIFY_ACCESS_TOKEN を空にして再起動 → スケジューラジョブはエラーログ吐くだけで安全
ssh root@46.250.252.99 "cd <X> && docker compose restart ebay-agent"
```

### Shopify側の全削除（撤退時）
```bash
# remove_from_shopify ツールを全SKUに対して実行
# または Shopify管理画面 → Products → Delete all
# Custom Appもアンインストール推奨
```

---

## D. デプロイ完了の判定基準

- [ ] `https://ebay.trustlink-tk.com/health` 200応答
- [ ] `docker compose logs ebay-agent | grep "shopify_sync"` で30分以内に1ジョブ起動を確認
- [ ] `/api/tool/get_shopify_status` が `{"synced": >0, "unsynced": ...}` を返す
- [ ] テスト用SKU 1件で `sync_all_to_shopify` 実行 → Shopify管理画面に商品出現
- [ ] テスト用商品をShopifyで購入 → webhookでeBay側 `quantity=0` に更新されることを確認
- [ ] `https://trustlink.shop/<test_sku>` が 301でShopify商品ページへ飛ぶ
- [ ] Telegram `@bmanager_trustlink_bot` に同期完了通知が届く

---

## E. Hiroさん用 当日チェックリスト（短縮版）

```
[ ] Shopify Starter契約完了 → URLとログイン情報メモ
[ ] Custom App作成 → アクセストークンとWebhook secret取得
[ ] .env に4変数追記（私のチャットに「.env追記しました」と一報）
[ ] ブランチ戦略決定（A/B/C のどれにするか私に伝達）
[ ] VPSパスと追跡ブランチ確認 → 私に伝達
[ ] デプロイ実行（私に「デプロイGO」と指示）
[ ] sync_all_to_shopify 実行（私に指示）
[ ] Caddy設定 → リロード（私に指示）
[ ] Shopifyダッシュボードでwebhook登録（テスト購入で動作確認）
[ ] Claude.aiコネクタ接続（スマホで動作確認）
```

---

## 関連ファイル

- 仕様書: `resources/docs/superpowers/specs/2026-04-12-shopify-integration-design.md`
- 実装計画: `resources/docs/superpowers/plans/2026-04-12-shopify-integration.md`
- 戦略メモ（185人調査ベース）: `~/.claude/plans/ebay-shopify-185-imperative-ripple.md`
- Shopify実装コード: `products/ebay-agent/shopify/{client.py, sync.py}`
- テスト: `products/ebay-agent/test_shopify.py`
- 4 Claude tools: `products/ebay-agent/tools/{registry.py, handlers.py}` 末尾
- スケジューラ: `products/ebay-agent/comms/scheduled_jobs.py` の `auto_sync_and_close_shopify`
- Webhook: `products/ebay-agent/main.py` の `/shopify/webhook/order-created`
