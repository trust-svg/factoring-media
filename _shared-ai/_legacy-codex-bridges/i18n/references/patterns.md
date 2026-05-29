# i18n パターン集 — 実装リファレンス

このファイルは `/i18n` スキルが参照する翻訳パターンの実例集です。
eBay Agent Hub での実装をベースにしています。

---

## 1. 静的HTML — data属性パターン

### 基本（見出し・ラベル）

```html
<!-- Before -->
<h2>Recent Activity</h2>
<div class="label">Total Listings</div>

<!-- After -->
<h2 data-en="Recent Activity" data-ja="最近のアクティビティ">Recent Activity</h2>
<div class="label" data-en="Total Listings" data-ja="総出品数">Total Listings</div>
```

### ボタン

```html
<!-- Before -->
<button class="btn" onclick="loadAlerts()">Refresh</button>

<!-- After -->
<button class="btn" onclick="loadAlerts()" data-en="Refresh" data-ja="更新">Refresh</button>
```

### Jinja2 ページタイトル

```html
<!-- Before -->
{% block page_title %}Sales Analytics{% endblock %}

<!-- After -->
{% block page_title %}<span data-en="Sales Analytics" data-ja="売上分析">Sales Analytics</span>{% endblock %}
```

### 動的カウント付きタイトル

```html
<!-- Before -->
{% block page_title %}Inventory ({{ listings|length }} items){% endblock %}

<!-- After -->
{% block page_title %}<span data-en="Inventory" data-ja="在庫管理">Inventory</span> ({{ listings|length }} <span data-en="items" data-ja="件">items</span>){% endblock %}
```

### テーブルヘッダー

```html
<!-- Before -->
<tr>
    <th>SKU</th>
    <th>Title</th>
    <th>Price</th>
</tr>

<!-- After -->
<tr>
    <th>SKU</th>
    <th data-en="Title" data-ja="タイトル">Title</th>
    <th data-en="Price" data-ja="価格">Price</th>
</tr>
```
> SKU のような固有略語は翻訳しない。

### フィルターボタン / タブ

```html
<button class="tab active" data-tab="all" onclick="filterProc('all')"
        data-en="All" data-ja="すべて">All</button>
<button class="tab" data-tab="purchased" onclick="filterProc('purchased')"
        data-en="Purchased" data-ja="購入済">Purchased</button>
```
> 既存の data-* 属性と共存可能。

### フォームラベル + placeholder

```html
<!-- Before -->
<label>Title</label>
<input placeholder="Product name">

<!-- After -->
<label data-en="Title" data-ja="タイトル">Title</label>
<input placeholder="Product name"
       data-placeholder-en="Product name"
       data-placeholder-ja="商品名">
```

### 空状態メッセージ

```html
<div class="empty-state"
     data-en="No inventory data yet. Use the AI Agent to sync inventory."
     data-ja="在庫データがありません。AIエージェントで同期してください。">
  No inventory data yet. Use the AI Agent to sync inventory.
</div>
```

---

## 2. JS生成コンテンツ — t() 関数パターン

### テーブルヘッダー（テンプレートリテラル内）

```javascript
// Before
let html = '<table><thead><tr><th>Product</th><th>Revenue</th></tr></thead>';

// After
let html = `<table><thead><tr><th>${t('Product','商品')}</th><th>${t('Revenue','売上')}</th></tr></thead>`;
```
> シングルクォートの文字列はバッククォートに変更が必要。

### 統計カードラベル

```javascript
// Before
`<div class="label">Total Sales</div><div class="value">${s.total_sales}</div>`

// After
`<div class="label">${t('Total Sales','総売上件数')}</div><div class="value">${s.total_sales}</div>`
```

### Chart.js ラベル

```javascript
// Before
{ label: 'Revenue ($)', data: trend.map(d => d.revenue_usd) }

// After
{ label: t('Revenue ($)', '売上 ($)'), data: trend.map(d => d.revenue_usd) }
```

### ボタンテキスト（動的変更）

```javascript
// Before
btn.textContent = 'Processing...';
btn.textContent = 'Send';

// After
btn.textContent = t('Processing...', '処理中...');
btn.textContent = t('Send', '送信');
```

### 空状態（JS生成）

```javascript
// Before
container.innerHTML = '<div class="empty-state">No recent activity</div>';

// After
container.innerHTML = `<div class="empty-state">${t('No recent activity','最近のアクティビティはありません')}</div>`;
```

### チャットメッセージ

```javascript
// Before
messages.innerHTML += `<div class="bubble"><span class="spinner"></span> Thinking...</div>`;

// After
messages.innerHTML += `<div class="bubble"><span class="spinner"></span> ${t('Thinking...','考え中...')}</div>`;
```

---

## 3. 基盤コード — 完全版

### app.js に追加する関数群

```javascript
/* ── Language Toggle ── */

function getLang() {
    return localStorage.getItem('lang-pref') || 'en';
}

function t(en, ja) { return getLang() === 'ja' ? ja : en; }

function applyLang(lang) {
    // テキストコンテンツ
    document.querySelectorAll('[data-en][data-ja]').forEach(el => {
        el.textContent = el.dataset[lang];
    });
    // プレースホルダー
    document.querySelectorAll('[data-placeholder-en][data-placeholder-ja]').forEach(el => {
        el.placeholder = lang === 'ja' ? el.dataset.placeholderJa : el.dataset.placeholderEn;
    });
    // トグルラベル
    const label = document.getElementById('langLabel');
    if (label) label.textContent = lang === 'ja' ? 'JA' : 'EN';
}

function toggleLang() {
    const next = getLang() === 'en' ? 'ja' : 'en';
    localStorage.setItem('lang-pref', next);
    location.reload();  // JS生成コンテンツも確実に切替
}

document.addEventListener('DOMContentLoaded', () => applyLang(getLang()));
```

### トグルボタン HTML

```html
<button class="lang-toggle" onclick="toggleLang()" title="言語切替">
    <span class="lang-label" id="langLabel">EN</span>
</button>
```

### トグルボタン CSS

```css
.lang-toggle {
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 4px;
    padding: 4px 10px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    color: inherit;
    transition: background 0.2s;
}
.lang-toggle:hover {
    background: rgba(255,255,255,0.2);
}
```

---

## 4. よく使う翻訳一覧

### ダッシュボード系

| EN | JA |
|---|---|
| Overview | 概要 |
| Dashboard | ダッシュボード |
| Analytics | 分析 |
| Settings | 設定 |
| Active | 稼働中 |
| Loading... | 読み込み中... |

### CRUD 操作

| EN | JA |
|---|---|
| Save | 保存 |
| Delete | 削除 |
| Edit | 編集 |
| Cancel | キャンセル |
| Close | 閉じる |
| Refresh | 更新 |
| Search | 検索 |
| Filter | フィルター |
| All | すべて |

### テーブル系

| EN | JA |
|---|---|
| Title | タイトル |
| Price | 価格 |
| Status | ステータス |
| Date | 日付 |
| Category | カテゴリ |
| Quantity / Qty | 数量 |

### EC / eBay 系

| EN | JA |
|---|---|
| Inventory | 在庫管理 |
| In Stock | 在庫あり |
| Out of Stock | 在庫切れ |
| Revenue | 売上 |
| Profit | 利益 |
| Margin | マージン |
| Sourcing | 仕入れ |
| Procurement | 調達 |
| Shipping | 送料 / 発送 |

### メッセージ系

| EN | JA |
|---|---|
| Messages | メッセージ |
| Send | 送信 |
| Reply | 返信 |
| Draft | 下書き |
| No data | データなし |
| Error | エラー |

---

## 5. 設計判断メモ

### なぜ data属性 + t() 方式か

- **フレームワーク不要**: React/Vue なしでも動作
- **CDN依存なし**: i18next 等のライブラリ不要
- **学習コスト低**: HTML属性とJS関数だけ
- **SSR互換**: Jinja2/Django テンプレートと共存可能
- **軽量**: 追加JS < 500バイト

### なぜ location.reload() か

- `t()` でレンダー済みのJS生成コンテンツはDOM操作では更新できない
- 各ページの init 関数を全て呼び直すよりリロードが確実
- ダッシュボード用途ではリロード時間は問題にならない

### 3言語以上に拡張する場合

data属性方式のままでも対応可能:
```html
<span data-en="Hello" data-ja="こんにちは" data-zh="你好">Hello</span>
```
```javascript
function getLang() {
    return localStorage.getItem('lang-pref') || 'en';
}
function applyLang(lang) {
    document.querySelectorAll(`[data-${lang}]`).forEach(el => {
        if (el.dataset[lang]) el.textContent = el.dataset[lang];
    });
}
```
ただし4言語以上になる場合は JSON 辞書ファイル方式への移行を推奨。
