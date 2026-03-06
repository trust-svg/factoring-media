# Meta Graph API セットアップ手順

Instagram自動投稿を有効化するための手順。
ebay-agentの `instagram/client.py` はトークン設定後に自動的にモック→実APIに切り替わる。

---

## Step 1: Instagramをビジネスアカウントに切替

1. Instagramアプリ → @samuraishopjp → 設定
2. 「アカウント」→「プロアカウントに切り替え」
3. カテゴリ: 「ショッピング・小売り」
4. 「ビジネス」を選択

## Step 2: Facebookページを作成・連携

1. [facebook.com/pages/create](https://www.facebook.com/pages/create) でページ作成
   - ページ名: `Samurai Shop Japan`
   - カテゴリ: `Shopping & Retail`
2. Instagramアプリ → 設定 → 「リンク済みアカウント」→ Facebookページを連携

## Step 3: Meta Developerアプリ登録

1. [developers.facebook.com](https://developers.facebook.com/) にログイン
2. 「マイアプリ」→「アプリを作成」
3. アプリタイプ: 「ビジネス」
4. アプリ名: `SamuraiShop Instagram`
5. 作成後、アプリID と シークレットをコピー

## Step 4: 必要な権限を追加

アプリダッシュボード → 「製品を追加」→ 「Instagram Graph API」

必要なパーミッション:
- `instagram_basic` — プロフィール情報
- `instagram_content_publish` — 投稿の公開
- `instagram_manage_insights` — インサイトデータ
- `pages_read_engagement` — ページエンゲージメント

## Step 5: アクセストークン取得

### Graph API Explorerで取得:
1. [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer/)
2. アプリを選択
3. 「ユーザートークンを生成」→ 上記パーミッションを選択
4. 短期トークンが発行される

### 長期トークンに変換:
```bash
curl -s "https://graph.facebook.com/v19.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id={APP_ID}&\
client_secret={APP_SECRET}&\
fb_exchange_token={SHORT_LIVED_TOKEN}"
```
→ 60日間有効な長期トークンが返る

### ページトークン取得:
```bash
curl -s "https://graph.facebook.com/v19.0/me/accounts?access_token={LONG_LIVED_TOKEN}"
```
→ `access_token` フィールドがページトークン（無期限）

### Instagram Business Account ID取得:
```bash
curl -s "https://graph.facebook.com/v19.0/{PAGE_ID}?fields=instagram_business_account&access_token={PAGE_TOKEN}"
```
→ `instagram_business_account.id` がInstagramユーザーID

## Step 6: .envに設定

```env
# products/ebay-agent/.env に追加
META_APP_ID=123456789
META_APP_SECRET=abcdef123456
INSTAGRAM_ACCESS_TOKEN=EAAxxxxxxx（ページトークン）
INSTAGRAM_USER_ID=17841400000000000
```

## Step 7: 動作確認

```bash
cd products/ebay-agent
python -c "
from instagram.client import InstagramClient
c = InstagramClient()
print('Connected:', c.is_connected)
print('Account:', c.get_account_insights())
"
```

`Connected: True` が表示されれば成功。

---

## トークン更新

ページトークンは無期限だが、アプリのレビュー前は開発モード制限あり。
本番運用にはMeta App Reviewでパーミッション承認が必要。

### App Review申請時のポイント:
- `instagram_content_publish` は動画デモが必要
- 使用目的: 「自社ビジネスのInstagramアカウントに商品情報を投稿するため」
- スクリーンショット: ダッシュボードの投稿生成画面を添付
