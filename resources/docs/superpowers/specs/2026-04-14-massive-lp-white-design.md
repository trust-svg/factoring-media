# Massive LP — White Redesign 仕様書

## Context

既存の `reusable/Dark Luxury/MassiveLP/` は50代男性向けマッチングLPだが、
ダーク系・明朝体・センター寄せのデザインで固定されている。

本仕様は同一セクション構成を維持しながら、フォント・レイアウト・カラーを
全面刷新し「パッと見で完全に別サイト」に見える新バリアントを制作するもの。

ターゲット: **「自分はまだ若い」と思っている50代男性**
出力先: `reusable/Massive White/index.html`（独立した静的HTMLファイル）

---

## デザインシステム

### カラー

| トークン | 値 | 用途 |
|---|---|---|
| `--clr-bg` | `#FFFFFF` | ベース背景 |
| `--clr-bg-tint` | `#FFF1F2` | セクション背景（交互） |
| `--clr-text` | `#1A0A0A` | 本文テキスト |
| `--clr-text-light` | `#6B4F52` | サブテキスト |
| `--clr-accent` | `#F43F5E` | アクセント・CTA装飾 |
| `--clr-accent-dark` | `#881337` | ホバー |
| `--clr-accent-light` | `#FFF1F2` | 薄いアクセント背景 |
| `--clr-line` | `#06C755` | LINE CTAボタン |
| `--clr-line-hover` | `#04A546` | LINE ホバー |

### タイポグラフィ

| 役割 | フォント | 備考 |
|---|---|---|
| 見出し（英） | Playfair Display | Google Fonts |
| 見出し（和） | Noto Serif JP | Google Fonts |
| 本文 | Noto Sans JP | Google Fonts |

フォントサイズスケール:
- Display: `clamp(48px, 8vw, 88px)`
- H2: `clamp(28px, 4vw, 48px)`
- H3: `clamp(20px, 2.5vw, 28px)`
- Body: `18px` / Line-height: `2.0`

### スペーシング

- セクション縦余白: `clamp(80px, 12vw, 160px)`
- コンテンツ最大幅: `1200px`
- グリッドgap: `60px`（SP: `32px`）
- ブレークポイント: `768px`（タブレット以下）、`480px`（スマホ）

---

## セクション構成

### ① Hero

**レイアウト**: 全幅フルスクリーン（100vh）
**写真**: 女性写真1枚（`img/hero.jpg`）を背景全幅
**オーバーレイ**: ローズグラデーション（`rgba(244,63,94,0.15)` → 透明）
**コピー**: 中央配置、Playfair Display + Noto Serif JP
**アニメーション**:
- 写真: Ken Burns（`transform: scale(1.0→1.08)` 8s ease-out）
- キャッチコピー: fadeUp（`translateY(40px→0)` + opacity, 1s, 0.3s delay）
- ローズ装飾線: 横方向に伸びる（`width: 0→80px` 1.5s）

コピー例:
```
（英）Still hunting.
（和）50代、まだ本番。
```

---

### ② 課題提示

**背景**: `#FFFFFF`
**レイアウト**: 中央寄せ、アイコン3つ横並び（SP: 縦並び）
**装飾**: 見出し下にローズの短いアンダーライン

課題3項目（既存Massiveと同内容）:
1. マッチングアプリで年齢で弾かれる
2. 何を書けばいいかわからない
3. 出会えても続かない

---

### ③ 比較（旧来 vs Massive）

**レイアウト**: 2カラム対比テーブル
- 左: グレー背景 `#F5F5F5`、× マーク、「よくある出会い」
- 右: ローズ薄背景 `#FFF1F2`、○ マーク、「Massive」

---

### ④ 特徴（3つ）— Splitレイアウト

**レイアウト**: 左右交互（写真60% + テキスト40%）
- 特徴1: 左写真（`img/feature1.jpg`）+ 右テキスト
- 特徴2: 右写真（`img/feature2.jpg`）+ 左テキスト
- 特徴3: 左写真（`img/feature3.jpg`）+ 右テキスト

**写真アニメーション**: スクロールparallax（`translateY`ずれ ±20px）
**テキストアニメーション**: fadeUp（Intersection Observer）

---

### ⑤ 夜デートバナー①

**レイアウト**: 全幅（`height: 500px`）
**写真**: 夜デート写真1枚（`img/night-date1.jpg`）、parallax固定
**テキスト**: 中央オーバーレイ、白文字、Playfair Display

---

### ⑥ スマホ操作イメージ

**レイアウト**: 右: スマホ画面写真（`img/smartphone.jpg`）+ 左: テキスト
**内容**: 既存と同一（「スマホひとつで」）

---

### ⑦ ステップ（3ステップ）

**背景**: `#FFF1F2`（ローズティント）
**レイアウト**: 横並び3カード（SP: 縦並び）
**番号**: Playfair Display、大きく（`font-size: 72px`）、ローズ色
**ステップ**:
1. LINEで無料登録
2. 匿名プロフィール登録
3. メッセージ開始

---

### ⑧ 女性フォトギャラリー

**レイアウト**: CSS Columns（3列 → SP: 2列）Masonry風
**写真**: 5〜6枚（`img/gallery1.jpg` 〜 `img/gallery6.jpg`）
**hover**: `scale(1.05)` + ローズオーバーレイ薄く（`rgba(244,63,94,0.15)`）

---

### ⑨ 安心・安全

**背景**: `#FFFFFF`
**レイアウト**: 3カード横並び、アイコン付き
**内容**: 既存と同一（安心・匿名・プライバシー）

---

### ⑩ 夜デートバナー②

**レイアウト**: 全幅（`height: 500px`）
**写真**: 夜デート写真2枚目（`img/night-date2.jpg`）、parallax固定
**役割**: Final CTAへの感情的な橋渡し

---

### ⑪ Final CTA

**背景**: `#FFF1F2`
**レイアウト**: 中央寄せ
**要素**: 大見出し + LINEボタン（pulse animation）
**LINEボタン**: `#06C755`、白テキスト、`border-radius: 9999px`

---

## アニメーション設計

| 要素 | アニメーション | 実装 |
|---|---|---|
| Hero写真 | Ken Burns（8s） | CSS `@keyframes` |
| Hero文字 | fadeUp + stagger | CSS + `animation-delay` |
| ローズ装飾線 | width 0→80px | CSS transition |
| スクロール要素 | fadeUp（Y40→0） | Intersection Observer |
| Split写真 | parallax（±20px） | JS scroll event |
| 全幅バナー | parallax背景 | CSS `background-attachment: fixed`（SP: fixed無効 → `background-size: cover` fallback） |
| ギャラリーhover | scale(1.05) | CSS transition |
| LINEボタン | pulse（1.5s loop） | CSS `@keyframes` |
| スクロール追従LINE | 固定表示 | CSS `position: fixed` |

---

## 写真素材

AI生成画像を使用。コード上はパスのみ定義、後から入れ替え可能。

| パス | 内容 |
|---|---|
| `img/hero.jpg` | ヒーロー女性写真（メイン） |
| `img/feature1.jpg` | 特徴1 女性写真 |
| `img/feature2.jpg` | 特徴2 女性写真 |
| `img/feature3.jpg` | 特徴3 女性写真 |
| `img/gallery1〜6.jpg` | ギャラリー女性写真（6枚） |
| `img/night-date1.jpg` | 夜デート写真1 |
| `img/night-date2.jpg` | 夜デート写真2 |
| `img/smartphone.jpg` | スマホ操作イメージ |

計: 女性写真10枚（hero1 + feature3 + gallery6）+ 夜デート2枚 + スマホ1枚

---

## 技術スタック

- **出力**: 単一 `index.html`（既存バリアントと同じ構成）
- **CSS**: CSS Variables + Flexbox/Grid（フレームワーク不使用）
- **フォント**: Google Fonts CDN
- **アイコン**: Font Awesome CDN
- **アニメーション**: CSS `@keyframes` + Intersection Observer（JS最小限）
- **外部依存**: Google Fonts + Font Awesome のみ

---

## 出力先

```
reusable/
└── Massive White/
    ├── index.html
    └── img/
        ├── hero.jpg         （プレースホルダー）
        ├── feature1〜3.jpg  （プレースホルダー）
        ├── gallery1〜6.jpg  （プレースホルダー）
        ├── night-date1.jpg  （プレースホルダー）
        ├── night-date2.jpg  （プレースホルダー）
        └── smartphone.jpg   （プレースホルダー）
```

---

## 検証方法

1. ブラウザで `index.html` を開き全セクションを目視確認
2. Chrome DevTools でモバイル（375px）表示を確認
3. スクロールアニメーションが各セクションで発火することを確認
4. 既存 `Dark Luxury/MassiveLP/index.html` と並べて「別サイトに見える」か確認
5. LINEボタンのpulseアニメーション・固定アイコンの動作確認
6. 画像パスをプレースホルダーのまま開いてレイアウト崩れがないことを確認
