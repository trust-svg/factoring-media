# ASP審査用ランディングページ 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `threads-sho.trustlink-tk.com` の `/` にASP審査担当者向けランディングページを設置し、問い合わせフォームからTelegram通知を送る

**Architecture:** 既存FastAPIに `GET /` (LP) と `POST /contact` を追加。ダッシュボードは `/dashboard` に移動。フォームはJS fetch送信でページ遷移なし。

**Tech Stack:** FastAPI, Jinja2, httpx（既存）, Telegram Bot API

---

## ファイル構成

| 操作 | ファイル | 内容 |
|------|----------|------|
| 作成 | `templates/landing.html` | LPの全HTML |
| 修正 | `main.py` | `/` をLP用に差し替え、`/dashboard` 追加、`POST /contact` 追加 |

---

## Task 1: ダッシュボードを `/dashboard` に移動

**Files:**
- Modify: `main.py:141-161`

- [ ] **Step 1: `/` ルートを `/dashboard` にリネーム**

`main.py` の `@app.get("/", ...)` を以下に変更:

```python
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    history = get_post_history(limit=50)
    queue = get_queue()
    feedback = get_analyst_feedback()
    jobs = [
        {"id": j.id, "name": j.name, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "history": list(reversed(history)),
        "queue": queue,
        "feedback": feedback,
        "jobs": jobs,
        "kill_switch": is_kill_switch_active(),
        "stats": {
            "total_posts": len(get_post_history()),
            "queue_size": len(queue),
        },
    })
```

- [ ] **Step 2: 動作確認コマンドをメモ（VPSで後ほど実行）**

```bash
curl -s http://localhost:8001/dashboard | grep -o "<title>.*</title>"
# Expected: <title>Threads Auto Dashboard</title> （または類似）
```

- [ ] **Step 3: コミット**

```bash
git add main.py
git commit -m "refactor(threads-auto): dashboardを/dashboardに移動"
```

---

## Task 2: `/contact` エンドポイント追加

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 必要なimportを確認**

`main.py` の先頭に以下が揃っているか確認（すでにある）:
```python
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
```

- [ ] **Step 2: Pydanticスキーマ追加**

`main.py` の `app = FastAPI(...)` の直前に追加:

```python
from pydantic import BaseModel

class ContactForm(BaseModel):
    name: str
    company: str
    email: str
    message: str
```

- [ ] **Step 3: `/contact` POSTエンドポイント追加**

`/dashboard` ルートの直後に追加:

```python
@app.post("/contact")
async def contact(form: ContactForm):
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    text = (
        f"📬 ASPお問い合わせ\n\n"
        f"名前: {form.name}\n"
        f"会社: {form.company}\n"
        f"メール: {form.email}\n\n"
        f"内容:\n{form.message}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        )
    return {"status": "ok"}
```

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat(threads-auto): /contact POSTエンドポイント追加（Telegram通知）"
```

---

## Task 3: ランディングページHTML作成

**Files:**
- Create: `templates/landing.html`

- [ ] **Step 1: `templates/landing.html` を作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>しょう｜転職・キャリアアップ — Threadsメディア</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Hiragino Sans', sans-serif; background: #0f172a; color: #f8fafc; }
    a { color: inherit; text-decoration: none; }

    /* HERO */
    .hero { background: #0f172a; padding: 64px 24px 48px; text-align: center; border-bottom: 1px solid #1e293b; }
    .hero-badge { display: inline-block; background: #1d4ed8; color: #fff; font-size: 11px; padding: 4px 14px; border-radius: 20px; letter-spacing: 1px; margin-bottom: 20px; }
    .hero h1 { font-size: clamp(22px, 5vw, 32px); font-weight: 700; margin-bottom: 12px; }
    .hero p { color: #94a3b8; font-size: 15px; line-height: 1.7; margin-bottom: 28px; }
    .hero-btn { display: inline-block; background: #1d4ed8; color: #fff; padding: 12px 28px; border-radius: 8px; font-size: 14px; font-weight: 600; transition: background .2s; }
    .hero-btn:hover { background: #1e40af; }

    /* STATS */
    .stats { background: #1e293b; padding: 24px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .stat { text-align: center; padding: 12px 4px; }
    .stat-value { color: #60a5fa; font-size: 22px; font-weight: 700; }
    .stat-label { color: #64748b; font-size: 11px; margin-top: 4px; }

    /* SECTIONS */
    .section { padding: 40px 24px; border-bottom: 1px solid #1e293b; max-width: 720px; margin: 0 auto; width: 100%; }
    .section-label { color: #60a5fa; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 10px; }
    .section h2 { font-size: 18px; font-weight: 700; margin-bottom: 16px; }
    .section p { color: #94a3b8; font-size: 14px; line-height: 1.8; }

    /* POLICY */
    .policy-list { list-style: none; display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
    .policy-list li { background: #1e293b; padding: 10px 14px; border-radius: 6px; font-size: 13px; color: #94a3b8; }

    /* FORM */
    .form { display: flex; flex-direction: column; gap: 12px; margin-top: 8px; }
    .form input, .form textarea {
      background: #1e293b; border: 1px solid #334155; color: #f8fafc;
      padding: 12px 14px; border-radius: 6px; font-size: 14px; width: 100%;
      font-family: inherit;
    }
    .form input:focus, .form textarea:focus { outline: none; border-color: #1d4ed8; }
    .form textarea { resize: vertical; min-height: 100px; }
    .form button {
      background: #1d4ed8; color: #fff; border: none; padding: 14px;
      border-radius: 6px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background .2s;
    }
    .form button:hover { background: #1e40af; }
    .form-msg { display: none; padding: 12px; border-radius: 6px; font-size: 13px; text-align: center; }
    .form-msg.success { background: #064e3b; color: #6ee7b7; display: block; }
    .form-msg.error { background: #7f1d1d; color: #fca5a5; display: block; }

    /* FOOTER */
    footer { background: #020617; padding: 20px 24px; text-align: center; color: #475569; font-size: 12px; }

    @media (max-width: 480px) {
      .stats { grid-template-columns: repeat(2, 1fr); }
    }
  </style>
</head>
<body>

  <!-- HERO -->
  <section class="hero">
    <div class="hero-badge">THREADS メディア</div>
    <h1>しょう｜転職・キャリアアップ</h1>
    <p>手取り18万 → 年収600万を実現した転職ノウハウを毎日発信<br>25〜35歳の転職検討層に届くコンテンツで成果を作ります</p>
    <a href="https://www.threads.net/@sho_career_up" target="_blank" rel="noopener" class="hero-btn">
      Threadsをフォローする @sho_career_up
    </a>
  </section>

  <!-- STATS -->
  <div class="stats">
    <div class="stat"><div class="stat-value">200+</div><div class="stat-label">投稿数</div></div>
    <div class="stat"><div class="stat-value">毎日</div><div class="stat-label">更新頻度</div></div>
    <div class="stat"><div class="stat-value">転職</div><div class="stat-label">専門ジャンル</div></div>
    <div class="stat"><div class="stat-value">2026.3</div><div class="stat-label">運営開始</div></div>
  </div>

  <!-- ABOUT -->
  <div class="section">
    <div class="section-label">About</div>
    <h2>運営者プロフィール</h2>
    <p>
      20代で手取り18万円のブラック企業から脱出し、3回の転職を経て年収600万円を達成。
      転職エージェントの裏側・面接対策・年収交渉術など、リアルな体験談をもとに情報発信中。<br><br>
      <strong>ターゲット読者:</strong> 25〜35歳の転職検討層・年収アップを目指すビジネスパーソン
    </p>
  </div>

  <!-- AD POLICY -->
  <div class="section">
    <div class="section-label">Ad Policy</div>
    <h2>広告・ASP掲載について</h2>
    <ul class="policy-list">
      <li>✅ 転職エージェント・プログラミングスクール・キャリアコーチング 案件対応可</li>
      <li>✅ 投稿内の自然な文脈でPR表記を明示して掲載</li>
      <li>✅ 読者に価値ある案件のみ取り扱い</li>
      <li>❌ 金融・ギャンブル・成人向けコンテンツは掲載不可</li>
    </ul>
  </div>

  <!-- CONTACT -->
  <div class="section">
    <div class="section-label">Contact</div>
    <h2>お問い合わせ</h2>
    <form class="form" id="contactForm">
      <input type="text" name="name" placeholder="お名前" required>
      <input type="text" name="company" placeholder="会社名・ASP名" required>
      <input type="email" name="email" placeholder="メールアドレス" required>
      <textarea name="message" placeholder="お問い合わせ内容" required></textarea>
      <button type="submit">送信する</button>
    </form>
    <div class="form-msg" id="formMsg"></div>
  </div>

  <footer>© 2026 しょう｜転職・キャリアアップ — Threads <a href="https://www.threads.net/@sho_career_up" target="_blank">@sho_career_up</a></footer>

  <script>
    document.getElementById('contactForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.target;
      const msg = document.getElementById('formMsg');
      msg.className = 'form-msg';
      msg.textContent = '';
      const data = {
        name: form.name.value,
        company: form.company.value,
        email: form.email.value,
        message: form.message.value,
      };
      try {
        const res = await fetch('/contact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        if (res.ok) {
          msg.className = 'form-msg success';
          msg.textContent = '送信しました。2〜3営業日以内にご連絡します。';
          form.reset();
        } else {
          throw new Error();
        }
      } catch {
        msg.className = 'form-msg error';
        msg.textContent = '送信に失敗しました。時間をおいて再度お試しください。';
      }
    });
  </script>

</body>
</html>
```

- [ ] **Step 2: `GET /` ルートをmain.pyに追加**

`@app.get("/dashboard", ...)` の直前に追加:

```python
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})
```

- [ ] **Step 3: コミット**

```bash
git add templates/landing.html main.py
git commit -m "feat(threads-auto): ASP審査用LPを/に追加"
```

---

## Task 4: VPSにデプロイして動作確認

- [ ] **Step 1: VPSでgit pull + コンテナ再起動**

```bash
ssh root@46.250.252.99 "cd /opt/threads-auto && git pull && docker compose restart threads-auto"
```

- [ ] **Step 2: LPの表示確認**

```bash
curl -s http://46.250.252.99:8001/ | grep -o "<title>.*</title>"
# Expected: <title>しょう｜転職・キャリアアップ — Threadsメディア</title>
```

- [ ] **Step 3: /contact エンドポイント確認**

```bash
curl -s -X POST http://46.250.252.99:8001/contact \
  -H "Content-Type: application/json" \
  -d '{"name":"テスト","company":"テストASP","email":"test@example.com","message":"動作確認"}' 
# Expected: {"status":"ok"}
# Telegramに通知が届くことを確認
```

- [ ] **Step 4: Caddyの確認（Basic Authが `/` にかかっている場合は解除）**

VPSで確認:
```bash
cat /etc/caddy/Caddyfile | grep -A 20 "threads-sho"
```

もし `basicauth` ディレクティブが `/` 全体にかかっていたら、`/dashboard` のみに限定する:
```
threads-sho.trustlink-tk.com {
    basicauth /dashboard* {
        admin JDJhJDE0J...  # 既存ハッシュをそのまま使う
    }
    reverse_proxy localhost:8001
}
```

変更後:
```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

- [ ] **Step 5: 本番URLで最終確認**

ブラウザで `https://threads-sho.trustlink-tk.com` を開いてLPが表示されることを確認。

- [ ] **Step 6: pushして完了**

```bash
git push origin master
```
