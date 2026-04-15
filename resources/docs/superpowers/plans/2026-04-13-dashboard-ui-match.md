# Dashboard UI — Complete Match with ui-samples6.html

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the deployed eBay Agent Hub dashboard (`/`) visually identical to `ui-samples6.html` — matching colors, font sizes, spacing, charts, layout, and all displayed items.

**Architecture:** Replace the dashboard CSS block in style.css with mockup CSS, rewrite overview.html content to use new class names and structure, update overview.js to match new classes, add a sales table backend endpoint, and restructure the nav sidebar.

**Tech Stack:** FastAPI + Jinja2, vanilla JS, custom CSS, SQLAlchemy (SalesRecord model)

---

## Class Name Mapping Reference

The current implementation uses different CSS class names from the mockup. Every task below follows this mapping:

| Mockup (target) | Current (to replace) |
|---|---|
| `.top-row` | `.achievement-board-4` |
| `.ac.blue/amber/green` | `.achievement-card` + inline border-image |
| `.ac-top`, `.ac-label`, `.badge.g/y/r` | `.ach-label` (no badge) |
| `.ac-vrow`, `.ac-v`, `.ac-t` | `.ach-values`, `.ach-actual`, `.ach-target` |
| `.pb`, `.pf.blue/amber/green` | `.progress-wrap`, `.progress-bar` |
| `.ac-foot` | `.ach-meta` |
| `.pay-card`, `.pay-head`, `.pay-body`, `.pay-row` | `.payoneer-card`, `.payoneer-head`, `.payoneer-body`, `.payoneer-row` |
| `.mid-row` | `.overview-mid-row` |
| `.card`, `.card-h` | `.section` (no header class) |
| `.tab-bar`, `.tab-btn.on`, `.tab-panel.on` | `.chart-tab-bar`, `.chart-tab-btn.active`, `.chart-tab-panel.active` |
| `.kt`, `.kn`, `.kv`, `.mb-w`, `.mini-bar`, `.mini-fill`, `.kd` | `.kpi-comparison-table`, `.kct-name`, `.kct-val`, `.kct-bar-w`, `.kct-bar`, `.kct-fill`, `.kct-diff` |
| `.freee-lbl`, `.freee-row`, `.freee-name`, `.freee-val` | `.freee-section-label`, `.freee-cf-row`, `.freee-cf-name`, `.freee-cf-val` |
| `.cal-tabs`, `.cal-tab.on` | `.cal-tab-bar`, `.cal-tab-btn.active` |
| `.cal-dl`, `.cc.sale-s1/s2/s3`, `.cc.td`, `.cc.ft`, `.cc.em` | `.cal-header`, `.cal-day.has-sales`, `.cal-day.is-today`, `.cal-day.is-future`, `.cal-day.empty` |
| `.action-row`, `.action-card`, `.action-h` | `.oos-card` wrapper missing |
| `.oos-table`, `.oos-days`, `.oos-btn` | `.oos-list-table`, `.oos-days-badge`, `.oos-search-btn` |
| `.modal-overlay.open`, `.modal`, `.modal-head/body/foot` | `.cat-modal-overlay.open`, `.cat-modal`, `.cat-modal-head/body/foot` |
| `.modal-cat-dot`, `.modal-bar`, `.modal-bar-track/fill/pct` | `.cat-dot`, `.cat-pct-bar`, `.cat-pct-track/fill/num` |

---

## File Map

| Action | File |
|---|---|
| Modify (replace lines 1452–1967) | `products/ebay-agent/static/css/style.css` |
| Modify (full rewrite of content + topbar_extra blocks) | `products/ebay-agent/templates/pages/overview.html` |
| Modify (update class refs + add sales table rendering) | `products/ebay-agent/static/js/overview.js` |
| Modify (add recent_sales endpoint) | `products/ebay-agent/main.py` |
| Modify (add crud function) | `products/ebay-agent/database/crud.py` |
| Modify (restructure sidebar) | `products/ebay-agent/templates/components/nav.html` |

---

## Task 1: Replace Dashboard CSS in style.css

**Files:**
- Modify: `products/ebay-agent/static/css/style.css` (lines 1452–end, currently 1967 lines)

- [ ] **Step 1: Identify the boundary**

Run: `grep -n "Achievement Board" products/ebay-agent/static/css/style.css`
Expected: `1452:/* ── Achievement Board ───────────────────────────────── */`

- [ ] **Step 2: Replace lines 1452–1967 with new dashboard CSS**

Use Edit to replace everything from `/* ── Achievement Board` to the end of file with:

```css
/* ── Achievement Board (top-row) ─────────────────────────── */
.top-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 190px;
    gap: 12px;
    margin-bottom: 14px;
}
@media (max-width: 900px) { .top-row { grid-template-columns: 1fr 1fr; } }

.ac {
    background: #fff;
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,.07);
    position: relative;
    overflow: hidden;
    transition: .2s;
}
.ac:hover { box-shadow: 0 4px 14px rgba(0,0,0,.1); }
.ac::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
.ac.blue::before   { background: linear-gradient(90deg,#60A5FA,#1D4ED8); }
.ac.amber::before  { background: linear-gradient(90deg,#FCD34D,#F59E0B); }
.ac.green::before  { background: linear-gradient(90deg,#6EE7B7,#10B981); }

.ac-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.ac-label { font-size:9px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.07em; }
.badge { font-size:9px; font-weight:700; padding:2px 7px; border-radius:20px; }
.badge.g { background:#DCFCE7; color:#15803D; }
.badge.y { background:#FEF9C3; color:#A16207; }
.badge.r { background:#FEE2E2; color:#DC2626; }

.ac-vrow { display:flex; align-items:baseline; gap:6px; margin-bottom:3px; }
.ac-v { font-size:20px; font-weight:800; color:#0F172A; letter-spacing:-.02em; }
.ac-t { font-size:11px; color:#94A3B8; }

.pb { height:5px; background:#F1F5F9; border-radius:3px; overflow:hidden; margin:8px 0 6px; }
.pf { height:100%; border-radius:3px; }
.pf.blue  { background: linear-gradient(90deg,#60A5FA,#2563EB); }
.pf.amber { background: linear-gradient(90deg,#FCD34D,#F59E0B); }
.pf.green { background: linear-gradient(90deg,#6EE7B7,#10B981); }

.ac-foot { display:flex; justify-content:space-between; align-items:center; font-size:9px; color:#94A3B8; }
.ac-foot .proj  { color:#10B981; font-weight:700; }
.ac-foot .warn  { color:#F59E0B; font-weight:700; }

/* Donut modal trigger */
.donut-btn {
    background:none; border:none; cursor:pointer; font-size:11px;
    color:#6366F1; font-weight:700; padding:0;
    display:flex; align-items:center; gap:3px; transition:.15s;
}
.donut-btn:hover { color:#4338CA; }

/* ── Payoneer card ────────────────────────────────────────── */
.pay-card { background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.07); }
.pay-head { background:linear-gradient(135deg,#FF5F00,#FF8533); padding:12px 14px; color:#fff; }
.pay-lbl  { font-size:9px; opacity:.8; letter-spacing:.06em; text-transform:uppercase; margin-bottom:4px; }
.pay-v    { font-size:18px; font-weight:800; letter-spacing:-.02em; }
.pay-sub  { font-size:9px; opacity:.7; margin-top:3px; }
.pay-body { padding:10px 14px; }
.pay-row  { display:flex; justify-content:space-between; font-size:10px; margin-bottom:4px; }
.pay-row:last-child { margin-bottom:0; }
.pay-name { color:#64748B; }
.pay-val  { font-weight:700; color:#0F172A; }
.pay-val.g { color:#10B981; }

/* ── Mid row ──────────────────────────────────────────────── */
.mid-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 12px;
    margin-bottom: 14px;
}
@media (max-width: 1100px) { .mid-row { grid-template-columns: 1fr 1fr; } }

.card {
    background: #fff;
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.card-h {
    font-size:11px; font-weight:700; color:#374151;
    margin-bottom:10px;
    display:flex; align-items:center; justify-content:space-between;
}

/* ── Chart tab switcher ──────────────────────────────────── */
.tab-bar {
    display:flex; border:1px solid #E2E8F0;
    border-radius:8px; overflow:hidden; width:fit-content;
}
.tab-btn {
    padding:4px 12px; font-size:10px; font-weight:600;
    cursor:pointer; border:none; background:#fff; color:#64748B; transition:.15s;
}
.tab-btn.on   { background:#2563EB; color:#fff; }
.tab-panel    { display:none; }
.tab-panel.on { display:block; }

/* Vertical bar chart (日別) */
.vchart {
    display:grid; grid-template-columns:repeat(12,1fr);
    gap:3px; align-items:end; height:78px; margin-top:4px;
}
.vbar-col { display:flex; flex-direction:column; align-items:center; gap:2px; }
.vbar-num { font-size:7px; font-weight:700; color:#64748B; text-align:center; white-space:nowrap; }
.vbar-num.hi { color:#1D4ED8; }
.vbar { width:100%; border-radius:3px 3px 0 0; }
.vbar.lo { background:linear-gradient(0deg,#BFDBFE,#93C5FD); }
.vbar.md { background:linear-gradient(0deg,#93C5FD,#3B82F6); }
.vbar.hi { background:linear-gradient(0deg,#3B82F6,#1D4ED8); box-shadow:0 2px 6px rgba(37,99,235,.25); }
.vbar-day { font-size:8px; color:#94A3B8; font-weight:600; }

/* Monthly cumulative SVG chart */
.chart-legend { display:flex; gap:12px; margin-bottom:8px; flex-wrap:wrap; }
.leg-item { display:flex; align-items:center; gap:5px; font-size:10px; color:#374151; font-weight:600; }
.leg-line { width:16px; height:2px; border-radius:1px; }
.leg-line.solid { background:#2563EB; }
.leg-line.dg { background:repeating-linear-gradient(90deg,#94A3B8 0,#94A3B8 4px,transparent 4px,transparent 8px); }
.leg-line.do { background:repeating-linear-gradient(90deg,#F97316 0,#F97316 4px,transparent 4px,transparent 8px); }

.chart-svg-wrap { display:flex; }
.y-labels { display:flex; flex-direction:column; justify-content:space-between; padding-bottom:16px; padding-top:2px; width:34px; }
.y-lbl { font-size:8px; color:#94A3B8; text-align:right; }
.x-labels { display:flex; justify-content:space-between; padding-left:34px; margin-top:2px; }
.x-lbl { font-size:8px; color:#94A3B8; }

/* 月別累計下部 3-box summary */
.chart-summary { display:flex; gap:10px; margin-top:8px; }
.chart-summary-box { border-radius:6px; padding:6px 10px; flex:1; }
.chart-summary-box .cs-label { font-size:9px; color:#64748B; margin-bottom:2px; }
.chart-summary-box .cs-val   { font-size:12px; font-weight:700; }
.chart-summary-box .cs-sub   { font-size:9px; color:#64748B; }
.csb-blue   { background:#EFF6FF; }
.csb-blue   .cs-val { color:#2563EB; }
.csb-yellow { background:#FEF9C3; }
.csb-yellow .cs-val { color:#F59E0B; }
.csb-green  { background:#ECFDF5; }
.csb-green  .cs-val { color:#10B981; }

/* ── KPI comparison table ────────────────────────────────── */
.kt { width:100%; border-collapse:collapse; }
.kt tr { border-bottom:1px solid #F8FAFC; }
.kt tr:last-child { border-bottom:none; }
.kt td { padding:5px 3px; font-size:11px; }
.kn  { color:#64748B; font-weight:500; width:60px; }
.kv  { font-weight:700; color:#0F172A; text-align:right; padding-right:4px; white-space:nowrap; }
.mb-w { width:54px; }
.mini-bar  { height:4px; background:#F1F5F9; border-radius:2px; overflow:hidden; }
.mini-fill { height:100%; border-radius:2px; }
.mf-b { background:#3B82F6; }
.mf-r { background:#EF4444; }
.mf-o { background:#F97316; }
.kd { font-size:10px; font-weight:700; text-align:right; white-space:nowrap; }
.kd.up { color:#10B981; }
.kd.dn { color:#EF4444; }
.kd.or { color:#F97316; }

/* freee divider + cashflow */
.freee-divider { border:none; border-top:1px dashed #E2E8F0; margin:10px 0 8px; }
.freee-lbl {
    font-size:9px; font-weight:700; color:#94A3B8;
    text-transform:uppercase; letter-spacing:.07em;
    margin-bottom:7px; display:flex; align-items:center; gap:5px;
}
.freee-row {
    display:flex; justify-content:space-between; align-items:center;
    padding:4px 0; font-size:11px; border-bottom:1px solid #F8FAFC;
}
.freee-row:last-child { border-bottom:none; }
.freee-name { color:#64748B; }
.freee-val  { font-weight:700; color:#0F172A; }
.freee-val.g { color:#10B981; }
.freee-val.r { color:#EF4444; }

/* ── Calendar card ───────────────────────────────────────── */
.cal-tabs {
    display:flex; border:1px solid #E2E8F0; border-radius:6px;
    overflow:hidden; margin-bottom:7px; width:100%;
}
.cal-tab {
    flex:1; padding:3px 0; font-size:10px; font-weight:600;
    cursor:pointer; border:none; background:#fff; color:#64748B; text-align:center;
}
.cal-tab.on { background:#2563EB; color:#fff; }

.cal-head { display:grid; grid-template-columns:repeat(7,1fr); margin-bottom:3px; }
.cal-dl   { font-size:8px; font-weight:700; color:#94A3B8; text-align:center; }

.cal {
    display:grid; grid-template-columns:repeat(7,1fr); gap:2px;
}
.cc {
    aspect-ratio:1; border-radius:3px; display:flex; align-items:center;
    justify-content:center; font-size:8px; color:#94A3B8;
    background:#F8FAFC; cursor:pointer; transition:.15s;
}
.cc:hover:not(.ft):not(.em) { transform:scale(1.1); z-index:1; }
.cc.sale-s1 { background:#DBEAFE; color:#1E40AF; font-weight:700; }
.cc.sale-s2 { background:#BFDBFE; color:#1D4ED8; font-weight:800; }
.cc.sale-s3 { background:#93C5FD; color:#1E3A8A; font-weight:800; }
.cc.pay-s1  { background:#DCFCE7; color:#15803D; font-weight:700; }
.cc.pay-s2  { background:#BBF7D0; color:#166534; font-weight:800; }
.cc.pay-s3  { background:#86EFAC; color:#14532D; font-weight:800; }
.cc.td  { background:#2563EB; color:#fff; font-weight:800; box-shadow:0 2px 8px rgba(37,99,235,.4); }
.cc.td-p{ background:#10B981; color:#fff; font-weight:800; box-shadow:0 2px 8px rgba(16,185,129,.4); }
.cc.ft  { color:#E2E8F0; }
.cc.em  { background:transparent; }
.cal-note { margin-top:6px; font-size:10px; color:#64748B; display:flex; align-items:center; gap:5px; }

/* ── Action row (OOS) ────────────────────────────────────── */
.action-row { display:grid; grid-template-columns:1fr; gap:12px; margin-bottom:14px; }
.action-card { background:#fff; border-radius:10px; padding:14px 16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
.action-h {
    font-size:11px; font-weight:700; color:#374151; margin-bottom:10px;
    display:flex; align-items:center; justify-content:space-between;
}
.action-h span { font-size:10px; color:#94A3B8; font-weight:500; cursor:pointer; }
.action-h span:hover { color:#2563EB; }

.oos-table { width:100%; border-collapse:collapse; }
.oos-table th {
    padding:6px 8px; text-align:left; font-size:9px; font-weight:700;
    color:#94A3B8; text-transform:uppercase; letter-spacing:.04em;
    border-bottom:1px solid #F1F5F9; background:#FAFAFA;
}
.oos-table td {
    padding:7px 8px; font-size:11px; color:#374151;
    border-bottom:1px solid #F8FAFC; vertical-align:middle;
}
.oos-table tbody tr:last-child td { border-bottom:none; }
.oos-table tbody tr:hover td { background:#F8FAFC; }
.oos-days { background:#FEE2E2; color:#DC2626; font-size:9px; font-weight:700; padding:2px 6px; border-radius:10px; }
.oos-btn  { background:#EFF6FF; color:#2563EB; font-size:9px; font-weight:700; padding:3px 8px; border-radius:6px; border:none; cursor:pointer; }
.oos-btn:hover { background:#DBEAFE; }

/* ── Sales table ─────────────────────────────────────────── */
.table-wrap { background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-bottom:16px; }
.table-head {
    padding:12px 18px; border-bottom:1px solid #F1F5F9;
    display:flex; justify-content:space-between; align-items:center;
}
.table-head h3 { font-size:13px; font-weight:700; color:#0F172A; }
.tbl-meta { font-size:11px; color:#94A3B8; }

table.dt { width:100%; border-collapse:collapse; }
table.dt th {
    padding:8px 14px; text-align:left; font-size:9px; font-weight:700;
    color:#94A3B8; text-transform:uppercase; letter-spacing:.05em;
    background:#FAFAFA; border-bottom:1px solid #F1F5F9;
}
table.dt td {
    padding:9px 14px; font-size:11px; color:#374151;
    border-bottom:1px solid #F8FAFC; vertical-align:middle;
}
table.dt tbody tr:hover td { background:#F8FAFC; }
table.dt tbody tr:last-child td { border-bottom:none; }

.ib  { display:flex; align-items:center; gap:6px; }
.ibt { flex:1; height:5px; background:#F1F5F9; border-radius:3px; overflow:hidden; min-width:44px; }
.ibf { height:100%; border-radius:3px; }
.ibf.hi { background:linear-gradient(90deg,#6EE7B7,#10B981); }
.ibf.md { background:linear-gradient(90deg,#93C5FD,#3B82F6); }
.ibf.lo { background:#EF4444; }
.ibv { font-size:10px; font-weight:700; min-width:32px; text-align:right; }
.ibv.hi { color:#10B981; }
.ibv.md { color:#3B82F6; }
.ibv.lo { color:#EF4444; }

.st { display:inline-flex; padding:2px 8px; border-radius:20px; font-size:9px; font-weight:700; }
.st.sold { background:#DCFCE7; color:#15803D; }
.st.ship { background:#DBEAFE; color:#1D4ED8; }
.st.pend { background:#FEF9C3; color:#A16207; }

/* ── USD/JPY rate chip ───────────────────────────────────── */
.fx-chip {
    display:flex; align-items:center; gap:5px;
    background:#F8FAFC; border:1px solid #E2E8F0; border-radius:7px;
    padding:4px 10px; font-size:11px; cursor:default; white-space:nowrap;
}
.fx-label { color:#64748B; font-weight:500; }
.fx-val   { color:#0F172A; font-weight:800; }
.fx-diff  { font-size:10px; font-weight:700; }
.fx-diff.up { color:#EF4444; }
.fx-diff.dn { color:#10B981; }

/* ── Today tag ───────────────────────────────────────────── */
.today-tag {
    background:#EFF6FF; color:#2563EB; font-size:10px; font-weight:700;
    padding:3px 9px; border-radius:20px; border:1px solid #DBEAFE;
    margin-left:8px; vertical-align:middle;
}

/* ── Topbar right controls ───────────────────────────────── */
.t-sel {
    border:1px solid #E2E8F0; background:#fff;
    padding:5px 10px; border-radius:7px; font-size:11px; color:#374151;
}
.t-btn {
    background:#2563EB; color:#fff; border:none;
    padding:6px 14px; border-radius:8px; font-size:12px; font-weight:700; cursor:pointer;
}
.t-btn:hover { background:#1D4ED8; }

/* ── Modal (category profit) ─────────────────────────────── */
.modal-overlay {
    position:fixed; inset:0; background:rgba(15,23,42,.5);
    display:none; align-items:center; justify-content:center;
    z-index:9999; backdrop-filter:blur(2px);
}
.modal-overlay.open { display:flex; }
.modal {
    background:#fff; border-radius:14px; width:520px;
    box-shadow:0 20px 60px rgba(0,0,0,.2); overflow:hidden;
}
.modal-head {
    padding:18px 20px; border-bottom:1px solid #F1F5F9;
    display:flex; justify-content:space-between; align-items:center;
}
.modal-head h3 { font-size:15px; font-weight:800; color:#0F172A; }
.modal-close { background:none; border:none; font-size:20px; color:#94A3B8; cursor:pointer; line-height:1; }
.modal-close:hover { color:#374151; }
.modal-body { padding:20px; display:flex; gap:20px; align-items:flex-start; }
.modal-donut { flex-shrink:0; }
.modal-table { flex:1; }
.modal-table table { width:100%; border-collapse:collapse; }
.modal-table th {
    padding:7px 8px; text-align:left; font-size:10px; font-weight:700;
    color:#94A3B8; text-transform:uppercase; border-bottom:1px solid #F1F5F9;
}
.modal-table td {
    padding:8px 8px; font-size:12px; color:#374151;
    border-bottom:1px solid #F8FAFC; vertical-align:middle;
}
.modal-table tr:last-child td { border-bottom:none; }
.modal-bar { display:flex; align-items:center; gap:6px; }
.modal-bar-track { flex:1; height:5px; background:#F1F5F9; border-radius:3px; overflow:hidden; }
.modal-bar-fill  { height:100%; border-radius:3px; }
.modal-bar-pct   { font-size:10px; font-weight:700; min-width:30px; text-align:right; }
.modal-cat-dot   { width:8px; height:8px; border-radius:50%; flex-shrink:0; display:inline-block; margin-right:6px; }
.modal-foot {
    padding:14px 20px; border-top:1px solid #F1F5F9;
    font-size:11px; color:#64748B; background:#FAFAFA;
}
```

- [ ] **Step 3: Verify no duplicate class names remain**

Run:
```bash
grep -n "achievement-board\|achievement-card\|payoneer-card\|overview-mid-row\|kpi-comparison-table\|oos-card\|cat-modal-overlay" products/ebay-agent/static/css/style.css
```
Expected: no output (old classes gone)

- [ ] **Step 4: Commit**

```bash
cd products/ebay-agent
git add static/css/style.css
git commit -m "style: replace dashboard CSS with mockup-matching classes"
```

---

## Task 2: Rewrite overview.html

**Files:**
- Modify: `products/ebay-agent/templates/pages/overview.html`

Note: The file is 248 lines. Do a complete replacement of the file.

- [ ] **Step 1: Replace entire file with new content**

```jinja
{% extends "base.html" %}
{% block title %}ダッシュボード — eBay Agent Hub{% endblock %}
{% block breadcrumb %}ダッシュボード{% endblock %}
{% block page_title %}<span data-en="Dashboard" data-ja="ダッシュボード">ダッシュボード</span><span class="today-tag" id="todayTag"></span>{% endblock %}

{% block topbar_extra %}
<div class="fx-chip" id="fxChip" title="USD/JPY レート">
  <span class="fx-label">USD/JPY</span>
  <span class="fx-val" id="fxRate">—</span>
  <span class="fx-diff" id="fxDiff"></span>
</div>
<select class="t-sel" id="monthSel" onchange="void(0)">
  <option>2026年4月</option>
</select>
<button class="t-btn" onclick="window.location='/listings/new'">＋ 出品登録</button>
{% endblock %}

{% block content %}

<!-- ① Alert Strip -->
<div id="alertStrip" class="alert-strip" style="display:none"></div>

<!-- ② Top Row: 3 achievement cards + payoneer -->
<div class="top-row">

  <!-- 月間売上 -->
  <div class="ac blue">
    <div class="ac-top">
      <div class="ac-label">月間売上</div>
      <span class="badge g" id="revBadge">—%</span>
    </div>
    <div class="ac-vrow">
      <span class="ac-v" id="revActual">¥—</span>
      <span class="ac-t">/ ¥5,000,000</span>
    </div>
    <div class="pb"><div class="pf blue" id="revBar" style="width:0%"></div></div>
    <div class="ac-foot">
      <span id="revRemain">—</span>
      <span id="revPace" class="proj"></span>
    </div>
  </div>

  <!-- 利益率 -->
  <div class="ac amber">
    <div class="ac-top">
      <div class="ac-label">利益率</div>
      <span class="badge y" id="marginBadge">—%</span>
    </div>
    <div class="ac-vrow">
      <span class="ac-v" id="marginActual">—%</span>
      <span class="ac-t">/ 20%</span>
    </div>
    <div class="pb"><div class="pf amber" id="marginBar" style="width:0%"></div></div>
    <div class="ac-foot">
      <span id="marginDiff">—</span>
      <span id="marginPace" class="warn"></span>
    </div>
  </div>

  <!-- 月間利益 -->
  <div class="ac green">
    <div class="ac-top">
      <div class="ac-label">月間利益</div>
      <span class="badge r" id="profitBadge">—%</span>
    </div>
    <div class="ac-vrow">
      <span class="ac-v" id="profitActual">¥—</span>
      <span class="ac-t">/ ¥1,000,000</span>
    </div>
    <div class="pb"><div class="pf green" id="profitBar" style="width:0%"></div></div>
    <div class="ac-foot">
      <span id="profitPace" class="proj"></span>
      <button class="donut-btn" onclick="openModal()">📊 カテゴリ分析 ↗</button>
    </div>
  </div>

  <!-- Payoneer -->
  <div class="pay-card">
    <div class="pay-head">
      <div class="pay-lbl">Payoneer</div>
      <div class="pay-v" id="pyBalance">$—</div>
      <div class="pay-sub" id="pySub">≈ ¥— (—円)</div>
    </div>
    <div class="pay-body">
      <div class="pay-row"><span class="pay-name">今月入金</span><span class="pay-val g" id="pyIncome">+$—</span></div>
      <div class="pay-row"><span class="pay-name" id="pyLastDate">前回 —</span><span class="pay-val" id="pyLastAmt">—</span></div>
      <div class="pay-row"><span class="pay-name">未決済</span><span class="pay-val" id="pyPending">$—</span></div>
      <div class="pay-row"><span class="pay-name">次回予定</span><span class="pay-val" id="pyNext" style="color:#2563EB">—頃</span></div>
    </div>
  </div>

</div>

<!-- ③ Mid Row: Chart + KPI/freee + Calendar -->
<div class="mid-row">

  <!-- Chart card -->
  <div class="card">
    <div class="card-h">
      <span>売上トレンド</span>
      <div class="tab-bar">
        <button class="tab-btn" id="tab-daily"   onclick="switchChart('daily')">日別</button>
        <button class="tab-btn on" id="tab-monthly" onclick="switchChart('monthly')">月別累計</button>
      </div>
    </div>

    <!-- 日別 panel -->
    <div class="tab-panel" id="panel-daily">
      <div style="font-size:10px;color:#94A3B8;margin-bottom:6px" id="dailySubLabel"></div>
      <div class="vchart" id="dailyBarChart">
        <div style="color:#94A3B8;font-size:11px;grid-column:1/-1;text-align:center;padding:20px 0">Loading...</div>
      </div>
    </div>

    <!-- 月別累計 panel -->
    <div class="tab-panel on" id="panel-monthly">
      <div class="chart-legend">
        <div class="leg-item"><div class="leg-line solid"></div>今月累計</div>
        <div class="leg-item"><div class="leg-line dg"></div>目標ライン</div>
        <div class="leg-item"><div class="leg-line do"></div>先月同日</div>
        <div style="margin-left:auto;font-size:10px;color:#64748B">目標: ¥5,000,000</div>
      </div>
      <div class="chart-svg-wrap">
        <div class="y-labels" id="monthlyYLabels"></div>
        <svg id="monthlyChartSvg" width="100%" height="100" style="flex:1;overflow:visible"></svg>
      </div>
      <div class="x-labels" id="monthlyXLabels"></div>
      <div class="chart-summary">
        <div class="chart-summary-box csb-blue">
          <div class="cs-label">今月ペース</div>
          <div class="cs-val" id="csPace">—</div>
          <div class="cs-sub">前月同日比</div>
        </div>
        <div class="chart-summary-box csb-yellow">
          <div class="cs-label">目標比</div>
          <div class="cs-val" id="csTarget">—</div>
          <div class="cs-sub">目標ライン対比</div>
        </div>
        <div class="chart-summary-box csb-green">
          <div class="cs-label">月末予測</div>
          <div class="cs-val" id="csEom">—</div>
          <div class="cs-sub" id="csEomSub">—</div>
        </div>
      </div>
    </div>
  </div>

  <!-- KPI + freee card -->
  <div class="card">
    <div class="card-h">📈 KPI 前月同日比</div>
    <table class="kt" id="kpiTable">
      <tr><td class="kn">—</td><td class="kv">—</td><td class="mb-w"><div class="mini-bar"><div class="mini-fill mf-b" style="width:0%"></div></div></td><td class="kd">—</td></tr>
    </table>
    <hr class="freee-divider">
    <div class="freee-lbl">📋 freee キャッシュフロー</div>
    <div class="freee-row"><span class="freee-name">口座残高</span><span class="freee-val" id="freeeBalance">—</span></div>
    <div class="freee-row"><span class="freee-name">今月収入</span><span class="freee-val g" id="freeeIncome">—</span></div>
    <div class="freee-row"><span class="freee-name">今月支出</span><span class="freee-val r" id="freeeExpense">—</span></div>
    <div class="freee-row"><span class="freee-name">純CF</span><span class="freee-val" id="freeeCF">—</span></div>
  </div>

  <!-- Calendar card -->
  <div class="card">
    <div class="card-h">📅 <span id="calMonthLabel">—</span></div>
    <div class="cal-tabs">
      <button class="cal-tab on" id="cal-tab-sale" onclick="switchCal('sale')">売上</button>
      <button class="cal-tab"    id="cal-tab-pay"  onclick="switchCal('pay')">入金</button>
    </div>
    <div id="salesCalendar"><div style="color:#94A3B8;font-size:11px;text-align:center;padding:20px">Loading...</div></div>
    <div id="payCalendar"  style="display:none"></div>
    <div class="cal-note" id="calNote" style="display:none">
      <div style="width:7px;height:7px;background:#2563EB;border-radius:50%"></div>
      <span id="calNoteText"></span>
    </div>
  </div>

</div>

<!-- ④ Out-of-stock -->
<div class="action-row">
  <div class="action-card">
    <div class="action-h">
      ⚠️ 在庫切れ商品 <span id="oosCount"></span>
      <span onclick="window.location='/sourcing'">仕入れ検索 →</span>
    </div>
    <table class="oos-table">
      <thead>
        <tr><th>商品名</th><th>最終売価</th><th>切れて</th><th></th></tr>
      </thead>
      <tbody id="oosTableBody">
        <tr><td colspan="4" style="text-align:center;color:#94A3B8;padding:16px">Loading...</td></tr>
      </tbody>
    </table>
    <div style="font-size:10px;color:#94A3B8;margin-top:8px;text-align:center" id="oosMore"></div>
  </div>
</div>

<!-- ⑤ Sales table -->
<div class="table-wrap">
  <div class="table-head">
    <h3>売上明細</h3>
    <span class="tbl-meta" id="salesMeta">— 件 / 今月</span>
  </div>
  <table class="dt">
    <thead>
      <tr><th>商品名</th><th>売価</th><th>利益</th><th>利益率</th><th>ステータス</th><th>日付</th></tr>
    </thead>
    <tbody id="salesTableBody">
      <tr><td colspan="6" style="text-align:center;color:#94A3B8;padding:20px">Loading...</td></tr>
    </tbody>
  </table>
</div>

<!-- ⑥ Category modal -->
<div class="modal-overlay" id="catModal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-head">
      <h3 id="catModalTitle">カテゴリ別利益分析 — 2026年4月</h3>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body">
      <div class="modal-donut">
        <svg id="catDonutSvg" width="120" height="120" viewBox="0 0 120 120"></svg>
      </div>
      <div class="modal-table">
        <table>
          <thead>
            <tr><th></th><th>カテゴリ</th><th>利益</th><th>構成比</th></tr>
          </thead>
          <tbody id="catModalTableBody">
            <tr><td colspan="4" style="text-align:center;color:#94A3B8;padding:20px">Loading...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="modal-foot" id="catModalFoot"></div>
  </div>
</div>

{% endblock %}

{% block scripts %}
<script src="/static/js/overview.js"></script>
{% endblock %}
```

- [ ] **Step 2: Verify render**

Run: `python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('templates')); t=e.get_template('pages/overview.html'); print('OK')"` from `products/ebay-agent/`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add templates/pages/overview.html
git commit -m "feat: rewrite overview.html with mockup-matching class names and structure"
```

---

## Task 3: Update overview.js

**Files:**
- Modify: `products/ebay-agent/static/js/overview.js`

This task updates every CSS class reference in overview.js to match the new HTML/CSS, and adds sales table rendering.

- [ ] **Step 1: Update `setText` for today-tag**

Find `initOverview` function (near end of file) and add today-tag initialization before the async calls:

```javascript
// Add right after "async function initOverview() {"
    // Today tag
    const todayEl = document.getElementById('todayTag');
    if (todayEl) {
        const now = new Date();
        todayEl.textContent = `本日 ${now.getMonth()+1}/${now.getDate()}`;
    }
```

- [ ] **Step 2: Update `switchChart` to use `.on` class**

Replace:
```javascript
function switchChart(mode) {
    ['daily','monthly'].forEach(m => {
        document.getElementById(`tab-${m}`).classList.toggle('active', m === mode);
        document.getElementById(`panel-${m}`).classList.toggle('active', m === mode);
    });
}
```

With:
```javascript
function switchChart(mode) {
    ['daily','monthly'].forEach(m => {
        document.getElementById(`tab-${m}`).classList.toggle('on', m === mode);
        document.getElementById(`panel-${m}`).classList.toggle('on', m === mode);
    });
}
```

- [ ] **Step 3: Update `switchCal` for new tab IDs**

Replace:
```javascript
function switchCal(mode) {
    ['sale','pay'].forEach(m => {
        document.getElementById(`cal-tab-${m}`).classList.toggle('active', m === mode);
        document.getElementById(`cal-panel-${m}`).classList.toggle('active', m === mode);
    });
}
```

With:
```javascript
function switchCal(mode) {
    const s = mode === 'sale';
    document.getElementById('salesCalendar').style.display = s ? '' : 'none';
    document.getElementById('payCalendar').style.display   = s ? 'none' : '';
    document.getElementById('cal-tab-sale').classList.toggle('on', s);
    document.getElementById('cal-tab-pay').classList.toggle('on', !s);
}
```

- [ ] **Step 4: Update `renderAchievement` — add badge updates**

In `renderAchievement(data)`, after `setText('revActual', fmt(rev.actual));` add:
```javascript
    // Badges
    const revBadge = document.getElementById('revBadge');
    if (revBadge) {
        revBadge.textContent = `${Math.round(rev.rate)}% 達成`;
        revBadge.className = `badge ${rev.rate >= 100 ? 'g' : rev.rate >= 80 ? 'y' : 'r'}`;
    }
    const revRemainEl = document.getElementById('revRemain');
    if (revRemainEl) revRemainEl.textContent = `残 ${fmtM(Math.max(rev.target - rev.actual, 0))}`;
```

After `setText('marginActual', ...)` add:
```javascript
    const marginBadge = document.getElementById('marginBadge');
    if (marginBadge) {
        marginBadge.textContent = `${Math.round(marginRatePct)}% 達成`;
        marginBadge.className = `badge ${marginRatePct >= 100 ? 'g' : marginRatePct >= 80 ? 'y' : 'r'}`;
    }
```

After `setText('profitActual', ...)` add:
```javascript
    const profitBadge = document.getElementById('profitBadge');
    if (profitBadge) {
        profitBadge.textContent = `${Math.round(profit.rate)}% 達成`;
        profitBadge.className = `badge ${profit.rate >= 100 ? 'g' : profit.rate >= 80 ? 'y' : 'r'}`;
    }
    const profitPaceEl = document.getElementById('profitPace');
    if (profitPaceEl) {
        const icon = profit.projected_eom >= profit.target ? '✅' : '📉';
        profitPaceEl.textContent = `予測: ${fmtM(profit.projected_eom)} ${icon}`;
    }
```

- [ ] **Step 5: Update Payoneer static render**

Replace `renderPayoneerStatic`:
```javascript
function renderPayoneerStatic() {
    setText('pyBalance', '$2,840');
    setText('pySub',     '≈ ¥432,899 (152.4円)');
    setText('pyIncome',  '+$1,240');
    const lastDate = document.getElementById('pyLastDate');
    if (lastDate) lastDate.textContent = '前回 4/9';
    setText('pyLastAmt', '+$580');
    setText('pyPending', '$340');
    setText('pyNext',    '4/16頃');
}
```

- [ ] **Step 6: Update `kpiRow()` class names**

Replace:
```javascript
function kpiRow(name, value, fillPct, fillClass, diff, diffClass) {
    return `<tr>
        <td class="kct-name">${escapeHtml(name)}</td>
        <td class="kct-val">${escapeHtml(value)}</td>
        <td class="kct-bar-w"><div class="kct-bar"><div class="kct-fill ${fillClass}" style="width:${Math.min(fillPct,100)}%"></div></div></td>
        <td class="kct-diff ${diffClass}">${escapeHtml(diff)}</td>
    </tr>`;
}
```

With:
```javascript
function kpiRow(name, value, fillPct, fillClass, diff, diffClass) {
    return `<tr>
        <td class="kn">${escapeHtml(name)}</td>
        <td class="kv">${escapeHtml(value)}</td>
        <td class="mb-w"><div class="mini-bar"><div class="mini-fill ${fillClass}" style="width:${Math.min(fillPct,100)}%"></div></div></td>
        <td class="kd ${diffClass}">${escapeHtml(diff)}</td>
    </tr>`;
}
```

- [ ] **Step 7: Update `renderKpiComparison` — add Payoneer row + rename IDs + update fill classes**

In `renderKpiComparison`, change `document.getElementById('kpiCompTable')` to `document.getElementById('kpiTable')`.

Change the `tbl.innerHTML =` block: replace all `'blue'` fill class → `'mf-b'`, `'red'` → `'mf-r'`.

Change `'up'` diffClass → `'up'` (keep), `'down'` → `'dn'`, `'neutral'` → `'or'`.

Add Payoneer row at the end:
```javascript
    tbl.innerHTML =
        kpiRow('売上',    fmt(rev.actual),              rev.rate,                              'mf-b',   `${revSign}${revDiffPct}%↑`,  revCls)  +
        kpiRow('利益率',  `${margin.actual.toFixed(1)}%`, margin.target > 0 ? margin.actual / margin.target * 100 : 0, 'mf-b', `${margSign}${marginDiff.toFixed(1)}pp`, margCls) +
        kpiRow('出品数',  `${listingCount}件`,            Math.min(listingCount / 200 * 100, 100), 'mf-b', '—', 'or') +
        kpiRow('在庫切れ',`${oosCount}件`,                Math.min(oosCount / 20 * 100, 100),    'mf-r', '—', 'or') +
        kpiRow('注文数',  `${orderCount}件`,              Math.min(orderCount / 100 * 100, 100), 'mf-b', `${ordSign}${orderDiffPct}%`, ordCls) +
        kpiRow('Payoneer','$2,840',                      70,                                    'mf-o', '+$580', 'or');
```

- [ ] **Step 8: Update `renderFreeeStatic` class names**

Replace:
```javascript
function renderFreeeStatic() {
    setText('freeeBalance', '¥1,234,567');
    setText('freeeIncome',  '+¥890,000');
    setText('freeeExpense', '-¥340,000');
    const cfEl = document.getElementById('freeeCF');
    if (cfEl) {
        cfEl.textContent = '+¥550,000';
        cfEl.className = 'freee-cf-val positive';
    }
}
```

With:
```javascript
function renderFreeeStatic() {
    setText('freeeBalance', '¥1,234,567');
    setText('freeeIncome',  '+¥890,000');
    setText('freeeExpense', '-¥340,000');
    const cfEl = document.getElementById('freeeCF');
    if (cfEl) {
        cfEl.textContent = '+¥550,000';
        cfEl.className = 'freee-val g';
    }
}
```

- [ ] **Step 9: Update `buildCalGrid` to use mockup classes**

Replace the entire `buildCalGrid` function:
```javascript
function buildCalGrid(year, month, days, cellFn) {
    const firstDow = new Date(year, month - 1, 1).getDay();
    const headJa   = ['日','月','火','水','木','金','土'];
    let html = '<div class="cal-head">';
    headJa.forEach(h => { html += `<div class="cal-dl">${h}</div>`; });
    html += '</div><div class="cal">';
    for (let i = 0; i < firstDow; i++) html += '<div class="cc em"></div>';
    days.forEach(d => { html += cellFn(d); });
    html += '</div>';
    return html;
}
```

- [ ] **Step 10: Update `renderSalesCal` cell function**

Replace the `el.innerHTML = buildCalGrid(...)` call in `renderSalesCal`:
```javascript
function renderSalesCal(data) {
    const { year, month, days } = data;
    const today  = new Date().toISOString().slice(0, 10);
    const maxRev = Math.max(...days.map(d => d.revenue), 1);
    const el = document.getElementById('salesCalendar');
    if (!el) return;

    // Set calendar month label
    const monthLabel = document.getElementById('calMonthLabel');
    if (monthLabel) monthLabel.textContent = `${year}年${month}月`;

    el.innerHTML = buildCalGrid(year, month, days, d => {
        const isToday  = d.date === today;
        const isFuture = d.date > today;
        const hasSales = d.revenue > 0;
        const ratio    = hasSales ? d.revenue / maxRev : 0;
        const dayNum   = parseInt(d.date.slice(8));
        let cls = isToday  ? 'cc td' :
                  isFuture ? 'cc ft' :
                  !hasSales ? 'cc' :
                  ratio > 0.7  ? 'cc sale-s3' :
                  ratio > 0.35 ? 'cc sale-s2' : 'cc sale-s1';
        const title = hasSales ? `${fmt(d.revenue)} / ${d.orders}件` : '';
        return `<div class="${cls}" title="${title}">${dayNum}</div>`;
    });

    // Today note
    const todayData = days.find(d => d.date === today);
    const noteEl = document.getElementById('calNote');
    const noteText = document.getElementById('calNoteText');
    if (noteEl && todayData && todayData.revenue > 0) {
        noteText.textContent = `今日: ${fmt(todayData.revenue)} · ${todayData.orders}件`;
        noteEl.style.display = 'flex';
    }
}
```

- [ ] **Step 11: Update `renderPayCal` cell function**

Replace with:
```javascript
function renderPayCal(data) {
    const { year, month, days } = data;
    const today  = new Date().toISOString().slice(0, 10);
    const maxRev = Math.max(...days.map(d => d.revenue), 1);
    const el = document.getElementById('payCalendar');
    if (!el) return;
    el.innerHTML = buildCalGrid(year, month, days, d => {
        const isToday  = d.date === today;
        const isFuture = d.date > today;
        const hasPay   = d.revenue > 0;
        const ratio    = hasPay ? d.revenue / maxRev : 0;
        const dayNum   = parseInt(d.date.slice(8));
        let cls = isToday  ? 'cc td-p' :
                  isFuture ? 'cc ft' :
                  !hasPay  ? 'cc' :
                  ratio > 0.7  ? 'cc pay-s3' :
                  ratio > 0.35 ? 'cc pay-s2' : 'cc pay-s1';
        return `<div class="${cls}">${dayNum}</div>`;
    });
}
```

- [ ] **Step 12: Update `renderDailyChart` class names**

In `renderDailyChart`, update the returned HTML template from `day-bar-col`, `day-bar-num`, `day-bar`, `day-bar-lbl` → `vbar-col`, `vbar-num`, `vbar`, `vbar-day`:

```javascript
        return `<div class="vbar-col">
            <div class="vbar-num ${numCls}">${label}</div>
            <div class="vbar ${cls}" style="height:${height}px"></div>
            <div class="vbar-day">${dayNum}</div>
        </div>`;
```

Also update the daily panel subtitle:
```javascript
    // Add at top of renderDailyChart, after pastDays is set:
    const subLabel = document.getElementById('dailySubLabel');
    if (subLabel && pastDays.length > 0) {
        const m = new Date().getMonth() + 1;
        subLabel.textContent = `日別売上（${m}月1日〜${pastDays.length}日）`;
    }
```

- [ ] **Step 13: Update monthly chart to also fill in summary boxes**

In `renderMonthlyCumulativeChart`, after building the SVG, add summary box updates:

```javascript
    // After svgEl.innerHTML = ... block, add:
    const todayActual  = thisMonthPoints[activeUntil] || 0;
    const todayTarget  = targetPoints[activeUntil] || 0;
    const todayPrevMth = prevMonthPoints[activeUntil] || 0;

    const paceEl  = document.getElementById('csPace');
    const tgtEl   = document.getElementById('csTarget');
    const eomEl   = document.getElementById('csEom');
    const eomSub  = document.getElementById('csEomSub');

    if (paceEl) {
        const diff = todayActual - todayPrevMth;
        const sign = diff >= 0 ? '+' : '-';
        const pct2 = todayPrevMth > 0 ? Math.abs(Math.round(diff / todayPrevMth * 100)) : 0;
        paceEl.textContent = `${sign}${fmtM(Math.abs(diff))} ↑${pct2}%`;
    }
    if (tgtEl) {
        const gap = todayActual - todayTarget;
        const sign = gap >= 0 ? '+' : '-';
        const pct2 = todayTarget > 0 ? Math.abs(Math.round(gap / todayTarget * 100)) : 0;
        tgtEl.textContent = `${sign}${fmtM(Math.abs(gap))} ${gap >= 0 ? '↑' : '↓'}${pct2}%`;
    }
    if (eomEl) {
        const projEom = achData.revenue.projected_eom || 0;
        eomEl.textContent = fmtM(projEom);
        if (eomSub) {
            eomSub.textContent = projEom >= achData.revenue.target ? '目標達成 ✅' : '目標未達 📉';
            eomSub.style.color = projEom >= achData.revenue.target ? '#10B981' : '#EF4444';
        }
    }
```

- [ ] **Step 14: Update `renderOOS` class names**

Replace `.oos-days-badge` and `.oos-search-btn`:
```javascript
        return `<tr>
            <td>${escapeHtml(title)}</td>
            <td>${price}</td>
            <td><span class="oos-days">${days}</span></td>
            <td><a class="oos-btn" href="/sourcing?q=${query}" target="_blank">仕入れ検索</a></td>
        </tr>`;
```

Also update the OOS count label and "more" text. After `tb.innerHTML = ...` in `renderOOS`:
```javascript
    const countEl = document.getElementById('oosCount');
    if (countEl) countEl.textContent = items.length > 0 ? `— ${items.length}件` : '';
    const moreEl = document.getElementById('oosMore');
    if (moreEl) moreEl.textContent = '';
```

- [ ] **Step 15: Update `openCatModal/closeCatModal` and `renderCatModal` class names**

Replace `openCatModal` (currently used in old HTML) → keep same logic but rename modal ID usage:
```javascript
function openModal() {
    document.getElementById('catModal').classList.add('open');
    if (_catData) { renderCatModal(_catData); return; }
    apiFetch('/api/overview/category_profit').then(data => {
        _catData = data;
        renderCatModal(data);
    }).catch(() => {
        const tb = document.getElementById('catModalTableBody');
        if (tb) tb.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:16px;color:#94A3B8">データなし</td></tr>';
    });
}
function closeModal() {
    document.getElementById('catModal').classList.remove('open');
}
```

In `renderCatModal`, update HTML class names:
```javascript
    tb.innerHTML = items.map((item, i) => {
        const color = CAT_COLORS[i % CAT_COLORS.length];
        return `<tr>
            <td><span class="modal-cat-dot" style="background:${color}"></span></td>
            <td>${escapeHtml(item.category)}</td>
            <td style="font-weight:700">${fmt(item.profit)}</td>
            <td>
                <div class="modal-bar">
                    <div class="modal-bar-track"><div class="modal-bar-fill" style="width:${item.pct_of_total}%;background:${color}"></div></div>
                    <span class="modal-bar-pct" style="color:${color}">${item.pct_of_total}%</span>
                </div>
            </td>
        </tr>`;
    }).join('');
```

Also update the SVG in `renderCatModal`: change `cx = 60, cy = 60` to match `width="120" height="120" viewBox="0 0 120 120"`:
```javascript
    if (svgEl) {
        const cx = 60, cy = 60, r = 50, r2 = 28;
        // ... rest of donut code unchanged ...
    }
```

- [ ] **Step 16: Add `renderSalesTable` function and API call**

Add after `renderOOS` function:
```javascript
/* ── Sales table ─────────────────────────────────────────── */
async function loadSalesTable() {
    try {
        const data = await apiFetch('/api/overview/recent_sales');
        renderSalesTable(data);
    } catch (e) {
        const tb = document.getElementById('salesTableBody');
        if (tb) tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#94A3B8;padding:20px">読み込みエラー</td></tr>';
    }
}

function renderSalesTable(data) {
    const tb = document.getElementById('salesTableBody');
    const meta = document.getElementById('salesMeta');
    if (!tb) return;
    if (!data.records || !data.records.length) {
        tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#94A3B8;padding:20px">売上データなし</td></tr>';
        return;
    }
    if (meta) meta.textContent = `${data.total_count}件 / 今月`;

    tb.innerHTML = data.records.map(r => {
        const m  = r.profit_margin;
        const cls = m >= 30 ? 'hi' : m >= 15 ? 'md' : 'lo';
        const barW = Math.min(m, 100);
        const stMap = { '発送済': 'ship', '納品済': 'sold', '未注文': 'pend', '注文済': 'pend' };
        const stCls = stMap[r.status] || 'pend';
        const title = r.title.length > 40 ? r.title.slice(0, 40) + '…' : r.title;
        return `<tr>
            <td>${escapeHtml(title)}</td>
            <td>${fmt(r.sale_price_jpy)}</td>
            <td><strong>${fmt(r.profit_jpy)}</strong></td>
            <td>
                <div class="ib">
                    <div class="ibt"><div class="ibf ${cls}" style="width:${barW}%"></div></div>
                    <span class="ibv ${cls}">${m.toFixed(1)}%</span>
                </div>
            </td>
            <td><span class="st ${stCls}">${escapeHtml(r.status)}</span></td>
            <td>${escapeHtml(r.sold_at)}</td>
        </tr>`;
    }).join('');
}
```

- [ ] **Step 17: Add `loadSalesTable()` to `initOverview`**

In `initOverview`, add `loadSalesTable()` to the Promise.all array:
```javascript
    const [calData, achData] = await Promise.all([
        loadCalendar(),
        loadAchievement(),
        loadFxRate(),
        loadAlerts(),
        loadKpiComparison(),
        loadOOS(),
        loadSalesTable(),
    ]);
```

- [ ] **Step 18: Remove old `openCatModal`/`closeCatModal` if duplicated**

Search for and remove the old `openCatModal` function definition (now replaced by `openModal`/`closeModal`).

- [ ] **Step 19: Commit**

```bash
git add static/js/overview.js
git commit -m "feat: update overview.js to match new CSS class names and add sales table"
```

---

## Task 4: Add /api/overview/recent_sales endpoint

**Files:**
- Modify: `products/ebay-agent/database/crud.py` (add `get_recent_sales`)
- Modify: `products/ebay-agent/main.py` (add endpoint)

- [ ] **Step 1: Add `get_recent_sales` to crud.py**

Append to `products/ebay-agent/database/crud.py` (after the last function):

```python
def get_recent_sales(db, year: int, month: int, limit: int = 15):
    """直近の売上明細（ダッシュボード売上明細テーブル用）"""
    from database.models import SalesRecord
    from sqlalchemy import extract

    records = (
        db.query(SalesRecord)
        .filter(
            extract('year',  SalesRecord.sold_at) == year,
            extract('month', SalesRecord.sold_at) == month,
        )
        .order_by(SalesRecord.sold_at.desc())
        .limit(limit)
        .all()
    )

    total_count = (
        db.query(SalesRecord)
        .filter(
            extract('year',  SalesRecord.sold_at) == year,
            extract('month', SalesRecord.sold_at) == month,
        )
        .count()
    )

    result = []
    for r in records:
        rate = r.exchange_rate if r.exchange_rate > 0 else 152.0
        sale_price_jpy = round(r.sale_price_usd * rate)
        status_map = {
            '発送済': '発送済',
            '納品済': '決済済',
            '未注文': '未発送',
            '注文済': '未発送',
            '':       '未発送',
        }
        status = status_map.get(r.progress, r.progress or '未発送')
        result.append({
            "title":          r.title or '—',
            "sale_price_jpy": sale_price_jpy,
            "profit_jpy":     r.net_profit_jpy,
            "profit_margin":  round(r.profit_margin_pct, 1),
            "status":         status,
            "sold_at":        r.sold_at.strftime("%-m/%-d") if r.sold_at else '—',
        })

    return {"records": result, "total_count": total_count}
```

- [ ] **Step 2: Add endpoint to main.py**

Find the `@app.get("/api/fx/usdjpy")` block in main.py (around line 3844) and add after it:

```python
@app.get("/api/overview/recent_sales")
async def overview_recent_sales():
    """最近の売上明細（ダッシュボード売上テーブル用）"""
    from database.crud import get_recent_sales
    db = get_db()
    try:
        today = datetime.now()
        return JSONResponse(get_recent_sales(db, today.year, today.month, limit=15))
    finally:
        db.close()
```

- [ ] **Step 3: Test endpoint**

Run: `python -c "from database.crud import get_recent_sales; print('import OK')"` from `products/ebay-agent/`
Expected: `import OK`

- [ ] **Step 4: Commit**

```bash
git add database/crud.py main.py
git commit -m "feat: add get_recent_sales crud + /api/overview/recent_sales endpoint"
```

---

## Task 5: Restructure nav.html sidebar

**Files:**
- Modify: `products/ebay-agent/templates/components/nav.html`

- [ ] **Step 1: Replace entire nav.html**

```jinja
<nav class="sidebar">
    <div class="sidebar-logo">
        <span class="logo-icon">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
            </svg>
        </span>
        <span class="logo-text">Agent Hub</span>
    </div>

    <!-- メイン -->
    <div class="nav-section-label">メイン</div>
    <ul class="nav-links">
        <li class="{{ 'active' if request.url.path == '/' }}">
            <a href="/">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z" />
                    </svg>
                </span>
                <span data-ja="ダッシュボード">ダッシュボード</span>
            </a>
        </li>
        <li class="{{ 'active' if request.url.path in ['/listings', '/inventory', '/pricing'] }}">
            <a href="/listings">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15a2.25 2.25 0 0 1 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25ZM6.75 12h.008v.008H6.75V12Zm0 3h.008v.008H6.75V15Zm0 3h.008v.008H6.75V18Z" />
                    </svg>
                </span>
                <span data-ja="出品管理">出品管理</span>
                <span class="nav-badge" id="navListingsBadge" style="display:none;background:#EF4444;color:#fff;font-size:9px;font-weight:700;padding:1px 5px;border-radius:10px;margin-left:auto">0</span>
            </a>
        </li>
        <li class="{{ 'active' if request.url.path in ['/procurement', '/stock', '/sourcing'] }}">
            <a href="/sourcing">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
                    </svg>
                </span>
                <span data-ja="仕入れリサーチ">仕入れリサーチ</span>
                <span class="nav-badge" id="navSourcingBadge" style="display:none;background:#F97316;color:#fff;font-size:9px;font-weight:700;padding:1px 5px;border-radius:10px;margin-left:auto">0</span>
            </a>
        </li>
        <li class="{{ 'active' if request.url.path == '/chat' }}">
            <a href="/chat">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
                    </svg>
                </span>
                <span data-ja="バイヤー対応">バイヤー対応</span>
                <span class="nav-badge" id="navUnreadBadge" style="display:none;background:#EF4444;color:#fff;font-size:9px;font-weight:700;padding:1px 5px;border-radius:10px;margin-left:auto">0</span>
            </a>
        </li>
    </ul>

    <!-- 財務 -->
    <div class="nav-section-label" style="margin-top:8px">財務</div>
    <ul class="nav-links">
        <li class="{{ 'active' if request.url.path in ['/sales', '/profit', '/analytics'] }}">
            <a href="/sales">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
                    </svg>
                </span>
                <span data-ja="売上・利益">売上・利益</span>
            </a>
        </li>
        <li>
            <a href="#">
                <span class="nav-icon">🏦</span>
                <span>Payoneer</span>
            </a>
        </li>
        <li>
            <a href="#">
                <span class="nav-icon">📋</span>
                <span>freee 連携</span>
            </a>
        </li>
        <li class="{{ 'active' if request.url.path == '/reports' }}">
            <a href="/reports">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
                    </svg>
                </span>
                <span data-ja="スケジュール">スケジュール</span>
            </a>
        </li>
    </ul>

    <!-- 設定 -->
    <div class="nav-section-label" style="margin-top:8px">設定</div>
    <ul class="nav-links">
        <li class="{{ 'active' if request.url.path == '/agent' }}">
            <a href="/agent">
                <span class="nav-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                    </svg>
                </span>
                <span data-ja="AIエージェント">AIエージェント</span>
            </a>
        </li>
    </ul>

    <div class="sidebar-footer">
        <div style="display:flex;align-items:center;gap:10px">
            <div style="width:28px;height:28px;background:linear-gradient(135deg,#6366F1,#8B5CF6);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0">H</div>
            <div>
                <div style="font-size:12px;font-weight:700;color:#0F172A">Hiro</div>
                <div style="font-size:10px;color:#94A3B8">管理者</div>
            </div>
        </div>
        <button class="lang-toggle" onclick="toggleLang()" title="言語切替" style="margin-left:auto">
            <span class="lang-label" id="langLabel">EN</span>
        </button>
    </div>
</nav>
```

- [ ] **Step 2: Commit**

```bash
git add templates/components/nav.html
git commit -m "feat: restructure sidebar with メイン/財務/設定 sections and user footer"
```

---

## Task 6: Deploy and verify

- [ ] **Step 1: Push to both remotes**

```bash
git push origin master
git push https://github.com/trust-svg/claude-workspace.git master
```

- [ ] **Step 2: Trigger GitHub Actions deploy**

```bash
curl -s -o /tmp/deploy_result.json \
  -X POST \
  -H "Authorization: Bearer $(gh auth token)" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/trust-svg/factoring-media/actions/workflows/deploy-ebay-agent.yml/dispatches \
  -d '{"ref":"main","inputs":{"message":"dashboard UI match deploy"}}'
echo "Deploy triggered (exit: $?)"
```

- [ ] **Step 3: Verify at https://ebay.trustlink-tk.com**

Check each section matches mockup:
- [ ] Top row: 3 achievement cards (blue/amber/green gradient top border) + Payoneer card (orange gradient header)
- [ ] Achievement cards show badge (達成%), value, progress bar, footer
- [ ] Mid row: chart card with "売上トレンド" title + tabs / KPI table + freee / calendar with tabs
- [ ] Monthly chart has 3 summary boxes (今月ペース/目標比/月末予測)
- [ ] KPI table has 6 rows including Payoneer row
- [ ] Calendar uses `.cc` cells with intensity coloring
- [ ] OOS card uses `.action-card` layout
- [ ] Sales table (売上明細) shows below OOS
- [ ] Old `.stats-grid` 4 stat cards are gone
- [ ] Sidebar shows メイン/財務/設定 sections with user avatar footer

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Remove old stats-grid → Task 2 (no stats-grid in new overview.html)
- ✅ Achievement cards with badge, gradient border → Task 1 CSS + Task 2 HTML
- ✅ Payoneer with 4 rows → Task 2 HTML + Task 3 JS
- ✅ Chart title "売上トレンド" → Task 2 HTML
- ✅ 3 summary boxes below monthly chart → Task 1 CSS + Task 2 HTML + Task 3 JS
- ✅ KPI table 6 rows including Payoneer → Task 3 JS
- ✅ Calendar with `.cc` cells → Task 1 CSS + Task 3 JS
- ✅ OOS with new class names → Task 1 CSS + Task 2 HTML + Task 3 JS
- ✅ Sales table → Task 1 CSS + Task 2 HTML + Task 3 JS + Task 4 backend
- ✅ Modal with new class names → Task 1 CSS + Task 2 HTML + Task 3 JS
- ✅ Sidebar sections → Task 5
- ✅ Today-tag → Task 1 CSS + Task 2 HTML + Task 3 JS

**No placeholders:** All code blocks are complete.

**Type consistency:** `openModal()`/`closeModal()` used in both Task 2 (HTML) and Task 3 (JS). `kpiTable` ID matches across Task 2 HTML and Task 3 JS.
