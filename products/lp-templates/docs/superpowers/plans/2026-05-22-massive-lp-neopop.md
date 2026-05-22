# Massive Neo Pop LP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `products/lp-templates/Massive Neo Pop/index.html` として、50代以上男性向けシークレットマッチング「Massive」のLP（単一HTMLファイル）を実装する。

**Architecture:** 単一 `index.html` にCSS・JSをすべてインライン記述。外部依存はCDN（AOS / Swiper / Font Awesome / Google Fonts）のみ。セクションは上から順に構築し、共通デザイントークン→構造→アニメーションの順で積み上げる。

**Tech Stack:** HTML5, Vanilla CSS (custom properties), Vanilla JS, AOS.js 2.3.4, Swiper.js 11, Font Awesome 6.5, Google Fonts (Noto Sans JP + Inter)

---

## ファイル構成

```
products/lp-templates/Massive Neo Pop/
├── index.html          ← すべてのCSS・JSをインライン
└── img/
    ├── w01.jpg         ← 女性: スマホでLINE打つ30代
    ├── w02.jpg         ← 女性: 年上好きを示す40代
    ├── w03.jpg         ← 女性: シミュレーター結果で笑顔30代
    ├── w04.jpg         ← 女性: 体験談A（30代）
    ├── w05.jpg         ← 女性: 体験談B（40代）
    ├── w06.jpg         ← 女性: 体験談C（40代）
    ├── w07.jpg         ← 女性: 体験談D（50代）
    ├── w08.jpg         ← 女性: LINEで返信中
    ├── s01.jpg         ← シーン: 夜の街を歩く男女後ろ姿
    ├── s02.jpg         ← シーン: 居酒屋で話す男女
    ├── s03.jpg         ← シーン: ホテル廊下・扉の前
    ├── s04.jpg         ← シーン: カフェでスマホを見せ合う
    ├── s05.jpg         ← シーン: 夜景バー・お酒
    ├── m01.jpg         ← 男性: 普通の50代、少し寂しそう
    └── m02.jpg         ← 男性: スマホ操作する50代
```

---

## Task 1: ディレクトリ作成 + HTMLシェル

**Files:**
- Create: `products/lp-templates/Massive Neo Pop/index.html`
- Create: `products/lp-templates/Massive Neo Pop/img/.gitkeep`

- [ ] **Step 1: ディレクトリ作成**

```bash
mkdir -p "products/lp-templates/Massive Neo Pop/img"
touch "products/lp-templates/Massive Neo Pop/img/.gitkeep"
```

- [ ] **Step 2: index.html のシェルを作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>まだいける。絶頂期は、今。| Massive</title>
  <meta name="description" content="50代以上の男性のための、完全匿名シークレットマッチング。累計18万人が登録。">
  <meta name="robots" content="noindex, nofollow">

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
  <!-- Icons -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <!-- AOS -->
  <link rel="stylesheet" href="https://unpkg.com/aos@2.3.4/dist/aos.css">
  <!-- Swiper -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css">

  <style>
    /* ── DESIGN TOKENS ── */
    :root {
      --clr-bg:        #FFFFFF;
      --clr-text:      #111111;
      --clr-text-sub:  #555555;
      --clr-accent-a:  #FF6B6B;
      --clr-accent-b:  #FFD166;
      --clr-line:      #06C755;
      --clr-line-dark: #04A546;
      --clr-gray-bg:   #F8F8F8;
      --clr-border:    #EEEEEE;

      --grad-accent: linear-gradient(135deg, var(--clr-accent-a), var(--clr-accent-b));
      --grad-text:   linear-gradient(135deg, #FF6B6B 0%, #FF9A5C 50%, #FFD166 100%);

      --font-jp:   'Noto Sans JP', sans-serif;
      --font-en:   'Inter', sans-serif;

      --section-pad: clamp(60px, 10vw, 120px);
      --container:   1100px;
      --radius-sm:   8px;
      --radius-md:   16px;
      --radius-lg:   24px;
      --radius-full: 9999px;
    }

    /* ── RESET ── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; overflow-x: hidden; }
    body { font-family: var(--font-jp); background: var(--clr-bg); color: var(--clr-text); line-height: 1.8; -webkit-font-smoothing: antialiased; }
    img { max-width: 100%; height: auto; display: block; }
    a { color: inherit; text-decoration: none; }

    /* ── LAYOUT ── */
    .container { max-width: var(--container); margin: 0 auto; padding: 0 clamp(16px, 5vw, 48px); }
    .section { padding: var(--section-pad) 0; }
    .section--gray { background: var(--clr-gray-bg); }

    /* ── LINE BUTTON (共通) ── */
    .btn-line {
      display: inline-flex; align-items: center; gap: 10px;
      background: var(--clr-line); color: #fff;
      padding: 14px 28px; border-radius: var(--radius-md);
      font-size: 1rem; font-weight: 700; letter-spacing: 0.05em;
      box-shadow: 0 6px 20px rgba(6,199,85,0.4);
      transition: background 0.2s, transform 0.15s, box-shadow 0.2s;
      border: none; cursor: pointer;
    }
    .btn-line:hover { background: var(--clr-line-dark); transform: translateY(-2px); box-shadow: 0 10px 28px rgba(6,199,85,0.5); }
    .btn-line:active { transform: translateY(0); }
    .btn-line .icon { font-size: 1.2rem; }

    /* ── GRADIENT TEXT ── */
    .grad-text {
      background: var(--grad-text);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    /* ── SECTION LABEL ── */
    .sec-label {
      font-family: var(--font-en);
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.3em;
      text-transform: uppercase; color: var(--clr-accent-a);
      margin-bottom: 12px;
    }
    .sec-title {
      font-size: clamp(1.6rem, 4vw, 2.4rem);
      font-weight: 900; line-height: 1.25;
      margin-bottom: 16px;
    }
    .sec-sub {
      font-size: 1rem; color: var(--clr-text-sub);
      max-width: 560px;
    }

    /* placeholder — sections will be added per task */
  </style>
</head>
<body>

  <!-- sections injected in subsequent tasks -->

  <!-- Scripts -->
  <script src="https://unpkg.com/aos@2.3.4/dist/aos.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>
  <script>
    AOS.init({ duration: 700, once: true, offset: 60 });
  </script>
</body>
</html>
```

- [ ] **Step 3: ブラウザで開いて白紙が表示されることを確認**

```bash
open "products/lp-templates/Massive Neo Pop/index.html"
```

- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/"
git commit -m "feat(massive-neopop): LPシェル作成 + デザイントークン定義"
```

---

## Task 2: 浮遊ブロブ + フローティングLINEボタン（共通UI）

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: `<style>` 内に浮遊ブロブとフローティングボタンのCSSを追加**

`/* placeholder — sections will be added per task */` の直前に挿入:

```css
/* ── FLOATING BLOBS ── */
@keyframes blobFloat {
  0%, 100% { transform: translateY(0) scale(1) rotate(0deg); }
  33%       { transform: translateY(-18px) scale(1.05) rotate(4deg); }
  66%       { transform: translateY(-8px) scale(0.97) rotate(-3deg); }
}
.blob {
  position: absolute; border-radius: 50%;
  pointer-events: none; z-index: 0;
  animation: blobFloat var(--dur, 7s) ease-in-out infinite;
  animation-delay: var(--delay, 0s);
}
.blob--a {
  width: clamp(160px, 25vw, 260px); height: clamp(160px, 25vw, 260px);
  background: linear-gradient(135deg, rgba(255,107,107,0.22), rgba(255,209,102,0.18));
  --dur: 8s;
}
.blob--b {
  width: clamp(100px, 15vw, 170px); height: clamp(100px, 15vw, 170px);
  background: linear-gradient(135deg, rgba(168,237,234,0.25), rgba(254,214,227,0.2));
  --dur: 6s; --delay: 1.5s;
}
.blob--c {
  width: clamp(60px, 8vw, 100px); height: clamp(60px, 8vw, 100px);
  background: rgba(255,209,102,0.2);
  --dur: 5s; --delay: 3s;
}

/* ── FLOATING LINE BUTTON ── */
.float-line-btn {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  z-index: 1000;
  display: inline-flex; align-items: center; gap: 10px;
  background: var(--clr-line); color: #fff;
  padding: 14px 32px; border-radius: var(--radius-full);
  font-size: 1rem; font-weight: 700;
  box-shadow: 0 8px 24px rgba(6,199,85,0.5);
  white-space: nowrap;
  transition: background 0.2s, transform 0.15s;
  border: none; cursor: pointer;
  animation: floatBtnPulse 3s ease-in-out infinite;
}
@keyframes floatBtnPulse {
  0%, 100% { box-shadow: 0 8px 24px rgba(6,199,85,0.5); }
  50%       { box-shadow: 0 12px 36px rgba(6,199,85,0.7); }
}
.float-line-btn:hover { background: var(--clr-line-dark); transform: translateX(-50%) translateY(-2px); }
```

- [ ] **Step 2: `</body>` 直前にフローティングボタンHTMLを追加**

```html
<!-- ── FLOATING LINE BTN ── -->
<button class="float-line-btn" onclick="document.querySelector('#cta').scrollIntoView({behavior:'smooth'})">
  <i class="fa-brands fa-line icon"></i>LINEで無料登録
</button>
```

- [ ] **Step 3: ブラウザ確認 — 画面下にLINEボタンが浮いていること**

- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): 浮遊ブロブCSS + フローティングLINEボタン追加"
```

---

## Task 3: ① Hero セクション

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: `<style>` に Hero CSS を追加**

```css
/* ── HERO ── */
.hero {
  position: relative; overflow: hidden;
  min-height: 100svh;
  display: flex; align-items: center;
  background: var(--clr-bg);
  padding: clamp(80px, 12vw, 140px) 0 clamp(60px, 8vw, 100px);
}
.hero .blob--a { top: -60px; right: -60px; }
.hero .blob--b { bottom: 40px; left: -30px; }
.hero .blob--c { top: 40%; right: 15%; }
.hero__inner {
  position: relative; z-index: 1;
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 40px; align-items: center;
}
@media (max-width: 640px) {
  .hero__inner { grid-template-columns: 1fr; }
  .hero__img { order: -1; }
}
.hero__eyebrow {
  font-family: var(--font-en);
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.3em;
  text-transform: uppercase; color: var(--clr-accent-a);
  margin-bottom: 16px;
}
.hero__title {
  font-size: clamp(2rem, 6vw, 3.4rem);
  font-weight: 900; line-height: 1.1;
  margin-bottom: 16px;
}
.hero__sub {
  font-size: clamp(0.95rem, 2vw, 1.1rem);
  color: var(--clr-text-sub); margin-bottom: 12px; line-height: 1.8;
}
.hero__proof {
  font-size: 0.85rem; color: var(--clr-text-sub); margin-bottom: 28px;
}
.hero__proof strong { color: var(--clr-text); font-weight: 900; font-size: 1.1rem; }
.hero__active {
  display: inline-flex; align-items: center; gap: 6px;
  background: #FFF3F3; border: 1px solid rgba(255,107,107,0.3);
  border-radius: var(--radius-full); padding: 5px 14px;
  font-size: 0.78rem; font-weight: 700; color: #CC3333;
  margin-bottom: 24px;
}
.hero__active .dot {
  width: 8px; height: 8px; border-radius: 50%; background: #FF4444;
  animation: pulse-dot 1.5s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(1.4); }
}
.hero__img {
  position: relative; z-index: 1;
  border-radius: var(--radius-lg); overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,0.12);
  aspect-ratio: 3/4; max-height: 540px;
}
.hero__img img { width: 100%; height: 100%; object-fit: cover; }
```

- [ ] **Step 2: `<!-- sections injected in subsequent tasks -->` を以下に置き換え（追記）**

```html
<!-- ── HERO ── -->
<section class="hero" id="top">
  <div class="blob blob--a"></div>
  <div class="blob blob--b"></div>
  <div class="blob blob--c"></div>
  <div class="container">
    <div class="hero__inner">
      <div class="hero__content">
        <div class="hero__eyebrow">50代以上限定 シークレットマッチング</div>
        <h1 class="hero__title">
          まだいける。<br>
          <span class="grad-text">絶頂期は、今。</span>
        </h1>
        <p class="hero__sub">年齢が、最強の武器になる。<br>50代からが本当の勝負。</p>
        <div class="hero__active">
          <span class="dot"></span>今 <strong>324人</strong> の女性がオンライン
        </div>
        <p class="hero__proof">累計 <strong>18万人</strong> 以上が登録 · 毎日 <strong>320件</strong> のマッチング</p>
        <button class="btn-line" onclick="document.querySelector('#cta').scrollIntoView({behavior:'smooth'})">
          <i class="fa-brands fa-line icon"></i>LINEで無料登録（3分）
        </button>
      </div>
      <div class="hero__img" data-aos="fade-left">
        <img src="img/w01.jpg" alt="マッチングに成功した女性" loading="eager">
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: ブラウザで確認 — タイトルにグラデーション、ブロブが動く、モバイルで1カラムになること**

- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): Heroセクション実装"
```

---

## Task 4: ② 実績バナー（カウントアップ）

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── STATS BANNER ── */
.stats { background: var(--clr-text); padding: clamp(36px, 6vw, 60px) 0; }
.stats__grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 24px; text-align: center;
}
@media (max-width: 480px) { .stats__grid { grid-template-columns: 1fr; gap: 32px; } }
.stats__num {
  font-family: var(--font-en); font-size: clamp(2rem, 5vw, 3rem);
  font-weight: 900; line-height: 1;
  background: var(--grad-text);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 6px;
}
.stats__label { font-size: 0.85rem; color: rgba(255,255,255,0.7); }
```

- [ ] **Step 2: Heroセクションの直後にHTMLを追加**

```html
<!-- ── STATS BANNER ── -->
<div class="stats" id="stats">
  <div class="container">
    <div class="stats__grid">
      <div data-aos="fade-up">
        <div class="stats__num" data-count="180000" data-suffix="人+">0</div>
        <div class="stats__label">累計登録者数</div>
      </div>
      <div data-aos="fade-up" data-aos-delay="100">
        <div class="stats__num" data-count="320" data-suffix="件/日">0</div>
        <div class="stats__label">毎日のマッチング数</div>
      </div>
      <div data-aos="fade-up" data-aos-delay="200">
        <div class="stats__num" data-count="92" data-suffix="%">0</div>
        <div class="stats__label">利用者満足度</div>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: `AOS.init(...)` の下にカウントアップJSを追加**

```javascript
// ── COUNT UP ──
(function() {
  const els = document.querySelectorAll('[data-count]');
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      obs.unobserve(entry.target);
      const el = entry.target;
      const target = parseInt(el.dataset.count);
      const suffix = el.dataset.suffix || '';
      const duration = 1800;
      const step = 16;
      const increment = target / (duration / step);
      let current = 0;
      const timer = setInterval(() => {
        current = Math.min(current + increment, target);
        const display = target >= 10000
          ? Math.floor(current / 10000) + '万'
          : Math.floor(current).toLocaleString();
        el.textContent = display + suffix;
        if (current >= target) clearInterval(timer);
      }, step);
    });
  }, { threshold: 0.4 });
  els.forEach(el => obs.observe(el));
})();
```

- [ ] **Step 4: ブラウザ確認 — スクロールして数字がカウントアップすること、黒背景に映えること**

- [ ] **Step 5: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): 実績バナー + カウントアップアニメ"
```

---

## Task 5: ③ 共感セクション

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── EMPATHY ── */
.empathy__grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px; margin-top: 40px;
}
.empathy__card {
  background: #fff; border: 1.5px solid var(--clr-border);
  border-radius: var(--radius-md); padding: 20px 24px;
  display: flex; align-items: flex-start; gap: 14px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}
.empathy__icon {
  font-size: 1.4rem; min-width: 32px; margin-top: 2px;
}
.empathy__text { font-size: 0.95rem; color: var(--clr-text); line-height: 1.7; }
.empathy__img {
  margin-top: 48px; border-radius: var(--radius-lg); overflow: hidden;
  max-height: 320px;
}
.empathy__img img { width: 100%; object-fit: cover; }
```

- [ ] **Step 2: statsバナーの直後にHTMLを追加**

```html
<!-- ── EMPATHY ── -->
<section class="section section--gray" id="empathy">
  <div class="container">
    <div class="sec-label">Are you one of them?</div>
    <h2 class="sec-title">こんな50代、<br><span class="grad-text">いませんか？</span></h2>
    <p class="sec-sub">多くの男性が同じ悩みを抱えています。あなただけじゃない。</p>
    <div class="empathy__grid">
      <div class="empathy__card" data-aos="fade-up">
        <span class="empathy__icon">😔</span>
        <p class="empathy__text">「出会いの場がなくなった」と感じている</p>
      </div>
      <div class="empathy__card" data-aos="fade-up" data-aos-delay="80">
        <span class="empathy__icon">📱</span>
        <p class="empathy__text">マッチングアプリは若い子ばかりで使いづらい</p>
      </div>
      <div class="empathy__card" data-aos="fade-up" data-aos-delay="160">
        <span class="empathy__icon">🪞</span>
        <p class="empathy__text">年齢のせいで女性に相手にされないと思っている</p>
      </div>
      <div class="empathy__card" data-aos="fade-up" data-aos-delay="240">
        <span class="empathy__icon">🔒</span>
        <p class="empathy__text">身バレが怖くてマッチングアプリに踏み出せない</p>
      </div>
      <div class="empathy__card" data-aos="fade-up" data-aos-delay="320">
        <span class="empathy__icon">💬</span>
        <p class="empathy__text">女性との会話の仕方がわからない・自信がない</p>
      </div>
      <div class="empathy__card" data-aos="fade-up" data-aos-delay="400">
        <span class="empathy__icon">❤️‍🔥</span>
        <p class="empathy__text">まだ恋愛したいのに、チャンスが回ってこない</p>
      </div>
    </div>
    <div class="empathy__img" data-aos="fade-up">
      <img src="img/m01.jpg" alt="出会いを探す50代男性" loading="lazy">
    </div>
  </div>
</section>
```

- [ ] **Step 3: 確認 — カードが順番にフェードイン、グレー背景で映えること**

- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): 共感セクション実装"
```

---

## Task 6: ④ なぜ50代はモテる・ヤレるのか（データセクション）

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── WHY 50s ── */
.why50__grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px; margin-top: 40px;
}
.why50__card {
  background: #fff; border-radius: var(--radius-md);
  padding: 28px 24px; text-align: center;
  box-shadow: 0 4px 20px rgba(0,0,0,0.07);
  border-top: 4px solid transparent;
  border-image: var(--grad-accent) 1;
  border-top-left-radius: var(--radius-md);
  border-top-right-radius: var(--radius-md);
}
.why50__pct {
  font-family: var(--font-en); font-size: 2.8rem; font-weight: 900;
  line-height: 1; margin-bottom: 8px;
}
.why50__desc { font-size: 0.9rem; color: var(--clr-text-sub); line-height: 1.7; }
.why50__rank {
  margin-top: 48px;
  background: var(--clr-text); border-radius: var(--radius-lg);
  padding: 36px 32px; color: #fff;
}
.why50__rank-title {
  font-size: 1rem; font-weight: 700; color: rgba(255,255,255,0.7);
  margin-bottom: 20px; text-align: center;
}
.why50__rank-list { display: flex; flex-direction: column; gap: 12px; }
.why50__rank-item {
  display: flex; align-items: center; gap: 14px;
}
.why50__rank-no {
  font-family: var(--font-en); font-size: 1.4rem; font-weight: 900;
  min-width: 32px;
}
.why50__rank-no.r1 { background: var(--grad-text); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.why50__rank-no.r2 { color: #ccc; }
.why50__rank-no.r3 { color: #aaa; }
.why50__rank-label { font-size: 1rem; font-weight: 700; }
.why50__rank-sub { font-size: 0.8rem; color: rgba(255,255,255,0.6); }
.why50__divider {
  margin: 48px 0;
  height: 200px; border-radius: var(--radius-lg); overflow: hidden;
}
.why50__divider img { width: 100%; height: 100%; object-fit: cover; }
```

- [ ] **Step 2: 共感セクションの直後にHTMLを追加**

```html
<!-- ── WHY 50s ── -->
<section class="section" id="why50">
  <div class="container">
    <div class="sec-label">Data & Research</div>
    <h2 class="sec-title">なぜ50代は<br><span class="grad-text">モテる・ヤレるのか</span></h2>
    <p class="sec-sub">データが証明している。年齢は言い訳にならない、最強の武器だ。</p>

    <div class="why50__grid">
      <div class="why50__card" data-aos="fade-up">
        <div class="why50__pct grad-text">68<span style="font-size:1.4rem">%</span></div>
        <div class="why50__desc">の女性が<strong>年上・同世代の男性</strong>との出会いを希望</div>
      </div>
      <div class="why50__card" data-aos="fade-up" data-aos-delay="100">
        <div class="why50__pct grad-text">4人<span style="font-size:1.4rem">に</span>1人</div>
        <div class="why50__desc">の30〜40代女性が<strong>年上限定</strong>でマッチングを探している</div>
      </div>
      <div class="why50__card" data-aos="fade-up" data-aos-delay="200">
        <div class="why50__pct grad-text">2.3<span style="font-size:1.4rem">倍</span></div>
        <div class="why50__desc">50代男性は20〜30代と比べてマッチング後の<strong>継続率が2.3倍</strong>高い</div>
      </div>
    </div>

    <div class="why50__rank" data-aos="fade-up">
      <div class="why50__rank-title">女性が「年上の男性」に求めるもの TOP 3</div>
      <div class="why50__rank-list">
        <div class="why50__rank-item">
          <div class="why50__rank-no r1">01</div>
          <div>
            <div class="why50__rank-label">包容力・余裕</div>
            <div class="why50__rank-sub">「話を聞いてくれる」「焦らせない」が圧倒的1位</div>
          </div>
        </div>
        <div class="why50__rank-item">
          <div class="why50__rank-no r2">02</div>
          <div>
            <div class="why50__rank-label">経済的な安定感</div>
            <div class="why50__rank-sub">「割り勘しない」「きちんとした食事に連れて行ってくれる」</div>
          </div>
        </div>
        <div class="why50__rank-item">
          <div class="why50__rank-no r3">03</div>
          <div>
            <div class="why50__rank-label">人生経験・話の深さ</div>
            <div class="why50__rank-sub">「話が面白い」「人生を知っている」が若い男性との差</div>
          </div>
        </div>
      </div>
    </div>

    <div class="why50__divider" data-aos="fade-up">
      <img src="img/s01.jpg" alt="夜の街を歩く男女" loading="lazy">
    </div>
  </div>
</section>
```

- [ ] **Step 3: 確認 — データカードが入場アニメ、ランキングカードが黒背景で映えること**

- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): 50代モテ理由セクション（データ/ランキング）"
```

---

## Task 7: ⑤ マッチング数シミュレーター（オリジナル要素）

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── SIMULATOR ── */
.sim { background: var(--clr-gray-bg); }
.sim__box {
  background: #fff; border-radius: var(--radius-lg);
  padding: clamp(28px, 5vw, 48px); max-width: 680px; margin: 40px auto 0;
  box-shadow: 0 8px 32px rgba(0,0,0,0.08);
}
.sim__step { margin-bottom: 28px; }
.sim__step-label {
  font-size: 0.78rem; font-weight: 700; letter-spacing: 0.15em;
  color: var(--clr-accent-a); margin-bottom: 10px;
}
.sim__step-q { font-size: 1rem; font-weight: 700; margin-bottom: 14px; }
/* Age slider */
.sim__slider-wrap { display: flex; align-items: center; gap: 14px; }
.sim__slider {
  -webkit-appearance: none; flex: 1; height: 6px;
  border-radius: 3px; outline: none; cursor: pointer;
  background: linear-gradient(90deg, var(--clr-accent-a) var(--pct, 50%), #e0e0e0 var(--pct, 50%));
}
.sim__slider::-webkit-slider-thumb {
  -webkit-appearance: none; width: 22px; height: 22px;
  border-radius: 50%; background: var(--clr-accent-a);
  box-shadow: 0 2px 8px rgba(255,107,107,0.4); cursor: pointer;
}
.sim__age-val {
  font-family: var(--font-en); font-size: 1.4rem; font-weight: 900;
  min-width: 48px; text-align: center;
}
/* Chips */
.sim__chips { display: flex; flex-wrap: wrap; gap: 10px; }
.sim__chip {
  padding: 8px 18px; border-radius: var(--radius-full);
  border: 2px solid var(--clr-border); font-size: 0.9rem; cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
  background: #fff; color: var(--clr-text);
}
.sim__chip.selected {
  border-color: var(--clr-accent-a); background: #FFF3F3; color: var(--clr-accent-a); font-weight: 700;
}
/* Result */
.sim__result {
  display: none; text-align: center; padding-top: 20px;
  border-top: 1px solid var(--clr-border); margin-top: 20px;
}
.sim__result.show { display: block; }
.sim__result-num {
  font-family: var(--font-en); font-size: clamp(3rem, 8vw, 4.5rem);
  font-weight: 900; line-height: 1;
}
.sim__result-label { font-size: 1rem; color: var(--clr-text-sub); margin: 8px 0 20px; }
@keyframes heartFly {
  0%   { transform: translateY(0) scale(1); opacity: 1; }
  100% { transform: translateY(-120px) scale(0.3); opacity: 0; }
}
.heart-particle {
  position: fixed; pointer-events: none; font-size: 1.6rem; z-index: 9999;
  animation: heartFly 1.2s ease-out forwards;
}
```

- [ ] **Step 2: why50セクションの直後にHTMLを追加**

```html
<!-- ── SIMULATOR ── -->
<section class="section sim" id="simulator">
  <div class="container">
    <div class="sec-label">Matching Simulator</div>
    <h2 class="sec-title"><span class="grad-text">あなたのマッチング数</span>を予測</h2>
    <p class="sec-sub">3ステップで入力するだけ。あなたへのマッチング予測数が出ます。</p>

    <div class="sim__box" data-aos="fade-up">
      <!-- Step 1: Age -->
      <div class="sim__step">
        <div class="sim__step-label">STEP 01</div>
        <div class="sim__step-q">あなたの年齢は？</div>
        <div class="sim__slider-wrap">
          <input type="range" class="sim__slider" id="simAge" min="50" max="75" value="55"
            oninput="simUpdateAge(this)">
          <div class="sim__age-val" id="simAgeVal">55歳</div>
        </div>
      </div>

      <!-- Step 2: Job -->
      <div class="sim__step">
        <div class="sim__step-label">STEP 02</div>
        <div class="sim__step-q">職業は？</div>
        <div class="sim__chips" id="simJobChips">
          <div class="sim__chip" data-val="2" onclick="simSelectChip(this,'job')">会社員</div>
          <div class="sim__chip" data-val="8" onclick="simSelectChip(this,'job')">経営者・役員</div>
          <div class="sim__chip" data-val="5" onclick="simSelectChip(this,'job')">自営業</div>
          <div class="sim__chip" data-val="1" onclick="simSelectChip(this,'job')">その他</div>
        </div>
      </div>

      <!-- Step 3: Hobbies -->
      <div class="sim__step">
        <div class="sim__step-label">STEP 03（複数選択OK）</div>
        <div class="sim__step-q">趣味・好きなことは？</div>
        <div class="sim__chips" id="simHobbyChips">
          <div class="sim__chip" data-val="2" onclick="simToggleHobby(this)">グルメ・食事</div>
          <div class="sim__chip" data-val="2" onclick="simToggleHobby(this)">旅行</div>
          <div class="sim__chip" data-val="2" onclick="simToggleHobby(this)">スポーツ・健康</div>
          <div class="sim__chip" data-val="2" onclick="simToggleHobby(this)">映画・ドラマ</div>
          <div class="sim__chip" data-val="2" onclick="simToggleHobby(this)">ドライブ</div>
          <div class="sim__chip" data-val="2" onclick="simToggleHobby(this)">音楽</div>
        </div>
      </div>

      <button class="btn-line" style="width:100%;justify-content:center;" onclick="simCalc()">
        <i class="fa-solid fa-calculator"></i>マッチング数を予測する
      </button>

      <div class="sim__result" id="simResult">
        <div class="sim__result-num grad-text" id="simResultNum">0</div>
        <div class="sim__result-label">1週間で推定マッチング数（人）</div>
        <p style="font-size:0.85rem;color:var(--clr-text-sub);margin-bottom:20px;">
          あなたのプロフィールなら、これだけの女性と繋がれる可能性があります。
        </p>
        <button class="btn-line" style="margin:0 auto;" onclick="document.querySelector('#cta').scrollIntoView({behavior:'smooth'})">
          <i class="fa-brands fa-line icon"></i>今すぐLINEで試してみる
        </button>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 3: `AOS.init(...)` の下にシミュレーターJSを追加**

```javascript
// ── SIMULATOR ──
var simState = { age: 55, job: 0, hobbies: 0 };

function simUpdateAge(el) {
  simState.age = parseInt(el.value);
  document.getElementById('simAgeVal').textContent = simState.age + '歳';
  var pct = (simState.age - 50) / (75 - 50) * 100;
  el.style.setProperty('--pct', pct + '%');
}

function simSelectChip(el, group) {
  document.querySelectorAll('#simJobChips .sim__chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  simState.job = parseInt(el.dataset.val);
}

function simToggleHobby(el) {
  el.classList.toggle('selected');
  simState.hobbies = document.querySelectorAll('#simHobbyChips .sim__chip.selected').length;
}

function simCalc() {
  var base = 15;
  var ageBonus = simState.age >= 60 ? 5 : 3;
  var jobBonus = simState.job || 1;
  var hobbyBonus = simState.hobbies * 2;
  var raw = base + ageBonus + jobBonus + hobbyBonus;
  var result = Math.min(Math.max(raw, 12), 47);

  var resultEl = document.getElementById('simResult');
  var numEl = document.getElementById('simResultNum');
  resultEl.classList.add('show');
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // count up
  var cur = 0;
  var timer = setInterval(function() {
    cur = Math.min(cur + 1, result);
    numEl.textContent = cur;
    if (cur >= result) clearInterval(timer);
  }, 40);

  // heart particles
  for (var i = 0; i < 8; i++) {
    (function(i) {
      setTimeout(function() {
        var h = document.createElement('div');
        h.className = 'heart-particle';
        h.textContent = '❤️';
        h.style.left = (30 + Math.random() * 40) + 'vw';
        h.style.top = (40 + Math.random() * 20) + 'vh';
        document.body.appendChild(h);
        setTimeout(function() { h.remove(); }, 1300);
      }, i * 120);
    })(i);
  }
}
```

- [ ] **Step 4: 確認 — スライダーで年齢変更→職業チップ選択→趣味複数選択→ボタン押下で数字カウントアップ＋ハートが飛ぶこと**

- [ ] **Step 5: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): マッチング数シミュレーター（インタラクティブ）"
```

---

## Task 8: ⑥⑦ 特徴×3点 + 3ステップ

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── FEATURES ── */
.features__grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 24px; margin-top: 40px;
}
.features__card {
  border-radius: var(--radius-md); padding: 28px 24px;
  background: #fff; box-shadow: 0 4px 20px rgba(0,0,0,0.07);
  text-align: center;
}
.features__icon {
  font-size: 2.4rem; margin-bottom: 14px;
  display: block;
}
.features__name { font-size: 1.1rem; font-weight: 900; margin-bottom: 8px; }
.features__desc { font-size: 0.9rem; color: var(--clr-text-sub); line-height: 1.8; }

/* ── STEPS ── */
.steps { background: var(--clr-text); }
.steps__list {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0; margin-top: 40px; position: relative;
}
.steps__list::before {
  content: ''; position: absolute; top: 36px; left: 10%; right: 10%; height: 2px;
  background: linear-gradient(90deg, var(--clr-accent-a), var(--clr-accent-b));
  opacity: 0.4;
}
@media (max-width: 640px) { .steps__list::before { display: none; } }
.steps__item { text-align: center; padding: 0 20px; }
.steps__num {
  width: 72px; height: 72px; border-radius: 50%; margin: 0 auto 16px;
  background: var(--grad-accent);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-en); font-size: 1.6rem; font-weight: 900; color: #fff;
  position: relative; z-index: 1;
}
.steps__title { font-size: 1rem; font-weight: 900; color: #fff; margin-bottom: 6px; }
.steps__sub { font-size: 0.85rem; color: rgba(255,255,255,0.6); line-height: 1.7; }
.steps__divider {
  margin-top: 48px; height: 200px;
  border-radius: var(--radius-lg); overflow: hidden;
}
.steps__divider img { width: 100%; height: 100%; object-fit: cover; }
```

- [ ] **Step 2: シミュレーターの直後にHTMLを追加**

```html
<!-- ── FEATURES ── -->
<section class="section" id="features">
  <div class="container">
    <div class="sec-label">Why Massive</div>
    <h2 class="sec-title">Massiveが<span class="grad-text">選ばれる</span>理由</h2>
    <div class="features__grid">
      <div class="features__card" data-aos="fade-up">
        <span class="features__icon">🔒</span>
        <div class="features__name">完全匿名・プロフ非公開</div>
        <div class="features__desc">顔写真・本名・職場は一切不要。身バレの心配ゼロで出会いを楽しめる。</div>
      </div>
      <div class="features__card" data-aos="fade-up" data-aos-delay="100">
        <span class="features__icon">👑</span>
        <div class="features__name">50代以上限定の空間</div>
        <div class="features__desc">同世代しかいないから、変な競争なし。年齢を武器にできる唯一の場所。</div>
      </div>
      <div class="features__card" data-aos="fade-up" data-aos-delay="200">
        <span class="features__icon">💕</span>
        <div class="features__name">30〜45歳の女性と繋がれる</div>
        <div class="features__desc">年上好きの女性が集まるプラットフォーム。あなたの経験と包容力が武器になる。</div>
      </div>
    </div>
  </div>
</section>

<!-- ── STEPS ── -->
<section class="section steps" id="steps">
  <div class="container">
    <div class="sec-label" style="color:rgba(255,255,255,0.5)">How to Start</div>
    <h2 class="sec-title" style="color:#fff">始め方は<span class="grad-text">カンタン</span>3ステップ</h2>
    <div class="steps__list">
      <div class="steps__item" data-aos="fade-up">
        <div class="steps__num">1</div>
        <div class="steps__title">LINEで無料登録</div>
        <div class="steps__sub">LINEを開いてボタンをタップするだけ。3分で完了。</div>
      </div>
      <div class="steps__item" data-aos="fade-up" data-aos-delay="150">
        <div class="steps__num">2</div>
        <div class="steps__title">プロフィール設定</div>
        <div class="steps__sub">顔写真不要。趣味・雰囲気だけでOK。</div>
      </div>
      <div class="steps__item" data-aos="fade-up" data-aos-delay="300">
        <div class="steps__num">3</div>
        <div class="steps__title">マッチング開始</div>
        <div class="steps__sub">すぐに女性からのアプローチが届き始める。</div>
      </div>
    </div>
    <div class="steps__divider" data-aos="fade-up">
      <img src="img/s02.jpg" alt="居酒屋でのデート" loading="lazy">
    </div>
  </div>
</section>
```

- [ ] **Step 3: 確認 — 特徴カードのフェードイン、ステップの横並び（モバイルで縦）、黒背景ステップが映えること**

- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): 特徴×3 + 3ステップセクション"
```

---

## Task 9: ⑧ 体験談（Swiper）

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── TESTIMONIALS ── */
.testi { background: var(--clr-gray-bg); }
.testi__swiper { margin-top: 40px; padding-bottom: 48px !important; }
.testi__card {
  background: #fff; border-radius: var(--radius-lg);
  overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}
.testi__img { height: 220px; overflow: hidden; }
.testi__img img { width: 100%; height: 100%; object-fit: cover; }
.testi__body { padding: 24px; }
.testi__age {
  font-size: 0.78rem; font-weight: 700; letter-spacing: 0.1em;
  color: var(--clr-accent-a); margin-bottom: 8px;
}
.testi__quote { font-size: 0.95rem; line-height: 1.8; margin-bottom: 14px; }
.testi__name { font-size: 0.8rem; color: var(--clr-text-sub); }
.testi__divider {
  margin-top: 48px; height: 200px;
  border-radius: var(--radius-lg); overflow: hidden;
}
.testi__divider img { width: 100%; height: 100%; object-fit: cover; }
```

- [ ] **Step 2: stepsセクションの直後にHTMLを追加**

```html
<!-- ── TESTIMONIALS ── -->
<section class="section testi" id="testimonials">
  <div class="container">
    <div class="sec-label">Success Stories</div>
    <h2 class="sec-title">実際に<span class="grad-text">成功した</span>50代たち</h2>
    <p class="sec-sub">普通の男性が、年齢を武器に変えた体験談。</p>

    <div class="swiper testi__swiper" data-aos="fade-up">
      <div class="swiper-wrapper">
        <div class="swiper-slide">
          <div class="testi__card">
            <div class="testi__img"><img src="img/w04.jpg" alt="体験談A" loading="lazy"></div>
            <div class="testi__body">
              <div class="testi__age">登録者 / 54歳 · 会社員</div>
              <p class="testi__quote">「正直、自分にはもう無理だと思ってた。でも登録して2週間で33歳の子とマッチングして、今は毎週会ってる。年齢なんて関係なかった。」</p>
              <div class="testi__name">T.K さん（54歳）</div>
            </div>
          </div>
        </div>
        <div class="swiper-slide">
          <div class="testi__card">
            <div class="testi__img"><img src="img/w05.jpg" alt="体験談B" loading="lazy"></div>
            <div class="testi__body">
              <div class="testi__age">登録者 / 58歳 · 自営業</div>
              <p class="testi__quote">「離婚後、もう恋愛はいいかなと思ってた。ものは試しと登録したら、40代の女性から先にメッセージが来て驚いた。包容力があるって言われた。」</p>
              <div class="testi__name">M.O さん（58歳）</div>
            </div>
          </div>
        </div>
        <div class="swiper-slide">
          <div class="testi__card">
            <div class="testi__img"><img src="img/w06.jpg" alt="体験談C" loading="lazy"></div>
            <div class="testi__body">
              <div class="testi__age">登録者 / 62歳 · 会社員</div>
              <p class="testi__quote">「62歳でマッチングアプリに登録するのは恥ずかしかった。でも匿名だから誰にもバレないし、1ヶ月で4人と会った。もっと早くやればよかった。」</p>
              <div class="testi__name">H.N さん（62歳）</div>
            </div>
          </div>
        </div>
        <div class="swiper-slide">
          <div class="testi__card">
            <div class="testi__img"><img src="img/w07.jpg" alt="体験談D" loading="lazy"></div>
            <div class="testi__body">
              <div class="testi__age">登録者 / 56歳 · 経営者</div>
              <p class="testi__quote">「仕事一筋で恋愛経験が少なく不安だったけど、女性の方が優しくリードしてくれた。経営者というより人間として見てくれた気がして嬉しかった。」</p>
              <div class="testi__name">Y.S さん（56歳）</div>
            </div>
          </div>
        </div>
      </div>
      <div class="swiper-pagination"></div>
    </div>

    <div class="testi__divider" data-aos="fade-up">
      <img src="img/s03.jpg" alt="ホテルへ向かうカップル" loading="lazy">
    </div>
  </div>
</section>
```

- [ ] **Step 3: `AOS.init(...)` の下にSwiper初期化コードを追加**

```javascript
// ── SWIPER ──
new Swiper('.testi__swiper', {
  slidesPerView: 1.1,
  spaceBetween: 16,
  centeredSlides: false,
  pagination: { el: '.swiper-pagination', clickable: true },
  breakpoints: {
    640: { slidesPerView: 2, spaceBetween: 20 },
    900: { slidesPerView: 3, spaceBetween: 24 }
  }
});
```

- [ ] **Step 4: 確認 — カードがスワイプ可能、ドットページネーション表示、モバイルで1.1枚見えること**

- [ ] **Step 5: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): 体験談スライダー（Swiper）"
```

---

## Task 10: ⑨⑩ FAQ + 最終CTA

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: CSS追加**

```css
/* ── FAQ ── */
.faq__list { margin-top: 40px; max-width: 720px; margin-left: auto; margin-right: auto; }
.faq__item {
  border-bottom: 1px solid var(--clr-border);
  overflow: hidden;
}
.faq__q {
  width: 100%; text-align: left; padding: 18px 0;
  font-size: 0.95rem; font-weight: 700; background: none; border: none;
  cursor: pointer; display: flex; justify-content: space-between; align-items: center;
  gap: 12px; color: var(--clr-text);
}
.faq__q .icon { font-size: 1rem; color: var(--clr-accent-a); flex-shrink: 0; transition: transform 0.3s; }
.faq__q[aria-expanded="true"] .icon { transform: rotate(45deg); }
.faq__a {
  font-size: 0.9rem; color: var(--clr-text-sub); line-height: 1.8;
  max-height: 0; overflow: hidden; transition: max-height 0.35s ease, padding 0.35s;
  padding: 0 0;
}
.faq__a.open { max-height: 200px; padding: 0 0 16px; }

/* ── FINAL CTA ── */
.final-cta {
  background: var(--clr-text); padding: var(--section-pad) 0;
  text-align: center; position: relative; overflow: hidden;
}
.final-cta .blob--a { top: -40px; left: -40px; opacity: 0.15; }
.final-cta .blob--b { bottom: -20px; right: -20px; opacity: 0.15; }
.final-cta__proof {
  font-family: var(--font-en); font-size: 0.8rem; letter-spacing: 0.2em;
  color: rgba(255,255,255,0.5); text-transform: uppercase; margin-bottom: 16px;
}
.final-cta__title {
  font-size: clamp(1.8rem, 5vw, 3rem); font-weight: 900;
  color: #fff; line-height: 1.2; margin-bottom: 16px;
}
.final-cta__sub { font-size: 1rem; color: rgba(255,255,255,0.7); margin-bottom: 32px; }
.final-cta__disclaimer {
  font-size: 0.75rem; color: rgba(255,255,255,0.35); margin-top: 20px;
}
.final-cta__img {
  margin: 40px auto 0; max-width: 500px;
  border-radius: var(--radius-lg); overflow: hidden; opacity: 0.85;
}
.final-cta__img img { width: 100%; height: 260px; object-fit: cover; }
```

- [ ] **Step 2: 体験談の直後にHTMLを追加**

```html
<!-- ── FAQ ── -->
<section class="section" id="faq">
  <div class="container">
    <div class="sec-label">FAQ</div>
    <h2 class="sec-title">よくある<span class="grad-text">質問</span></h2>
    <div class="faq__list">
      <div class="faq__item">
        <button class="faq__q" aria-expanded="false" onclick="toggleFaq(this)">
          <span>顔写真なしでも登録できますか？</span>
          <i class="fa-solid fa-plus icon"></i>
        </button>
        <div class="faq__a">もちろんです。Massiveでは顔写真は任意です。趣味・雰囲気・メッセージの内容で十分にマッチングできます。むしろ顔写真なしで登録している方も多く、プライバシーが守られます。</div>
      </div>
      <div class="faq__item">
        <button class="faq__q" aria-expanded="false" onclick="toggleFaq(this)">
          <span>職場や家族にバレませんか？</span>
          <i class="fa-solid fa-plus icon"></i>
        </button>
        <div class="faq__a">Massiveは完全匿名のため、本名・職場・住所などの個人情報は一切不要です。LINEのみで登録でき、知り合いが表示される機能もありません。</div>
      </div>
      <div class="faq__item">
        <button class="faq__q" aria-expanded="false" onclick="toggleFaq(this)">
          <span>本当に30〜40代の女性と出会えますか？</span>
          <i class="fa-solid fa-plus icon"></i>
        </button>
        <div class="faq__a">はい。Massiveには年上の男性を希望する30〜45歳の女性会員が多く在籍しています。包容力や安定感を求める女性が積極的に年上男性へアプローチします。</div>
      </div>
      <div class="faq__item">
        <button class="faq__q" aria-expanded="false" onclick="toggleFaq(this)">
          <span>無料で使えますか？</span>
          <i class="fa-solid fa-plus icon"></i>
        </button>
        <div class="faq__a">LINE登録・プロフィール設定・マッチングまでは無料です。詳しい料金プランは登録後にご確認いただけます。</div>
      </div>
      <div class="faq__item">
        <button class="faq__q" aria-expanded="false" onclick="toggleFaq(this)">
          <span>スマートフォンが苦手でも使えますか？</span>
          <i class="fa-solid fa-plus icon"></i>
        </button>
        <div class="faq__a">LINEが使えれば操作できます。LINEのトーク画面でやり取りするシンプルな仕組みなので、特別なアプリのインストールも不要です。</div>
      </div>
    </div>
  </div>
</section>

<!-- ── FINAL CTA ── -->
<section class="final-cta" id="cta">
  <div class="blob blob--a"></div>
  <div class="blob blob--b"></div>
  <div class="container" style="position:relative;z-index:1;">
    <div class="final-cta__proof">すでに 18万人以上 が登録済み</div>
    <h2 class="final-cta__title">
      あなたの絶頂期は、<br>
      <span class="grad-text">まだ始まっていない。</span>
    </h2>
    <p class="final-cta__sub">今日登録すれば、今夜にはマッチングが届くかもしれない。</p>
    <button class="btn-line" style="font-size:1.1rem;padding:16px 36px;margin:0 auto;">
      <i class="fa-brands fa-line icon"></i>LINEで無料登録する
    </button>
    <p class="final-cta__disclaimer">※ 登録・マッチングまで無料。個人情報の入力不要。</p>
    <div class="final-cta__img" data-aos="fade-up">
      <img src="img/w08.jpg" alt="LINEで返信する女性" loading="lazy">
    </div>
  </div>
</section>
```

- [ ] **Step 3: FAQのJSを追加**

```javascript
// ── FAQ ──
function toggleFaq(btn) {
  var expanded = btn.getAttribute('aria-expanded') === 'true';
  document.querySelectorAll('.faq__q').forEach(function(b) {
    b.setAttribute('aria-expanded', 'false');
    b.nextElementSibling.classList.remove('open');
  });
  if (!expanded) {
    btn.setAttribute('aria-expanded', 'true');
    btn.nextElementSibling.classList.add('open');
  }
}
```

- [ ] **Step 4: 確認 — FAQアコーディオンが開閉、最終CTAにブロブが動く、モバイルで崩れないこと**

- [ ] **Step 5: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/index.html"
git commit -m "feat(massive-neopop): FAQ + 最終CTAセクション実装（LP構造完成）"
```

---

## Task 11: 画像生成（ChatGPT Image Pro）

**Files:**
- Create: `products/lp-templates/Massive Neo Pop/img/w01.jpg` 〜 `m02.jpg`

> **NOTE:** 画像生成には `/chatgpt-image-pro` スキルを使用すること。各プロンプトは英語で入力する。縦長 (3:4) と横長 (16:9) を使い分ける。生成後は `img/` に保存してindex.htmlの `<img src="img/...">` が正しく参照されることを確認。

**女性ポートレート（3:4, portrait, bright background, NOT luxury）**

| ファイル | プロンプト |
|---------|---------|
| w01.jpg | Japanese woman in her 30s, cute and friendly face, natural bangs, slightly larger chest, wearing casual clothes, holding smartphone and smiling at screen, background: cozy cafe interior, natural lighting, warm tone, not glamorous or hostess-like, approachable and warm expression |
| w02.jpg | Japanese woman in her early 40s, beautiful and kind-looking, hair without bangs, slightly larger chest, casual outfit, warm smile, background: park or street in daytime, approachable not high-class |
| w03.jpg | Japanese woman in her 30s, cute face with natural bangs, laughing happily while looking at smartphone, slightly larger chest, casual wear, background: home or bright room, very approachable |
| w04.jpg | Japanese woman in her 30s, friendly and cute, natural bangs, slightly larger chest, warm smile, background: casual outdoor or cafe, not luxury |
| w05.jpg | Japanese woman in her 40s, attractive and kind face, no bangs, slightly larger chest, casual elegant style, warm smile, background: simple indoor or park |
| w06.jpg | Japanese woman in her 40s, beautiful, hair pulled back with some strands framing face, slightly larger chest, casual smart outfit, gentle expression, background: everyday setting |
| w07.jpg | Japanese woman in her late 40s to early 50s, attractive and mature, kind face, slightly larger chest, casual but neat outfit, warm smile, background: simple room or outdoor |
| w08.jpg | Japanese woman in her 30s, cute, natural bangs, slightly larger chest, typing on smartphone with a smile, background: bedroom or living room, soft lighting |

**デート・シーンシーン（16:9, NOT overly luxury）**

| ファイル | プロンプト |
|---------|---------|
| s01.jpg | Rear view of a middle-aged Japanese man and a woman walking together at night in an urban area with hotels and restaurants, city lights background, cinematic, intimate atmosphere, not too high-class |
| s02.jpg | Japanese middle-aged man and woman in their 30s-40s at a casual izakaya or restaurant, laughing together, drinks on table, warm intimate lighting, natural and happy |
| s03.jpg | Hotel corridor at night, a couple standing near a door, moody lighting, suggestive but tasteful, not overly luxurious hotel, intimate |
| s04.jpg | Japanese man and woman sitting at a cafe table, looking at a smartphone screen together, smiling, casual daytime setting, warm and relaxed atmosphere |
| s05.jpg | Japanese couple at a casual bar with city night view, glasses of beer or wine, intimate conversation, warm lighting, not overly high-end |

**男性（3:4, ordinary 50s Japanese man）**

| ファイル | プロンプト |
|---------|---------|
| m01.jpg | Ordinary Japanese man in his 50s, average looking, slightly lonely expression, casual clothes, not particularly attractive, everyday setting, relatable |
| m02.jpg | Ordinary Japanese man in his 50s, average appearance, looking at smartphone screen, casual clothes, simple background, natural everyday look |

- [ ] **Step 1: `/chatgpt-image-pro` スキルを起動して上記プロンプトで順次生成**
- [ ] **Step 2: 生成画像を `products/lp-templates/Massive Neo Pop/img/` に保存（ファイル名通り）**
- [ ] **Step 3: ブラウザで全セクションを確認 — 画像が正しく表示されること**
- [ ] **Step 4: Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/img/"
git commit -m "feat(massive-neopop): 生成画像を追加（女性8枚・シーン5枚・男性2枚）"
```

---

## Task 12: レスポンシブ最終確認 + 仕上げ

**Files:**
- Modify: `products/lp-templates/Massive Neo Pop/index.html`

- [ ] **Step 1: Chrome DevToolsでモバイル（375px）を確認**
  - Hero: 1カラム、画像が上
  - Stats: 1カラム縦並び
  - Simulator: フルワイドスライダー・チップが折り返し
  - Steps: 縦並び
  - 体験談: slidesPerView 1.1でスワイプ

- [ ] **Step 2: フローティングLINEボタンがスクロール中も正しく表示されること確認**

- [ ] **Step 3: `<head>` に OGP/meta を追加（存在しない場合）**

```html
<meta property="og:title" content="まだいける。絶頂期は、今。| Massive">
<meta property="og:description" content="50代以上の男性のための完全匿名シークレットマッチング。累計18万人登録。">
<meta property="og:type" content="website">
<meta property="og:image" content="img/w01.jpg">
<meta name="twitter:card" content="summary_large_image">
```

- [ ] **Step 4: 最終Commit**

```bash
git add "products/lp-templates/Massive Neo Pop/"
git commit -m "feat(massive-neopop): レスポンシブ調整 + OGP meta 追加（LP完成）"
```

---

## セルフレビュー結果

- **スペックカバレッジ**: 全10セクション対応済み ✓ / シミュレーター計算式実装済み ✓ / 追加3案（固定ボタン・オンラインバッジ・ハート）実装済み ✓
- **プレースホルダー**: なし ✓
- **型一貫性**: `simState` / `simCalc` / `toggleFaq` / Swiper設定すべて一貫 ✓
- **画像パス**: 全セクションで `img/xxx.jpg` を参照、Task 11で生成後に一致 ✓
