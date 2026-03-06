---
name: i18n
description: >
  Web プロジェクトの多言語化（i18n）を自動化するスキルです。
  HTML/テンプレートファイルのハードコードされたテキストを検出し、
  data-en/data-ja 属性によるクライアントサイド翻訳を一括適用します。
  JS生成コンテンツにも対応し、言語切替トグルの設置まで行います。
  「多言語化して」「i18n対応」「日本語化」「翻訳対応」「EN/JA切替」
  「言語切り替え」「internationalize」「add translations」で使ってください。
argument-hint: [scan|setup|apply|full] [target-dir]
---

# i18n — Web多言語化スキル

Webプロジェクトのフロントエンドを EN/JA バイリンガル対応にする。
フレームワーク不要、バニラJS + HTML属性だけで動作する軽量アプローチ。

## コンセプト

- **data属性方式**: `data-en="English" data-ja="日本語"` を各要素に付与
- **JSヘルパー**: 動的生成コンテンツには `t('English', '日本語')` 関数
- **localStorage永続化**: 言語設定をブラウザに保存
- **ページリロード方式**: トグル時にリロードし、全コンテンツを確実に切替

---

## 実行モード

引数 `$ARGUMENTS` に応じて動作を切り替える:

| コマンド | 動作 |
|---|---|
| `/i18n scan [dir]` | 対象ディレクトリをスキャンし、未翻訳テキストを一覧表示（変更なし） |
| `/i18n setup [dir]` | 言語切替の基盤コード（JS関数 + トグルUI）を設置 |
| `/i18n apply [dir]` | 全ファイルに翻訳属性を一括適用 |
| `/i18n full [dir]` | setup + scan + apply をまとめて実行（デフォルト） |
| `/i18n` | `full` と同じ（引数なしの場合） |

`[dir]` 省略時はカレントディレクトリ直下の `templates/` と `static/` を対象とする。

---

## Mode: scan

対象ファイルを読み取り専用でスキャンし、翻訳が必要なテキストを洗い出す。

### 手順

1. **対象ファイルの特定**
   - Glob で `templates/**/*.html`, `**/*.jinja2`, `**/*.j2` を検索
   - Glob で `static/**/*.js`, `static/**/*.ts` を検索
   - `node_modules/`, `venv/`, `.git/` は除外

2. **HTML/テンプレートのスキャン**
   各ファイルを Read し、以下を検出:
   - `<h1>` ~ `<h6>`, `<th>`, `<label>`, `<button>`, `.label`, `.badge` 内のテキスト
   - `placeholder="..."` 属性の値
   - `.empty-state` 内のメッセージ
   - `data-en` が**まだ付いていない**要素のみ対象

3. **JSファイルのスキャン**
   - テンプレートリテラル内の `<th>`, `<div class="label">` 等のハードコード文字列
   - `.innerHTML = '...'` のテキスト
   - `.textContent = '...'` のテキスト
   - `t()` 関数が**まだ使われていない**箇所のみ対象

4. **結果レポート**
   ファイルごとに未翻訳テキストを一覧表示:
   ```
   == i18n Scan Report ==

   templates/pages/overview.html (8 items)
     L12: <div class="label">Total Listings</div>
     L16: <div class="label">In Stock</div>
     ...

   static/js/agent.js (3 items)
     L52: btn.textContent = 'Processing...';
     ...

   Total: 24 untranslated strings in 6 files
   ```

---

## Mode: setup

言語切替の基盤コードを設置する。既存のコードを壊さない。

### 手順

1. **共有JSに i18n 関数を追加**
   対象: メインのJSファイル（`app.js`, `main.js`, `script.js` など）
   既に `getLang` 関数が存在する場合はスキップ。

   追加するコード:
   ```javascript
   /* ── Language Toggle ── */
   function getLang() {
       return localStorage.getItem('lang-pref') || 'en';
   }

   function t(en, ja) { return getLang() === 'ja' ? ja : en; }

   function applyLang(lang) {
       document.querySelectorAll('[data-en][data-ja]').forEach(el => {
           el.textContent = el.dataset[lang];
       });
       document.querySelectorAll('[data-placeholder-en][data-placeholder-ja]').forEach(el => {
           el.placeholder = lang === 'ja' ? el.dataset.placeholderJa : el.dataset.placeholderEn;
       });
       const label = document.getElementById('langLabel');
       if (label) label.textContent = lang === 'ja' ? 'JA' : 'EN';
   }

   function toggleLang() {
       const next = getLang() === 'en' ? 'ja' : 'en';
       localStorage.setItem('lang-pref', next);
       location.reload();
   }

   document.addEventListener('DOMContentLoaded', () => applyLang(getLang()));
   ```

2. **トグルUIの設置**
   ナビバーまたはヘッダーに言語切替ボタンを追加:
   ```html
   <button class="lang-toggle" onclick="toggleLang()" title="言語切替">
       <span class="lang-label" id="langLabel">EN</span>
   </button>
   ```
   配置場所はプロジェクトのナビ構造に合わせて判断する。

3. **CSSスタイル追加**（必要に応じて）
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
   .lang-toggle:hover { background: rgba(255,255,255,0.2); }
   ```

---

## Mode: apply

scan で検出したテキストに翻訳属性を一括適用する。

### 翻訳ルール

#### 静的HTML要素

`data-en` / `data-ja` 属性を追加し、デフォルトテキストはEnglishのまま:

**Before:**
```html
<h2>Price Alerts</h2>
```
**After:**
```html
<h2 data-en="Price Alerts" data-ja="価格アラート">Price Alerts</h2>
```

ページタイトル（Jinja2 block）はspanで囲む:
```html
{% block page_title %}<span data-en="Overview" data-ja="概要">Overview</span>{% endblock %}
```

#### input placeholder

`data-placeholder-en` / `data-placeholder-ja` を追加:

```html
<input placeholder="Search..." data-placeholder-en="Search..." data-placeholder-ja="検索...">
```

#### JS生成コンテンツ

テンプレートリテラル内のラベルを `t()` 関数で囲む:

**Before:**
```javascript
`<div class="label">Total Sales</div>`
```
**After:**
```javascript
`<div class="label">${t('Total Sales','総売上件数')}</div>`
```

ボタンテキストの動的設定:
```javascript
btn.textContent = t('Send', '送信');
```

Chart.js ラベル:
```javascript
{ label: t('Revenue', '売上'), data: ... }
```

#### 翻訳しないもの

- 固有名詞（SKU, URL, eBay, Google等）
- 数値・通貨記号
- プラットフォーム名（ヤフオク、メルカリ等 — 既に日本語）
- CSSクラス名やHTML属性値

### 翻訳の品質

- 自然な日本語を使う（機械翻訳っぽさを避ける）
- UIラベルは簡潔に（「在庫管理」「価格分析」「売上同期」）
- 文章は丁寧語で統一（「〜してください」「〜がありません」）
- 専門用語はカタカナ許容（「マージン」「ステータス」）

---

## Mode: full（デフォルト）

以下を順番に実行:

1. **setup** — 基盤コード設置
2. **scan** — 未翻訳テキスト検出
3. **apply** — 翻訳属性一括適用
4. **verify** — 全ファイルを再スキャンし、漏れがないか確認

### 最終レポート

```
== i18n Complete ==

Setup:
  ✅ Language functions added to static/js/app.js
  ✅ Toggle button added to templates/components/nav.html
  ✅ CSS styles added to static/css/style.css

Applied:
  ✅ templates/pages/overview.html — 12 strings translated
  ✅ templates/pages/inventory.html — 8 strings translated
  ...

Summary:
  Files modified: 9
  Strings translated: 67
  Language toggle: EN ↔ JA (localStorage)
```

---

## 対応テンプレートエンジン

| エンジン | 対応パターン |
|---|---|
| Jinja2 | `{% block %}`, `{% extends %}`, `{{ var }}` |
| Django | `{% block %}`, `{% include %}`, `{{ var }}` |
| 生HTML | そのまま |
| EJS | `<%= %>` |

Jinja2/Django の `{% block page_title %}` 内はspanで囲んで翻訳。
テンプレート変数（`{{ count }}`）はそのまま残す。

---

## 注意事項

- 既に `data-en` が付いている要素はスキップ（二重適用防止）
- 既に `t()` で囲まれているJS文字列はスキップ
- ファイル変更前に必ず現在の内容を Read で確認する
- 大量のファイルがある場合は TodoWrite で進捗管理する
- 翻訳に自信がない語句はコメント付きで提示し、ユーザーに確認する
