# Massive White LP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `reusable/Massive White/index.html` として、既存Massive LP（Dark Luxury版）と同一コンテンツながら、白ベース×ローズ×Playfair Display×Split Layoutで完全に別サイトに見えるLPを静的HTMLで制作する。

**Architecture:** 単一の `index.html` にCSS・JSを全てインライン記述。外部依存はGoogle Fonts・Font Awesome CDNのみ。Intersection Observerでスクロールアニメーション制御。画像はプレースホルダーパスで実装し後から差し替え。

**Tech Stack:** HTML5, CSS Variables, CSS Grid/Flexbox, CSS `@keyframes`, Intersection Observer API, Google Fonts（Playfair Display + Noto Serif JP + Noto Sans JP）, Font Awesome 6

**Spec:** `docs/superpowers/specs/2026-04-14-massive-lp-white-design.md`

---

## ファイル構成

```
reusable/Massive White/
├── index.html       ← 全コード（CSS・JS込み）
└── img/
    ├── hero.jpg          （プレースホルダー）
    ├── feature1.jpg      （プレースホルダー）
    ├── feature2.jpg      （プレースホルダー）
    ├── feature3.jpg      （プレースホルダー）
    ├── gallery1.jpg      （プレースホルダー）
    ├── gallery2.jpg      （プレースホルダー）
    ├── gallery3.jpg      （プレースホルダー）
    ├── gallery4.jpg      （プレースホルダー）
    ├── gallery5.jpg      （プレースホルダー）
    ├── gallery6.jpg      （プレースホルダー）
    ├── night-date1.jpg   （プレースホルダー）
    ├── night-date2.jpg   （プレースホルダー）
    └── smartphone.jpg    （プレースホルダー）
```

---

## Task 1: ディレクトリ作成 + プレースホルダー画像生成

**Files:**
- Create: `reusable/Massive White/img/` ディレクトリ
- Create: `reusable/Massive White/img/*.jpg` プレースホルダー

- [ ] **Step 1: ディレクトリ作成**

```bash
mkdir -p "reusable/Massive White/img"
```

- [ ] **Step 2: プレースホルダー画像生成（Python）**

```bash
python3 -c "
from PIL import Image, ImageDraw
import os

imgs = {
    'hero': (1920, 1080, '#D4A5B5'),
    'feature1': (800, 900, '#F9C0CC'),
    'feature2': (800, 900, '#F5A8B8'),
    'feature3': (800, 900, '#F0909C'),
    'gallery1': (600, 800, '#FDB8C4'),
    'gallery2': (600, 700, '#FCA5B0'),
    'gallery3': (600, 900, '#FB92A0'),
    'gallery4': (600, 800, '#FA7F90'),
    'gallery5': (600, 700, '#F96C80'),
    'gallery6': (600, 800, '#F85970'),
    'night-date1': (1920, 900, '#2A1520'),
    'night-date2': (1920, 900, '#1A0A15'),
    'smartphone': (600, 900, '#FFF1F2'),
}

base = 'reusable/Massive White/img'
for name, (w, h, color) in imgs.items():
    img = Image.new('RGB', (w, h), color)
    d = ImageDraw.Draw(img)
    d.text((w//2 - 50, h//2), name, fill='#FFFFFF')
    img.save(f'{base}/{name}.jpg')
    print(f'Created {name}.jpg')
print('Done')
"
```

> Pillowがない場合: `pip install Pillow` または後続タスクで `img/` パスのままで進める（ブラウザは broken image で表示されるが動作確認は可能）

- [ ] **Step 3: 動作確認**

```bash
ls "reusable/Massive White/img/"
```

Expected: 13ファイルが表示される

---

## Task 2: HTMLスケルトン + デザインシステム（CSS Variables）

**Files:**
- Create: `reusable/Massive White/index.html`

- [ ] **Step 1: `index.html` を作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>50代、まだ本番。大人のシークレットマッチング | Massive</title>
  <meta name="description" content="「自分はまだ若い」そんな50代男性のための、プライバシー重視のシークレットマッチング。">

  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Noto+Serif+JP:wght@400;700&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">

  <!-- Font Awesome -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">

  <style>
    /* ============================================================
       Design Tokens
    ============================================================ */
    :root {
      --clr-bg:           #FFFFFF;
      --clr-bg-tint:      #FFF1F2;
      --clr-text:         #1A0A0A;
      --clr-text-light:   #6B4F52;
      --clr-accent:       #F43F5E;
      --clr-accent-dark:  #881337;
      --clr-accent-light: #FFF1F2;
      --clr-line:         #06C755;
      --clr-line-hover:   #04A546;
      --clr-gray:         #F5F5F5;
      --clr-border:       #F0D0D5;

      --font-display:  'Playfair Display', Georgia, serif;
      --font-serif-jp: 'Noto Serif JP', 'Yu Mincho', serif;
      --font-body:     'Noto Sans JP', 'Hiragino Sans', sans-serif;

      --space-section: clamp(80px, 12vw, 160px);
      --container-max: 1200px;
      --radius-sm:  4px;
      --radius-md:  12px;
      --radius-lg:  24px;
      --radius-full: 9999px;

      --shadow-sm: 0 2px 8px rgba(244, 63, 94, 0.08);
      --shadow-md: 0 8px 32px rgba(244, 63, 94, 0.12);
      --shadow-lg: 0 16px 48px rgba(244, 63, 94, 0.16);
    }

    /* ============================================================
       Reset & Base
    ============================================================ */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; font-size: 16px; overflow-x: hidden; }
    body {
      font-family: var(--font-body);
      color: var(--clr-text);
      background: var(--clr-bg);
      line-height: 2.0;
      font-size: 1.125rem;
      -webkit-font-smoothing: antialiased;
    }
    img { max-width: 100%; height: auto; display: block; }
    a { color: inherit; text-decoration: none; }

    /* ============================================================
       Layout Utilities
    ============================================================ */
    .container {
      max-width: var(--container-max);
      margin: 0 auto;
      padding: 0 clamp(20px, 5vw, 60px);
    }
    .section {
      padding: var(--space-section) 0;
    }
    .section--tint { background: var(--clr-bg-tint); }
    .section--gray  { background: var(--clr-gray); }

    /* ============================================================
       Typography
    ============================================================ */
    .section-label {
      font-family: var(--font-display);
      font-size: clamp(11px, 1.5vw, 13px);
      letter-spacing: 0.25em;
      text-transform: uppercase;
      color: var(--clr-accent);
      display: block;
      margin-bottom: 12px;
    }
    .section-title {
      font-family: var(--font-serif-jp);
      font-size: clamp(26px, 4vw, 44px);
      font-weight: 700;
      line-height: 1.4;
      margin-bottom: 24px;
    }
    .section-title--en {
      font-family: var(--font-display);
      font-style: italic;
    }
    .rose-line {
      width: 0;
      height: 2px;
      background: var(--clr-accent);
      margin: 0 auto 40px;
      transition: width 1.5s ease;
    }
    .rose-line.animated { width: 80px; }

    /* ============================================================
       Buttons
    ============================================================ */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 18px 40px;
      border-radius: var(--radius-full);
      font-family: var(--font-body);
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.3s ease;
      border: none;
    }
    .btn--line {
      background: var(--clr-line);
      color: #fff;
      font-size: 1.125rem;
      padding: 20px 48px;
      box-shadow: 0 4px 20px rgba(6, 199, 85, 0.35);
    }
    .btn--line:hover {
      background: var(--clr-line-hover);
      transform: translateY(-2px);
      box-shadow: 0 8px 28px rgba(6, 199, 85, 0.45);
    }

    /* ============================================================
       Scroll Animation Base
    ============================================================ */
    .fade-up {
      opacity: 0;
      transform: translateY(40px);
      transition: opacity 0.8s ease, transform 0.8s ease;
    }
    .fade-up.visible {
      opacity: 1;
      transform: translateY(0);
    }
    .fade-up.delay-1 { transition-delay: 0.1s; }
    .fade-up.delay-2 { transition-delay: 0.2s; }
    .fade-up.delay-3 { transition-delay: 0.3s; }
    .fade-up.delay-4 { transition-delay: 0.4s; }
  </style>
</head>
<body>

  <!-- Sections will be added in subsequent tasks -->
  <p style="padding:40px;text-align:center;color:#F43F5E;">Massive White LP — Building...</p>

</body>
</html>
```

- [ ] **Step 2: ブラウザで確認**

`reusable/Massive White/index.html` をブラウザで開く。
Expected: 白背景に「Massive White LP — Building...」がローズ色で表示される。Consoleエラーなし。

- [ ] **Step 3: コミット**

```bash
git add "reusable/Massive White/"
git commit -m "feat: scaffold Massive White LP with design system"
```

---

## Task 3: Hero セクション

**Files:**
- Modify: `reusable/Massive White/index.html` — body内 + style内

- [ ] **Step 1: Hero CSS を `</style>` の直前に追記**

```css
/* ============================================================
   Hero
============================================================ */
.hero {
  position: relative;
  height: 100vh;
  min-height: 600px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.hero__bg {
  position: absolute;
  inset: 0;
  background-image: url('img/hero.jpg');
  background-size: cover;
  background-position: center;
  animation: kenBurns 8s ease-out forwards;
  z-index: 0;
}
@keyframes kenBurns {
  from { transform: scale(1.0); }
  to   { transform: scale(1.08); }
}
.hero__overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(244, 63, 94, 0.18) 0%,
    rgba(0, 0, 0, 0.35) 100%
  );
  z-index: 1;
}
.hero__content {
  position: relative;
  z-index: 2;
  color: #fff;
  padding: 0 20px;
}
.hero__label {
  font-family: var(--font-display);
  font-size: clamp(12px, 1.5vw, 14px);
  letter-spacing: 0.3em;
  text-transform: uppercase;
  opacity: 0;
  animation: fadeUp 1s ease 0.2s forwards;
  margin-bottom: 16px;
  display: block;
}
.hero__title-en {
  font-family: var(--font-display);
  font-style: italic;
  font-size: clamp(52px, 9vw, 100px);
  line-height: 1.1;
  opacity: 0;
  animation: fadeUp 1s ease 0.4s forwards;
  display: block;
}
.hero__title-jp {
  font-family: var(--font-serif-jp);
  font-size: clamp(22px, 3.5vw, 42px);
  font-weight: 700;
  letter-spacing: 0.1em;
  opacity: 0;
  animation: fadeUp 1s ease 0.6s forwards;
  display: block;
  margin-top: 8px;
  margin-bottom: 32px;
}
.hero__line {
  width: 0;
  height: 2px;
  background: rgba(255,255,255,0.6);
  margin: 0 auto 32px;
  animation: lineExpand 1.5s ease 0.8s forwards;
}
.hero__cta {
  opacity: 0;
  animation: fadeUp 1s ease 1s forwards;
}
.hero__note {
  font-size: 0.8rem;
  opacity: 0.7;
  margin-top: 12px;
  animation: fadeUp 1s ease 1.2s forwards;
  opacity: 0;
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(30px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes lineExpand {
  from { width: 0; }
  to   { width: 80px; }
}
```

- [ ] **Step 2: Hero HTML を `<body>` 内の placeholder pタグと差し替え**

```html
<!-- ① Hero -->
<section class="hero">
  <div class="hero__bg"></div>
  <div class="hero__overlay"></div>
  <div class="hero__content">
    <span class="hero__label">Secret Matching for 50s</span>
    <span class="hero__title-en">Still hunting.</span>
    <span class="hero__title-jp">50代、まだ本番。</span>
    <div class="hero__line"></div>
    <div class="hero__cta">
      <a href="#" class="btn btn--line">
        <i class="fa-brands fa-line"></i>
        今すぐLINEで無料お試し
      </a>
    </div>
    <p class="hero__note">※完全匿名・誰にもバレずに始められます</p>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected:
- 全画面ローズがかった写真背景（img/hero.jpg → プレースホルダーのピンク矩形）
- 「Still hunting.」が大きなイタリックで表示
- 文字とLINEボタンがfadeUpで現れる
- Ken Burns効果でわずかにズームしていく

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add Hero section with Ken Burns and fade animations"
```

---

## Task 4: 課題提示セクション（Empathy）

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: Empathy CSS を追記**

```css
/* ============================================================
   Empathy (課題提示)
============================================================ */
.empathy__header { text-align: center; margin-bottom: 60px; }
.empathy__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
  margin-bottom: 56px;
}
.empathy__card {
  background: var(--clr-bg);
  border: 1px solid var(--clr-border);
  border-radius: var(--radius-md);
  padding: 40px 28px;
  text-align: center;
  box-shadow: var(--shadow-sm);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.empathy__card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-md);
}
.empathy__icon {
  font-size: 2.5rem;
  color: var(--clr-accent);
  margin-bottom: 20px;
}
.empathy__card p {
  font-size: 1rem;
  color: var(--clr-text);
  line-height: 1.8;
}
.empathy__solution {
  background: var(--clr-bg-tint);
  border: 2px solid var(--clr-accent);
  border-radius: var(--radius-md);
  padding: 48px 40px;
  text-align: center;
  max-width: 780px;
  margin: 0 auto;
}
.empathy__solution p {
  font-family: var(--font-serif-jp);
  font-size: clamp(17px, 2vw, 22px);
  line-height: 2.0;
}
.empathy__solution strong {
  color: var(--clr-accent);
}
@media (max-width: 768px) {
  .empathy__grid { grid-template-columns: 1fr; gap: 20px; }
}
```

- [ ] **Step 2: Empathy HTML を Hero の直後に追記**

```html
<!-- ② 課題提示 -->
<section class="section">
  <div class="container">
    <div class="empathy__header fade-up">
      <span class="section-label">Secret Desire</span>
      <h2 class="section-title">こんな本音、<br>隠していませんか？</h2>
      <div class="rose-line"></div>
    </div>

    <div class="empathy__grid">
      <div class="empathy__card fade-up delay-1">
        <i class="fa-solid fa-champagne-glasses empathy__icon"></i>
        <p>気軽に女性と出会いたいが<br>きっかけがなくて困っている</p>
      </div>
      <div class="empathy__card fade-up delay-2">
        <i class="fa-solid fa-fire-flame-curved empathy__icon"></i>
        <p>ハイスペックではないが<br>「男」として見られたい</p>
      </div>
      <div class="empathy__card fade-up delay-3">
        <i class="fa-solid fa-ban empathy__icon"></i>
        <p>真剣すぎる婚活は重い…<br>気楽な大人の関係がほしい</p>
      </div>
    </div>

    <div class="empathy__solution fade-up">
      <p>
        <strong>「Massive」</strong>は、<br>
        そんな<em>「飾らない50代以上の男性」</em>と<br>
        女性をつなぐ、プライバシー重視の<br>
        シークレットマッチングです。
      </p>
    </div>
  </div>
</section>
```

- [ ] **Step 3: Intersection Observer JS を `</body>` 直前に追加**

（Task 3で追加していない場合のみ）

```html
<script>
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      // rose-line専用
      const rl = e.target.querySelector('.rose-line');
      if (rl) rl.classList.add('animated');
    }
  });
}, { threshold: 0.15 });

document.querySelectorAll('.fade-up, .rose-line').forEach(el => observer.observe(el));
</script>
```

- [ ] **Step 4: ブラウザで確認**

Expected: 白背景・3カードがスクロールでfadeUp・ローズ線が伸びる・ソリューションボックスにローズボーダー

- [ ] **Step 5: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add Empathy section with scroll animations"
```

---

## Task 5: 比較セクション（旧来 vs Massive）

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: 比較 CSS を追記**

```css
/* ============================================================
   Compare
============================================================ */
.compare { text-align: center; }
.compare__header { margin-bottom: 60px; }
.compare__table {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  max-width: 860px;
  margin: 0 auto;
}
.compare__col { padding: 40px 36px; }
.compare__col--old {
  background: var(--clr-gray);
  color: var(--clr-text-light);
}
.compare__col--new {
  background: var(--clr-bg-tint);
  color: var(--clr-text);
}
.compare__col-title {
  font-family: var(--font-serif-jp);
  font-size: 1.2rem;
  font-weight: 700;
  margin-bottom: 28px;
  padding-bottom: 16px;
  border-bottom: 2px solid;
}
.compare__col--old .compare__col-title { border-color: #ddd; color: #999; }
.compare__col--new .compare__col-title { border-color: var(--clr-accent); color: var(--clr-accent); }
.compare__item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 0.95rem;
  line-height: 1.6;
  text-align: left;
}
.compare__item i { margin-top: 3px; flex-shrink: 0; font-size: 1rem; }
.compare__col--old  i { color: #bbb; }
.compare__col--new i { color: var(--clr-accent); }
@media (max-width: 640px) {
  .compare__table { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: 比較 HTML を追記**

```html
<!-- ③ 比較 -->
<section class="section section--gray compare">
  <div class="container">
    <div class="compare__header fade-up">
      <span class="section-label">Why Massive</span>
      <h2 class="section-title">よくある出会い vs <span style="color:var(--clr-accent)">Massive</span></h2>
      <div class="rose-line"></div>
    </div>

    <div class="compare__table fade-up">
      <div class="compare__col compare__col--old">
        <div class="compare__col-title">よくある出会い</div>
        <div class="compare__item"><i class="fa-solid fa-xmark"></i><span>年齢でフィルタリングされる</span></div>
        <div class="compare__item"><i class="fa-solid fa-xmark"></i><span>プロフィールの書き方がわからない</span></div>
        <div class="compare__item"><i class="fa-solid fa-xmark"></i><span>実名・顔出しが必要で不安</span></div>
        <div class="compare__item"><i class="fa-solid fa-xmark"></i><span>マッチングしても会話が続かない</span></div>
        <div class="compare__item"><i class="fa-solid fa-xmark"></i><span>周囲にバレるリスクがある</span></div>
      </div>
      <div class="compare__col compare__col--new">
        <div class="compare__col-title">Massive</div>
        <div class="compare__item"><i class="fa-solid fa-check"></i><span>50代以上が「選ばれる」設計</span></div>
        <div class="compare__item"><i class="fa-solid fa-check"></i><span>プロフィール作成をサポート</span></div>
        <div class="compare__item"><i class="fa-solid fa-check"></i><span>完全匿名・シークレット利用</span></div>
        <div class="compare__item"><i class="fa-solid fa-check"></i><span>AIが会話のきっかけを提案</span></div>
        <div class="compare__item"><i class="fa-solid fa-check"></i><span>誰にも知られずに始められる</span></div>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected: 左グレー×マーク / 右ローズ薄背景チェックマークの2カラム対比テーブル

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add Compare section"
```

---

## Task 6: 特徴セクション（Split Layout × 3）

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: Split CSS を追記**

```css
/* ============================================================
   Features (Split Layout)
============================================================ */
.features__header { text-align: center; margin-bottom: 80px; }
.feature-split {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 80px;
  align-items: center;
  margin-bottom: 120px;
}
.feature-split:last-child { margin-bottom: 0; }
.feature-split--reverse { grid-template-columns: 2fr 3fr; }
.feature-split--reverse .feature-split__img { order: 2; }
.feature-split--reverse .feature-split__text { order: 1; }
.feature-split__img-wrap {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.feature-split__img-wrap img {
  width: 100%;
  aspect-ratio: 4/5;
  object-fit: cover;
  transition: transform 0.6s ease;
}
.feature-split__img-wrap:hover img { transform: scale(1.04); }
.feature-split__accent {
  position: absolute;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: var(--clr-accent);
  opacity: 0.12;
  bottom: -30px;
  right: -30px;
  pointer-events: none;
}
.feature-split__num {
  font-family: var(--font-display);
  font-size: clamp(60px, 8vw, 96px);
  color: var(--clr-bg-tint);
  line-height: 1;
  margin-bottom: -16px;
  font-weight: 700;
}
.feature-split__title {
  font-family: var(--font-serif-jp);
  font-size: clamp(22px, 2.8vw, 34px);
  font-weight: 700;
  line-height: 1.4;
  margin-bottom: 24px;
  color: var(--clr-text);
}
.feature-split__desc {
  color: var(--clr-text-light);
  font-size: 1rem;
  line-height: 2.0;
}
@media (max-width: 768px) {
  .feature-split,
  .feature-split--reverse { grid-template-columns: 1fr; gap: 40px; }
  .feature-split--reverse .feature-split__img { order: 0; }
  .feature-split--reverse .feature-split__text { order: 0; }
}
```

- [ ] **Step 2: Features HTML を追記**

```html
<!-- ④ 特徴 -->
<section class="section">
  <div class="container">
    <div class="features__header fade-up">
      <span class="section-label">Features</span>
      <h2 class="section-title">Massiveが選ばれる<br>3つの理由</h2>
      <div class="rose-line"></div>
    </div>

    <!-- 特徴1: 左写真 + 右テキスト -->
    <div class="feature-split fade-up">
      <div class="feature-split__img">
        <div class="feature-split__img-wrap">
          <img src="img/feature1.jpg" alt="50代男性が選ばれる理由">
          <div class="feature-split__accent"></div>
        </div>
      </div>
      <div class="feature-split__text">
        <div class="feature-split__num">01</div>
        <h3 class="feature-split__title">「落ち着いた男性が好き」<br>そんな女性が急増中</h3>
        <p class="feature-split__desc">
          「若い男性とは合わない」「歳を重ねた落ち着いた男性がいい」という女性が急増しています。背伸びする必要も、無理に若作りする必要もありません。ありのままの自分で、気の合う女性と自然に出会える場所です。
        </p>
      </div>
    </div>

    <!-- 特徴2: 右写真 + 左テキスト -->
    <div class="feature-split feature-split--reverse fade-up">
      <div class="feature-split__img">
        <div class="feature-split__img-wrap">
          <img src="img/feature2.jpg" alt="完全匿名のシークレット利用">
          <div class="feature-split__accent"></div>
        </div>
      </div>
      <div class="feature-split__text">
        <div class="feature-split__num">02</div>
        <h3 class="feature-split__title">完全匿名・誰にも<br>バレない安心設計</h3>
        <p class="feature-split__desc">
          実名登録不要。顔写真も任意です。プライバシーを守りながら、安心してメッセージを楽しめます。会社の同僚にも、家族にも、一切バレません。
        </p>
      </div>
    </div>

    <!-- 特徴3: 左写真 + 右テキスト -->
    <div class="feature-split fade-up">
      <div class="feature-split__img">
        <div class="feature-split__img-wrap">
          <img src="img/feature3.jpg" alt="スマホひとつで簡単登録">
          <div class="feature-split__accent"></div>
        </div>
      </div>
      <div class="feature-split__text">
        <div class="feature-split__num">03</div>
        <h3 class="feature-split__title">スマホひとつで<br>今夜から始められる</h3>
        <p class="feature-split__desc">
          LINEさえあればすぐに始められます。面倒な本人確認や複雑な設定は一切なし。登録から3分で女性とメッセージできる状態になります。
        </p>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected: 写真左右交互のSplit Layout。大きな薄いナンバー（01/02/03）がアクセントに。ホバーで写真がわずかにズーム。

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add Features split layout section"
```

---

## Task 7: 夜デートバナー①

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: バナー CSS を追記**

```css
/* ============================================================
   Full-Width Banner (夜デート写真)
============================================================ */
.banner-full {
  position: relative;
  height: 500px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.banner-full__bg {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
  background-attachment: fixed;  /* parallax */
  transition: transform 0.1s linear;
}
@media (max-width: 768px) {
  /* iOS Safariではfixedが動作しないためfallback */
  .banner-full__bg { background-attachment: scroll; }
}
.banner-full__overlay {
  position: absolute;
  inset: 0;
  background: rgba(10, 5, 10, 0.55);
}
.banner-full__content {
  position: relative;
  z-index: 2;
  color: #fff;
  padding: 0 20px;
}
.banner-full__title {
  font-family: var(--font-display);
  font-style: italic;
  font-size: clamp(32px, 5vw, 60px);
  line-height: 1.3;
  margin-bottom: 8px;
}
.banner-full__sub {
  font-family: var(--font-serif-jp);
  font-size: clamp(16px, 2vw, 22px);
  opacity: 0.85;
}
```

- [ ] **Step 2: バナー① HTML を特徴セクションの直後に追記**

```html
<!-- ⑤ 夜デートバナー① -->
<div class="banner-full fade-up">
  <div class="banner-full__bg" style="background-image: url('img/night-date1.jpg');"></div>
  <div class="banner-full__overlay"></div>
  <div class="banner-full__content">
    <div class="banner-full__title">Tonight could change<br>everything.</div>
    <p class="banner-full__sub">今夜、新しい出会いが始まる。</p>
  </div>
</div>
```

- [ ] **Step 3: ブラウザで確認**

Expected: 全幅の暗い夜写真（プレースホルダー）に白テキストオーバーレイ。スクロールでparallax効果。

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add night date banner #1 with parallax"
```

---

## Task 8: スマホ操作 + ステップセクション

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: スマホ + ステップ CSS を追記**

```css
/* ============================================================
   Smartphone Section
============================================================ */
.smartphone-split {
  display: grid;
  grid-template-columns: 2fr 3fr;
  gap: 80px;
  align-items: center;
}
.smartphone-split__img img {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 320px;
  margin: 0 auto;
}
@media (max-width: 768px) {
  .smartphone-split { grid-template-columns: 1fr; gap: 40px; }
}

/* ============================================================
   Steps
============================================================ */
.steps__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 40px;
  margin-top: 60px;
}
.step-card {
  text-align: center;
  padding: 48px 24px;
  background: var(--clr-bg);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  position: relative;
}
.step-card__num {
  font-family: var(--font-display);
  font-size: 80px;
  font-weight: 700;
  color: var(--clr-bg-tint);
  line-height: 1;
  margin-bottom: -8px;
}
.step-card__title {
  font-family: var(--font-serif-jp);
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--clr-text);
}
.step-card__desc {
  font-size: 0.9rem;
  color: var(--clr-text-light);
  line-height: 1.8;
}
.step-card::after {
  content: '→';
  position: absolute;
  right: -28px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.5rem;
  color: var(--clr-accent);
  opacity: 0.5;
}
.step-card:last-child::after { display: none; }
@media (max-width: 768px) {
  .steps__grid { grid-template-columns: 1fr; }
  .step-card::after { content: '↓'; right: auto; top: auto; bottom: -28px; left: 50%; transform: translateX(-50%); }
}
```

- [ ] **Step 2: スマホ + ステップ HTML を追記**

```html
<!-- ⑥ スマホ操作 -->
<section class="section">
  <div class="container">
    <div class="smartphone-split fade-up">
      <div class="smartphone-split__img">
        <img src="img/smartphone.jpg" alt="スマホ操作イメージ">
      </div>
      <div class="smartphone-split__text">
        <span class="section-label">Easy to Start</span>
        <h2 class="section-title">スマホひとつで、<br>今夜から新しい出会いを。</h2>
        <p style="color:var(--clr-text-light);line-height:2.0;">
          難しい操作は一切不要。LINEさえあればすぐに始められます。登録から3分で女性とメッセージできる状態に。
        </p>
      </div>
    </div>
  </div>
</section>

<!-- ⑦ ステップ -->
<section class="section section--tint">
  <div class="container">
    <div class="fade-up" style="text-align:center;margin-bottom:16px;">
      <span class="section-label">How to Start</span>
      <h2 class="section-title">3ステップで始める</h2>
      <div class="rose-line"></div>
    </div>

    <div class="steps__grid">
      <div class="step-card fade-up delay-1">
        <div class="step-card__num">01</div>
        <div class="step-card__title">LINEで無料登録</div>
        <p class="step-card__desc">下のボタンからLINEを追加するだけ。実名不要・完全無料。</p>
      </div>
      <div class="step-card fade-up delay-2">
        <div class="step-card__num">02</div>
        <div class="step-card__title">匿名プロフィール登録</div>
        <p class="step-card__desc">ニックネームと簡単な情報を入力。顔写真は任意です。</p>
      </div>
      <div class="step-card fade-up delay-3">
        <div class="step-card__num">03</div>
        <div class="step-card__title">メッセージ開始</div>
        <p class="step-card__desc">気になる女性にメッセージ。今夜から新しい出会いが始まります。</p>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected: スマホ写真+テキストのSplit。ステップカードが矢印でつながる横並び3カード（ローズティント背景）

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add Smartphone and Steps sections"
```

---

## Task 9: フォトギャラリーセクション

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: ギャラリー CSS を追記**

```css
/* ============================================================
   Photo Gallery
============================================================ */
.gallery__header { text-align: center; margin-bottom: 60px; }
.gallery__grid {
  columns: 3;
  column-gap: 16px;
}
.gallery__item {
  break-inside: avoid;
  margin-bottom: 16px;
  overflow: hidden;
  border-radius: var(--radius-md);
  position: relative;
}
.gallery__item img {
  width: 100%;
  display: block;
  transition: transform 0.5s ease;
}
.gallery__item::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(244, 63, 94, 0.15);
  opacity: 0;
  transition: opacity 0.4s ease;
  border-radius: var(--radius-md);
}
.gallery__item:hover img { transform: scale(1.05); }
.gallery__item:hover::after { opacity: 1; }
@media (max-width: 768px) { .gallery__grid { columns: 2; } }
@media (max-width: 480px) { .gallery__grid { columns: 1; } }
```

- [ ] **Step 2: ギャラリー HTML を追記**

```html
<!-- ⑧ フォトギャラリー -->
<section class="section">
  <div class="container">
    <div class="gallery__header fade-up">
      <span class="section-label">Members</span>
      <h2 class="section-title">Massiveに集まる女性たち</h2>
      <div class="rose-line"></div>
    </div>

    <div class="gallery__grid fade-up">
      <div class="gallery__item"><img src="img/gallery1.jpg" alt="会員女性1"></div>
      <div class="gallery__item"><img src="img/gallery2.jpg" alt="会員女性2"></div>
      <div class="gallery__item"><img src="img/gallery3.jpg" alt="会員女性3"></div>
      <div class="gallery__item"><img src="img/gallery4.jpg" alt="会員女性4"></div>
      <div class="gallery__item"><img src="img/gallery5.jpg" alt="会員女性5"></div>
      <div class="gallery__item"><img src="img/gallery6.jpg" alt="会員女性6"></div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected: Masonry風3カラムグリッド。ホバーでローズオーバーレイ + 拡大。

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add photo gallery section"
```

---

## Task 10: 安心・安全セクション

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: 安心 CSS を追記**

```css
/* ============================================================
   Safety
============================================================ */
.safety__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
  margin-top: 60px;
}
.safety__card {
  padding: 40px 28px;
  border: 1px solid var(--clr-border);
  border-radius: var(--radius-lg);
  text-align: center;
  background: var(--clr-bg);
  transition: box-shadow 0.3s ease, transform 0.3s ease;
}
.safety__card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-4px);
}
.safety__icon {
  font-size: 2.5rem;
  color: var(--clr-accent);
  margin-bottom: 20px;
}
.safety__title {
  font-family: var(--font-serif-jp);
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 12px;
}
.safety__desc {
  font-size: 0.9rem;
  color: var(--clr-text-light);
  line-height: 1.8;
}
@media (max-width: 768px) {
  .safety__grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: 安心 HTML を追記**

```html
<!-- ⑨ 安心・安全 -->
<section class="section section--gray">
  <div class="container">
    <div class="fade-up" style="text-align:center;">
      <span class="section-label">Trust & Safety</span>
      <h2 class="section-title">安心して始められる<br>3つの保証</h2>
      <div class="rose-line"></div>
    </div>

    <div class="safety__grid">
      <div class="safety__card fade-up delay-1">
        <i class="fa-solid fa-shield-halved safety__icon"></i>
        <div class="safety__title">安心・安全の出会いを保証</div>
        <p class="safety__desc">全会員を厳正に審査。業者・サクラ・悪質ユーザーを徹底ブロックします。</p>
      </div>
      <div class="safety__card fade-up delay-2">
        <i class="fa-solid fa-user-secret safety__icon"></i>
        <div class="safety__title">完全匿名・シークレット利用</div>
        <p class="safety__desc">実名・顔写真は不要。ニックネームで完全匿名のまま利用できます。</p>
      </div>
      <div class="safety__card fade-up delay-3">
        <i class="fa-solid fa-lock safety__icon"></i>
        <div class="safety__title">プライバシー重視の安心設計</div>
        <p class="safety__desc">個人情報は暗号化して厳重に管理。外部への情報漏えいは一切ありません。</p>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected: 3カード横並び、ローズアイコン、ホバーで浮き上がる効果。

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add Safety section"
```

---

## Task 11: 夜デートバナー② + Final CTA

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: Final CTA CSS を追記**

```css
/* ============================================================
   Final CTA
============================================================ */
.final-cta {
  text-align: center;
  padding: var(--space-section) 0;
  background: var(--clr-bg-tint);
}
.final-cta__title {
  font-family: var(--font-serif-jp);
  font-size: clamp(28px, 4vw, 48px);
  font-weight: 700;
  line-height: 1.5;
  margin-bottom: 32px;
}
.final-cta__title em {
  color: var(--clr-accent);
  font-style: normal;
}
.final-cta__note {
  font-size: 0.85rem;
  color: var(--clr-text-light);
  margin-top: 16px;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 4px 20px rgba(6,199,85,0.35); }
  50%       { box-shadow: 0 4px 36px rgba(6,199,85,0.60); transform: scale(1.02); }
}
.btn--pulse { animation: pulse 1.5s ease-in-out infinite; }
```

- [ ] **Step 2: バナー② + Final CTA HTML を追記**

```html
<!-- ⑩ 夜デートバナー② -->
<div class="banner-full fade-up">
  <div class="banner-full__bg" style="background-image: url('img/night-date2.jpg');"></div>
  <div class="banner-full__overlay"></div>
  <div class="banner-full__content">
    <div class="banner-full__title">Your story starts<br>tonight.</div>
    <p class="banner-full__sub">あなたの物語は、今夜から始まる。</p>
  </div>
</div>

<!-- ⑪ Final CTA -->
<section class="final-cta">
  <div class="container">
    <div class="fade-up">
      <h2 class="final-cta__title">
        極上の出会いを、<br>
        <em>今夜から。</em>
      </h2>
      <a href="#" class="btn btn--line btn--pulse">
        <i class="fa-brands fa-line"></i>
        LINEを追加して無料スタート
      </a>
      <p class="final-cta__note">※完全匿名・実名登録不要・今すぐ始められます</p>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認**

Expected: 夜写真バナー → ローズ薄背景のFinal CTA → LINEボタンがpulseアニメーション

- [ ] **Step 4: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add night banner #2 and Final CTA"
```

---

## Task 12: 固定LINEボタン + 全体スクロールJS

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: 固定ボタン CSS を追記**

```css
/* ============================================================
   Floating LINE Button
============================================================ */
.float-line {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 999;
  background: var(--clr-line);
  color: #fff;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8rem;
  box-shadow: 0 4px 20px rgba(6,199,85,0.5);
  text-decoration: none;
  transition: transform 0.3s ease, opacity 0.4s ease;
  opacity: 0;
}
.float-line.show { opacity: 1; }
.float-line:hover { transform: scale(1.1); }
```

- [ ] **Step 2: 固定ボタン HTML を `</body>` 直前に追加**

```html
<!-- Floating LINE -->
<a href="#" class="float-line" id="floatLine">
  <i class="fa-brands fa-line"></i>
</a>
```

- [ ] **Step 3: JS（`<script>` タグ）を更新 — Intersection Observer + 固定ボタン表示**

既存の `<script>` タグを以下に差し替える:

```html
<script>
  // Scroll animations
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        const rl = e.target.querySelector('.rose-line');
        if (rl) rl.classList.add('animated');
      }
    });
  }, { threshold: 0.15 });

  document.querySelectorAll('.fade-up').forEach(el => observer.observe(el));

  // Rose line standalone elements
  const rlObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) e.target.classList.add('animated');
    });
  }, { threshold: 0.5 });
  document.querySelectorAll('.rose-line').forEach(el => rlObserver.observe(el));

  // Floating LINE button
  const floatLine = document.getElementById('floatLine');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 400) {
      floatLine.classList.add('show');
    } else {
      floatLine.classList.remove('show');
    }
  });
</script>
```

- [ ] **Step 4: ブラウザで確認**

Expected: スクロール400px超で右下にLINEアイコンが現れる。各セクションのfadeUpが正しく発火する。

- [ ] **Step 5: コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "feat: add floating LINE button and finalize scroll JS"
```

---

## Task 13: レスポンシブ最終調整

**Files:**
- Modify: `reusable/Massive White/index.html`

- [ ] **Step 1: Chrome DevTools でモバイル（375px）確認**

確認項目:
- [ ] Hero: テキストが画面に収まる・ボタンが切れない
- [ ] Empathy: カードが縦並びになる
- [ ] Compare: 2カラム → 1カラムになる
- [ ] Features: Split → 縦積みになる
- [ ] Steps: 横並び → 縦並び + 下矢印になる
- [ ] Gallery: 3列 → 2列になる
- [ ] Safety: 3カード → 縦積みになる
- [ ] 固定LINEボタン: 右下に正しく表示

- [ ] **Step 2: 480px（小型スマホ）でも確認**

- [ ] **Step 3: 崩れ箇所があれば修正**

共通パターン:
```css
@media (max-width: 480px) {
  /* 問題のあるセレクタ */ { /* 修正CSS */ }
}
```

- [ ] **Step 4: 最終コミット**

```bash
git add "reusable/Massive White/index.html"
git commit -m "fix: responsive adjustments for mobile"
```

---

## 検証チェックリスト

- [ ] デスクトップ（1440px）で全セクション目視確認
- [ ] モバイル（375px）で全セクション目視確認
- [ ] スクロールアニメーションが各セクションで発火
- [ ] Ken Burns / fadeUp / pulse / rose-line が動作
- [ ] 固定LINEボタンがスクロール後に出現
- [ ] `reusable/Dark Luxury/MassiveLP/index.html` と並べてブラウザタブで比較 → 「別サイトに見える」
- [ ] Consoleエラーなし
- [ ] 全画像パスが `img/` フォルダを参照（後から差し替え可能な状態）
