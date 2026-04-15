# Invest-Simulator UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `products/invest-simulator/frontend/index.html` from the current 4-card layout to a B+C merged design — light background with 3-column color-accented KPI cards, a 2-column chart+bar-chart layout, spec-colored trade badges, and a compact AI log list.

**Architecture:** Single-file implementation (all CSS + HTML + JS in `frontend/index.html`). No backend changes. No new files. The JS data sources (`/api/portfolio`, `/api/positions`, `/api/trades`, `/api/cycles`) are unchanged — only rendering logic changes.

**Tech Stack:** Vanilla HTML/CSS/JS, Chart.js 4.4.0 (existing), Inter + JetBrains Mono fonts (existing)

---

## File Structure

| File | Change |
|------|--------|
| `products/invest-simulator/frontend/index.html` | Full CSS rewrite + HTML restructure + JS render updates |

All tasks modify only this one file. Each task maps to a distinct section of the file.

---

### Task 1: CSS — Root Variables and Base Reset

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`:root` block, lines ~11–35)

Replace the `:root` CSS variables block. Keep existing variable names that are reused downstream; add new ones for the 3-card accent colors.

- [ ] **Step 1: Replace `:root` block**

Find the block starting with `:root {` and ending at the closing `}` (~line 35). Replace entirely with:

```css
:root {
    --bg:          #f8fafc;
    --surface:     #ffffff;
    --card:        #ffffff;
    --border:      #e2e8f0;
    --border-med:  #cbd5e1;
    --accent:      #3b82f6;
    --accent-dim:  rgba(59,130,246,0.08);
    --text:        #0f172a;
    --sub:         #1e293b;
    --muted:       #64748b;
    --gain:        #10b981;
    --gain-bg:     rgba(16,185,129,0.10);
    --loss:        #ef4444;
    --loss-bg:     rgba(239,68,68,0.10);
    --buy:         #1d4ed8;
    --buy-bg:      #dbeafe;
    --sell:        #c2410c;
    --sell-bg:     #ffedd5;
    --hold:        #64748b;
    --hold-bg:     #f1f5f9;
    --amber:       #f59e0b;
    --amber-bg:    rgba(245,158,11,0.10);
    --mono:        'JetBrains Mono', monospace;
    --body:        'Inter', sans-serif;
    --shadow-sm:   0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04);
    --shadow-md:   0 4px 12px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04);
}
```

- [ ] **Step 2: Verify no broken references**

Search the file for `var(--bg)`, `var(--accent)`, `var(--gain)`, `var(--loss)` — these are the most-used variables. Confirm they still exist in the new `:root`.

- [ ] **Step 3: Commit**

```bash
cd /Users/Mac_air/Claude-Workspace
git add products/invest-simulator/frontend/index.html
git commit -m "style: update CSS variables for B+C redesign palette"
```

---

### Task 2: CSS — KPI Card Styles (3-column with accent top border)

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`.metrics-row` and `.metric-card` blocks)

Replace the 4-column grid with 3-column, and add top-border accent support.

- [ ] **Step 1: Replace `.metrics-row` grid**

Find:
```css
.metrics-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px; margin-bottom: 20px;
}
```
Replace with:
```css
.metrics-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px; margin-bottom: 20px;
}
```

- [ ] **Step 2: Update `.metric-card` for accent top border**

Find the `.metric-card` rule. Replace with:
```css
.metric-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    border-top: 4px solid var(--border);
    padding: 22px 24px;
    box-shadow: var(--shadow-sm);
    transition: box-shadow .2s, border-color .2s;
}
.metric-card:hover { box-shadow: var(--shadow-md); }
```

- [ ] **Step 3: Add pill badge style for KPI sub-values**

After the `.metric-sub` rule, add:
```css
.metric-pill {
    display: inline-flex; align-items: center;
    padding: 3px 10px; border-radius: 20px;
    font-family: var(--mono); font-size: 11px; font-weight: 600;
    margin-top: 8px;
}
.metric-pill.pos { background: var(--gain-bg); color: var(--gain); }
.metric-pill.neg { background: var(--loss-bg); color: var(--loss); }
.metric-pill.neu { background: var(--amber-bg); color: var(--amber); }
```

- [ ] **Step 4: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "style: 3-column KPI cards with accent top border and pill badges"
```

---

### Task 3: CSS — 2-Column Mid Layout and Bar Chart Styles

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`.mid-row`, `.bar-*` styles)

Change the chart+positions grid ratio and add horizontal bar styles for the new positions panel.

- [ ] **Step 1: Update `.mid-row` grid**

Find:
```css
.mid-row {
    display: grid;
    grid-template-columns: 1fr 380px;
    gap: 16px; margin-bottom: 20px;
}
```
Replace with:
```css
.mid-row {
    display: grid;
    grid-template-columns: 1.3fr 1fr;
    gap: 16px; margin-bottom: 20px;
}
```

- [ ] **Step 2: Add bar-list styles for positions panel**

After the `.pos-val` rule, add:
```css
/* ─── POSITIONS BAR CHART ─────────────────────────────── */
.bar-list {
    padding: 16px; display: flex; flex-direction: column; gap: 10px;
}
.bar-item {
    display: flex; align-items: center; gap: 10px;
}
.bar-ticker {
    font-family: var(--mono); font-size: 12px; font-weight: 600;
    color: var(--text); min-width: 70px; flex-shrink: 0;
}
.bar-track {
    flex: 1; height: 8px; background: var(--border);
    border-radius: 4px; overflow: hidden;
}
.bar-fill {
    height: 100%; border-radius: 4px;
    transition: width 0.4s ease;
}
.bar-fill.pos { background: var(--accent); }
.bar-fill.neg { background: #fca5a5; }
.bar-pct {
    font-family: var(--mono); font-size: 12px; font-weight: 600;
    min-width: 56px; text-align: right; flex-shrink: 0;
}
```

- [ ] **Step 3: Add chart container background**

Find `.chart-wrap { padding: 20px; }` and replace with:
```css
.chart-wrap { padding: 20px; background: #f8fafc; border-radius: 8px; margin: 12px; }
```

- [ ] **Step 4: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "style: 1.3fr/1fr mid grid + horizontal bar styles for positions"
```

---

### Task 4: CSS — Trade Table and AI Log Styles

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`.act-badge` and `.ai-log-*` styles)

Update trade badge colors to spec values and replace collapsible cycle-log styles with compact AI log styles.

- [ ] **Step 1: Update `.act-badge` colors**

Find the `.act-badge` rules:
```css
.act-badge.BUY  { background: var(--buy-bg); color: var(--buy); }
.act-badge.SELL { background: var(--sell-bg); color: var(--sell); }
.act-badge.HOLD { background: #F1F5F9; color: var(--hold); }
```
Replace with:
```css
.act-badge.BUY  { background: #dbeafe; color: #1d4ed8; }
.act-badge.SELL { background: #ffedd5; color: #c2410c; }
.act-badge.HOLD { background: #f1f5f9; color: #64748b; }
```

Also update the `td` border-bottom to a lighter shade:
Find `td { padding: 11px 18px; font-size: 13px; border-bottom: 1px solid var(--border); vertical-align: middle; color: var(--sub); }` and replace with:
```css
td { padding: 11px 18px; font-size: 13px; border-bottom: 1px solid #f8fafc; vertical-align: middle; color: var(--sub); }
```

- [ ] **Step 2: Replace cycle-log CSS with AI log compact styles**

Delete the entire block from `/* ─── CYCLE LOG ───` down to and including `.cycle-input {` closing brace and everything below it through `.cycle-decision-reason { ... }` (approximately lines 261–306 in the current file).

Replace with:
```css
/* ─── AI LOG ──────────────────────────────────────────── */
.ai-log-list {
    padding: 12px; display: flex; flex-direction: column; gap: 8px;
}
.ai-log-entry {
    background: #f8fafc; border-radius: 8px;
    border-left: 3px solid var(--border-med);
    padding: 10px 14px;
}
.ai-log-entry.BUY  { border-left-color: #3b82f6; }
.ai-log-entry.SELL { border-left-color: #f97316; }
.ai-log-entry.HOLD { border-left-color: #cbd5e1; }
.ai-log-head {
    display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}
.ai-log-badge {
    font-family: var(--mono); font-size: 10px; font-weight: 700;
    letter-spacing: 0.5px; padding: 2px 8px; border-radius: 4px;
}
.ai-log-badge.BUY  { background: #dbeafe; color: #1d4ed8; }
.ai-log-badge.SELL { background: #ffedd5; color: #c2410c; }
.ai-log-badge.HOLD { background: #f1f5f9; color: #64748b; }
.ai-log-ticker {
    font-family: var(--mono); font-size: 12px; font-weight: 600; color: var(--text);
}
.ai-log-ts { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-left: auto; }
.ai-log-body {
    font-size: 12px; color: var(--sub); line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
```

- [ ] **Step 3: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "style: spec-colored trade badges and compact AI log styles"
```

---

### Task 5: HTML — KPI Cards (4→3 cards)

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`.metrics-row` HTML block)

Replace the 4-card HTML with 3 cards, each with `border-top` accent inline style and pill badge placeholders.

- [ ] **Step 1: Replace the metrics HTML block**

Find the entire `<div class="metrics-row">` block (currently lines ~409–432) and replace with:

```html
<!-- Metrics -->
<div class="metrics-row">
    <div class="metric-card" style="border-top-color:#3b82f6">
        <div class="metric-label">総資産</div>
        <div class="metric-value" id="m-total">$—</div>
        <div class="metric-sub" id="m-total-jpy">≈ ¥—</div>
        <div id="m-total-pill" class="metric-pill neu">初期比 —%</div>
    </div>
    <div class="metric-card" id="m-pnl-card" style="border-top-color:#10b981">
        <div class="metric-label">含み損益</div>
        <div class="metric-value" id="m-pnl">$—</div>
        <div class="metric-sub" id="m-pnl-jpy">≈ ¥—</div>
        <div id="m-pnl-pill" class="metric-pill pos">全体 —%</div>
    </div>
    <div class="metric-card" style="border-top-color:#f59e0b">
        <div class="metric-label">現金残高</div>
        <div class="metric-value" id="m-cash-val">$—</div>
        <div class="metric-sub" id="m-cash-sub">JP $— / US $—</div>
        <div id="m-cash-pill" class="metric-pill neu">総資産比 —%</div>
    </div>
</div>
```

Note: The USD/JPY metric card is removed. Market open status remains in header badges and status bar.

- [ ] **Step 2: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "feat: replace 4-card KPI with 3-card accented layout (総資産/損益/現金)"
```

---

### Task 6: HTML — Positions Panel (list → bar chart)

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (positions panel inside `.mid-row`)

Replace the `pos-list` div with a `bar-list` div.

- [ ] **Step 1: Replace positions panel inner HTML**

Find:
```html
        <div class="panel">
            <div class="panel-head"></div>
                <span class="panel-title">保有銘柄</span>
                <span class="panel-meta" id="pos-ct">0 銘柄</span>
            </div>
            <div class="pos-list" id="pos-list">
                <div class="empty">ポジションなし</div>
            </div>
        </div>
```

The exact HTML in the file is (lines ~448–456):
```html
        <div class="panel">
            <div class="panel-head">
                <span class="panel-title">保有銘柄</span>
                <span class="panel-meta" id="pos-ct">0 銘柄</span>
            </div>
            <div class="pos-list" id="pos-list">
                <div class="empty">ポジションなし</div>
            </div>
        </div>
```

Replace the `<div class="pos-list"...>` line only with:
```html
            <div class="bar-list" id="pos-list">
                <div class="empty">ポジションなし</div>
            </div>
```

- [ ] **Step 2: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "feat: switch positions panel to bar-list container"
```

---

### Task 7: HTML — AI Log Panel (collapsible → compact list)

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (AI log panel)

Replace the collapsible `cycle-log-scroll` div with a simple `ai-log-list` div.

- [ ] **Step 1: Replace AI log panel HTML**

Find the entire `<!-- Cycle Analysis Log -->` section (lines ~485–494):
```html
    <!-- Cycle Analysis Log -->
    <div class="panel cycle-log-panel">
        <div class="panel-head">
            <span class="panel-title">AI 分析ログ</span>
            <span class="panel-meta" id="cycle-ct">0 件</span>
        </div>
        <div class="cycle-log-scroll" id="cycle-log-body">
            <div class="empty">サイクルログなし（初回取引サイクル後に表示されます）</div>
        </div>
    </div>
```

Replace with:
```html
    <!-- AI Analysis Log -->
    <div class="panel" style="margin-top:20px">
        <div class="panel-head">
            <span class="panel-title">AI 分析ログ</span>
            <span class="panel-meta" id="cycle-ct">0 件</span>
        </div>
        <div class="ai-log-list" id="cycle-log-body">
            <div class="empty">ログなし</div>
        </div>
    </div>
```

- [ ] **Step 2: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "feat: replace collapsible AI log with compact list panel"
```

---

### Task 8: JS — Update `fetchPortfolio()` for 3-card KPI

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`fetchPortfolio` function, lines ~569–601)

Update element IDs to match new HTML and add pill badge logic.

- [ ] **Step 1: Replace `fetchPortfolio` function body**

Find the `async function fetchPortfolio() {` block and replace the entire function with:

```javascript
async function fetchPortfolio() {
    const d = await fetch(`${API}/api/portfolio`).then(r => r.json());
    _usdjpy = d.usdjpy || 150;

    // 総資産カード
    const te = document.getElementById('m-total');
    te.textContent = f$(d.total_value); flash(te);
    document.getElementById('m-total-jpy').textContent = `≈ ${fY(d.total_value * _usdjpy)}`;
    const initPct = ((d.total_value - 10000) / 10000 * 100);
    const pill = document.getElementById('m-total-pill');
    pill.textContent = `初期比 ${fP(initPct)}`;
    pill.className = `metric-pill ${initPct >= 0 ? 'pos' : 'neg'}`;

    // 含み損益カード
    const pe = document.getElementById('m-pnl');
    pe.textContent = fS(d.pnl);
    pe.className = 'metric-value ' + (d.pnl >= 0 ? 'pos' : 'neg');
    const pnlJpy = document.getElementById('m-pnl-jpy');
    pnlJpy.textContent = `≈ ${fYS(d.pnl * _usdjpy)}`;
    pnlJpy.style.color = d.pnl >= 0 ? 'var(--gain)' : 'var(--loss)';
    const pnlPill = document.getElementById('m-pnl-pill');
    pnlPill.textContent = `全体 ${fP(d.pnl_pct)}`;
    pnlPill.className = `metric-pill ${d.pnl >= 0 ? 'pos' : 'neg'}`;
    document.getElementById('m-pnl-card').style.borderTopColor = d.pnl >= 0 ? '#10b981' : '#ef4444';

    // 現金残高カード
    const totalCash = (d.cash_jp || 0) + (d.cash_us || 0);
    document.getElementById('m-cash-val').textContent = f$(totalCash);
    document.getElementById('m-cash-sub').textContent = `JP ${f$(d.cash_jp)} / US ${f$(d.cash_us)}`;
    const cashPct = d.total_value > 0 ? (totalCash / d.total_value * 100) : 0;
    const cashPill = document.getElementById('m-cash-pill');
    cashPill.textContent = `総資産比 ${cashPct.toFixed(1)}%`;
    cashPill.className = 'metric-pill neu';

    // Market badges
    const upd = (id, open, label) => {
        const el = document.getElementById(id);
        el.className = `badge ${open ? 'open' : 'closed'}`;
        el.innerHTML = `<div class="badge-dot"></div>${label} ${open ? '開場' : '閉場'}`;
    };
    upd('bdg-jp', d.jp_market_open, '🇯🇵 JP');
    upd('bdg-us', d.us_market_open, '🇺🇸 US');
}
```

- [ ] **Step 2: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "feat: update fetchPortfolio for 3-card KPI with pill badges"
```

---

### Task 9: JS — Update `fetchPositions()` for horizontal bar chart

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`fetchPositions` function)

Replace the card-list rendering with bar-chart rendering. Bar width = `|pnl_pct| / maxAbsPnl * 100%`.

- [ ] **Step 1: Replace `fetchPositions` function**

Find the `async function fetchPositions() {` block and replace entirely with:

```javascript
async function fetchPositions() {
    const data = await fetch(`${API}/api/positions`).then(r => r.json());
    document.getElementById('pos-ct').textContent = `${data.length} 銘柄`;
    const list = document.getElementById('pos-list');
    if (!data.length) { list.innerHTML = '<div class="empty">保有銘柄なし</div>'; return; }

    const maxAbs = Math.max(...data.map(p => Math.abs(p.pnl_pct)), 0.01);
    list.innerHTML = data.map(p => {
        const barWidth = (Math.abs(p.pnl_pct) / maxAbs * 100).toFixed(1);
        const cls = p.pnl_pct >= 0 ? 'pos' : 'neg';
        const pctStr = (p.pnl_pct >= 0 ? '+' : '') + p.pnl_pct.toFixed(2) + '%';
        return `
        <div class="bar-item">
            <span class="bar-ticker">${p.ticker}</span>
            <div class="bar-track">
                <div class="bar-fill ${cls}" style="width:${barWidth}%"></div>
            </div>
            <span class="bar-pct ${cls}">${pctStr}</span>
        </div>`;
    }).join('');
}
```

- [ ] **Step 2: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "feat: positions panel renders as horizontal P&L bar chart"
```

---

### Task 10: JS — Update `fetchCycleLogs()` for compact AI log

**Files:**
- Modify: `products/invest-simulator/frontend/index.html` (`fetchCycleLogs` function)

Replace collapsible card rendering with compact 2-line-clamp entries.

- [ ] **Step 1: Find and replace `fetchCycleLogs` function**

Search the file for `function fetchCycleLogs` (or `async function fetchCycleLogs`). Replace the entire function with:

```javascript
async function fetchCycleLogs() {
    const data = await fetch(`${API}/api/cycles`).then(r => r.json());
    document.getElementById('cycle-ct').textContent = `${data.length} 件`;
    const body = document.getElementById('cycle-log-body');
    if (!data.length) { body.innerHTML = '<div class="empty">ログなし</div>'; return; }

    body.innerHTML = data.map(c => {
        const action = c.action || 'HOLD';
        const ticker = c.ticker || c.symbol || '—';
        const ts = c.executed_at || c.timestamp || '';
        const reason = c.reason || c.analysis || '';
        return `
        <div class="ai-log-entry ${action}">
            <div class="ai-log-head">
                <span class="ai-log-badge ${action}">${action}</span>
                <span class="ai-log-ticker">${ticker}</span>
                <span class="ai-log-ts">${ts ? fD(ts) : ''}</span>
            </div>
            <div class="ai-log-body">${reason}</div>
        </div>`;
    }).join('');
}
```

- [ ] **Step 2: Verify the `/api/cycles` response shape**

The function accesses `c.action`, `c.ticker`, `c.executed_at`, and `c.reason`. These match the cycle log structure in `backend/db.py`. If the actual API returns different field names (e.g., `symbol` instead of `ticker`), adjust the fallback chain (`c.ticker || c.symbol`).

- [ ] **Step 3: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "feat: AI log renders as compact 2-line-clamp list"
```

---

### Task 11: Cleanup — Remove Orphaned CSS and Old Toggle JS

**Files:**
- Modify: `products/invest-simulator/frontend/index.html`

Remove CSS classes that are no longer used in HTML and any JS that referenced the old collapsible cycle log.

- [ ] **Step 1: Remove old positions CSS**

Search for and delete these CSS rules that are no longer used:
- `.pos-list` (replaced by `.bar-list`)
- `.pos-item`, `.pos-ticker`, `.pos-mkt`, `.pos-shares`, `.pos-right`, `.pos-pnl`, `.pos-val`

- [ ] **Step 2: Remove old cycle-log toggle JS**

Search the JS section for any function like `toggleCycle(el)` or `onclick="toggleCycle` references. Remove the function definition and verify no remaining HTML references it.

- [ ] **Step 3: Remove old metric element references**

The old `m-fx`, `m-pct`, `m-posval`, `m-mkt` element IDs no longer exist in HTML. Search the JS for any `getElementById('m-fx')`, `getElementById('m-pct')`, `getElementById('m-posval')`, `getElementById('m-mkt')` — delete those lines.

- [ ] **Step 4: Final check**

Open `frontend/index.html` in a browser (or via the VPS at invest.trustlink-tk.com) and verify:
- 3 KPI cards visible with colored top borders
- Chart on left (~57%), bar list on right (~43%)
- Trade table shows BUY=blue, SELL=orange, HOLD=gray badges
- AI log shows compact 2-line entries with left border colors

- [ ] **Step 5: Commit**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "chore: remove orphaned pos-list and cycle-log CSS/JS"
```

---

### Task 12: Deploy to VPS

**Files:**
- VPS: `/opt/apps/invest-simulator/` (not a git repo — manual copy required)

- [ ] **Step 1: Push local changes**

```bash
cd /Users/Mac_air/Claude-Workspace
git push origin feature/zinq-suite-mvp
```

- [ ] **Step 2: SSH to VPS and deploy**

```bash
ssh root@46.250.252.99
```

Then on VPS:
```bash
cd /opt/apps/claude-workspace && git pull origin feature/zinq-suite-mvp
cp /opt/apps/claude-workspace/products/invest-simulator/frontend/index.html /opt/apps/invest-simulator/frontend/index.html
cd /opt/apps/invest-simulator && docker compose restart
```

No backend changes = no rebuild needed. Container restart picks up the new static file.

- [ ] **Step 3: Verify in browser**

Open `https://invest.trustlink-tk.com` and confirm the new design renders correctly.

- [ ] **Step 4: Final commit if any last-minute fixes**

```bash
git add products/invest-simulator/frontend/index.html
git commit -m "fix: post-deploy UI adjustments"
git push origin feature/zinq-suite-mvp
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task that covers it |
|---|---|
| 3カラムKPIカード (総資産/損益/現金) | Task 2 (CSS), Task 5 (HTML), Task 8 (JS) |
| border-top: 4px solid アクセントカラー | Task 2 (CSS), Task 5 (HTML) |
| 損益カード正負で緑/赤切替 | Task 8 JS: `border-top-color` dynamically set |
| ピルバッジ (初期比/全体%/総資産比%) | Task 2 (CSS `.metric-pill`), Task 5 (HTML), Task 8 (JS) |
| 2カラム 1.3fr / 1fr | Task 3 (CSS) |
| 資産推移チャート background:#f8fafc wrap | Task 3 (CSS `.chart-wrap`) |
| 保有銘柄バー比較 (損益率絶対値比例) | Task 3 (CSS `.bar-*`), Task 6 (HTML), Task 9 (JS) |
| 含み益#3b82f6/含み損#fca5a5 | Task 3 CSS `.bar-fill.pos/.neg` |
| 取引履歴 BUY#dbeafe/#1d4ed8 etc. | Task 4 (CSS), spec colors match |
| 行border-bottom #f8fafc | Task 4 (CSS `td` rule) |
| AI分析ログ常時2行/border-left | Task 4 (CSS), Task 7 (HTML), Task 10 (JS) |
| BUY左border #3b82f6, SELL #f97316, HOLD #cbd5e1 | Task 4 CSS `.ai-log-entry` |

**Placeholder scan:** No TBDs, no "implement later", all code blocks complete.

**Type consistency:** 
- `metric-pill` class referenced in Task 2 CSS, Task 5 HTML, Task 8 JS — consistent.
- `bar-fill pos/neg` referenced in Task 3 CSS, Task 9 JS — consistent.
- `ai-log-entry BUY/SELL/HOLD` referenced in Task 4 CSS, Task 10 JS — consistent.
- `fetchPositions` → `bar-list` (id=`pos-list`) — container id unchanged, class on wrapper changed to `bar-list` in Task 6.
- Removed metrics: `m-fx`, `m-pct`, `m-posval`, `m-mkt` — Task 11 removes JS references.
