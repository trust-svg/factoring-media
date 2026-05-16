# Phase 3 Frontend Implementation Plan — Procurement Table UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the card-based Procurement UI in `sourcing.html` with a full-featured table UI (sortable columns, column toggle, scraping, bulk ops), hide the 在庫台帳 tab, and delete dead code.

**Prerequisite:** Backend plan (`2026-05-17-procurement-phase3-backend.md`) must be complete — all `/api/procurements/*` endpoints must be deployed before this plan runs.

**Architecture:** New `procurement-table.js` replaces all inline JS in `sourcing.html`. The file follows the same patterns as `stock.js` (1473 lines) but targets Procurement data and endpoints. `sourcing.html` is updated to use table markup and load the new JS. Dead files `_sourcing_content.html` and `procurement.html` are deleted.

**Tech Stack:** Vanilla JS, HTML/CSS (no framework), FastAPI Jinja2 templates

**Working directory:** `products/ebay-agent/`

**Manual test:** `open http://localhost:8002/sourcing` — verify table renders, sort works, add/edit/delete work, scrape tab visible.

---

### Task 9: Create `procurement-table.js` — core (columns, sort, KPI, render)

**Files:**
- Create: `static/js/procurement-table.js`

No automated tests for pure frontend JS. Manual test after each task.

- [ ] **Step 1: Create `static/js/procurement-table.js` with columns + sort + KPI**

```javascript
/* procurement-table.js — 仕入れ記録テーブルUI */

// ── ソート状態 ──────────────────────────────────────────
let procSortCol = 'purchase_date';
let procSortDir = 'desc';
let procRawData = [];
let procFilterStatus = 'all';
let procFilterPlatform = 'all';
let procSearchQuery = '';
let _procUsdJpy = 149;
let _pendingProcSS = null; // pending screenshot file
let _procScrapePoller = null;

// ── カラム定義 ──────────────────────────────────────────
const PROC_ALL_COLUMNS = [
    { id: 'stock_no',    label: 'No.',       ja: '管理番号',   sortKey: 'stock_number' },
    { id: 'title',       label: 'Product',   ja: '商品名',     sortKey: 'title' },
    { id: 'sku',         label: 'SKU',       ja: 'SKU',        sortKey: 'sku' },
    { id: 'cost',        label: 'Cost',      ja: '原価',       sortKey: 'total_cost_jpy' },
    { id: 'date',        label: 'Date',      ja: '仕入日',     sortKey: 'purchase_date' },
    { id: 'platform',    label: 'Platform',  ja: '仕入先',     sortKey: 'platform' },
    { id: 'status',      label: 'Status',    ja: 'ステータス', sortKey: 'status' },
    { id: 'location',    label: 'Location',  ja: '保管場所',   sortKey: 'location' },
    { id: 'ebay_id',     label: 'eBay ID',   ja: 'eBay ItemID', sortKey: 'ebay_item_id' },
    { id: 'ebay_price',  label: '$Price',    ja: 'eBay販売額', sortKey: 'ebay_price_usd' },
    { id: 'listed_at',   label: 'Listed',    ja: '出品日',     sortKey: 'listed_at' },
    { id: 'sold_at',     label: 'Sold',      ja: '売却日',     sortKey: 'sold_at' },
    { id: 'shipped_at',  label: 'Shipped',   ja: '発送日',     sortKey: 'shipped_at' },
    { id: 'quantity',    label: 'Qty',       ja: '数量',       sortKey: 'quantity' },
    { id: 'condition',   label: 'Condition', ja: '状態',       sortKey: 'condition' },
    { id: 'ss',          label: 'SS',        ja: 'SS',         sortKey: null },
];

const PROC_DEFAULT_COLS = ['stock_no','title','sku','cost','date','platform','status'];
const PROC_COL_KEY = 'proc_column_order';
const PROC_VIS_KEY = 'proc_column_visible';

function getProcColOrder() {
    try {
        const saved = JSON.parse(localStorage.getItem(PROC_COL_KEY) || 'null');
        if (saved) {
            const ids = new Set(PROC_ALL_COLUMNS.map(c => c.id));
            const filtered = saved.filter(id => ids.has(id));
            for (const c of PROC_ALL_COLUMNS) {
                if (!filtered.includes(c.id)) filtered.push(c.id);
            }
            return filtered;
        }
    } catch (e) {}
    return PROC_ALL_COLUMNS.map(c => c.id);
}

function getProcColVisible() {
    try {
        const saved = JSON.parse(localStorage.getItem(PROC_VIS_KEY) || 'null');
        if (saved) return saved;
    } catch (e) {}
    const vis = {};
    for (const c of PROC_ALL_COLUMNS) vis[c.id] = PROC_DEFAULT_COLS.includes(c.id);
    return vis;
}

function saveProcColOrder(order) { localStorage.setItem(PROC_COL_KEY, JSON.stringify(order)); }
function saveProcColVisible(vis) { localStorage.setItem(PROC_VIS_KEY, JSON.stringify(vis)); }

function getProcColDef(id) { return PROC_ALL_COLUMNS.find(c => c.id === id); }

// ── ソート ──────────────────────────────────────────────
function sortProc(col) {
    if (procSortCol === col) {
        procSortDir = procSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        procSortCol = col;
        procSortDir = 'desc';
    }
    renderProcRows(procRawData);
    updateProcSortIcons();
}

function updateProcSortIcons() {
    document.querySelectorAll('#procTable thead th[data-sort]').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (!icon) return;
        if (th.dataset.sort === procSortCol) {
            icon.textContent = procSortDir === 'asc' ? ' ▲' : ' ▼';
            icon.style.opacity = '1';
        } else {
            icon.textContent = ' ⇅';
            icon.style.opacity = '0.3';
        }
    });
}

function compareProc(a, b) {
    const col = PROC_ALL_COLUMNS.find(c => c.id === procSortCol || c.sortKey === procSortCol);
    const key = col ? col.sortKey : procSortCol;
    let va = a[key] ?? '';
    let vb = b[key] ?? '';
    if (procSortCol === 'cost') { va = a.total_cost_jpy || 0; vb = b.total_cost_jpy || 0; }
    if (typeof va === 'string') {
        const cmp = va.localeCompare(vb);
        return procSortDir === 'asc' ? cmp : -cmp;
    }
    return procSortDir === 'asc' ? va - vb : vb - va;
}

// ── 為替レート ───────────────────────────────────────────
async function fetchProcExchangeRate() {
    try {
        const resp = await fetch('/api/exchange-rate');
        const data = await resp.json();
        if (data.usd_to_jpy) _procUsdJpy = data.usd_to_jpy;
    } catch (e) {}
}

// ── KPI ──────────────────────────────────────────────────
async function loadProcStats() {
    try {
        const s = await (await fetch('/api/procurements/stats')).json();
        const el = id => document.getElementById(id);
        if (el('procKpiTotal'))   el('procKpiTotal').textContent   = s.total || 0;
        if (el('procKpiCost'))    el('procKpiCost').textContent    = '¥' + ((s.total_cost_jpy || 0)).toLocaleString();
        if (el('procKpiListed'))  el('procKpiListed').textContent  = s.listed || 0;
        if (el('procKpiSold'))    el('procKpiSold').textContent    = (s.sold || 0) + (s.shipped || 0);
        if (el('procKpiTax'))     el('procKpiTax').textContent     = '¥' + ((s.total_tax_jpy || 0)).toLocaleString();
    } catch (e) { console.error('stats:', e); }
}

// ── テーブルヘッダー（D&D対応） ──────────────────────────
let _procDragCol = null;

function renderProcTableHeader() {
    const thead = document.querySelector('#procTable thead tr');
    if (!thead) return;
    const order = getProcColOrder();
    const vis = getProcColVisible();
    let html = '<th style="width:32px;"><input type="checkbox" id="procSelectAll" onchange="toggleSelectAllProc(this.checked)" style="cursor:pointer;"></th>';
    for (const colId of order) {
        if (!vis[colId]) continue;
        const col = getProcColDef(colId);
        if (!col) continue;
        if (col.sortKey) {
            const isActive = procSortCol === colId || procSortCol === col.sortKey;
            const icon = isActive ? (procSortDir === 'asc' ? ' ▲' : ' ▼') : ' ⇅';
            const opacity = isActive ? '1' : '0.3';
            html += `<th draggable="true" data-col="${colId}" data-sort="${colId}" onclick="sortProc('${colId}')" style="cursor:pointer;user-select:none;">${col.ja}<span class="sort-icon" style="font-size:10px;opacity:${opacity};">${icon}</span></th>`;
        } else {
            html += `<th draggable="true" data-col="${colId}" style="cursor:grab;user-select:none;">${col.ja}</th>`;
        }
    }
    html += '<th></th>';
    thead.innerHTML = html;
    initProcHeaderDragDrop();
}

function initProcHeaderDragDrop() {
    document.querySelectorAll('#procTable thead th[draggable]').forEach(th => {
        th.addEventListener('dragstart', e => {
            _procDragCol = th.dataset.col;
            th.style.opacity = '0.4';
            e.dataTransfer.effectAllowed = 'move';
        });
        th.addEventListener('dragend', () => {
            th.style.opacity = '1';
            _procDragCol = null;
            document.querySelectorAll('#procTable thead th').forEach(h => h.classList.remove('drag-over'));
        });
        th.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; th.classList.add('drag-over'); });
        th.addEventListener('dragleave', () => th.classList.remove('drag-over'));
        th.addEventListener('drop', e => {
            e.preventDefault();
            th.classList.remove('drag-over');
            if (!_procDragCol || _procDragCol === th.dataset.col) return;
            const order = getProcColOrder();
            const from = order.indexOf(_procDragCol);
            const to = order.indexOf(th.dataset.col);
            if (from < 0 || to < 0) return;
            order.splice(from, 1);
            order.splice(to, 0, _procDragCol);
            saveProcColOrder(order);
            renderProcTableHeader();
            renderProcRows(procRawData);
        });
    });
}

// ── プラットフォームバッジ ────────────────────────────────
function platBadgeProc(name) {
    const m = {
        'メルカリ':                {bg:'#FFE4E6', color:'#BE123C'},
        'メルカリShops':           {bg:'#FFE4E6', color:'#BE123C'},
        '楽天':                    {bg:'#CCFBF1', color:'#0F766E'},
        'Amazon':                  {bg:'#FFEDD5', color:'#9A3412'},
        'ヤフオク':                {bg:'#FEF9C3', color:'#854D0E'},
        'ヤフーショッピング':       {bg:'#DCFCE7', color:'#166534'},
        'Yahooフリマ':             {bg:'#E0F2FE', color:'#075985'},
        'ラクマ':                  {bg:'#EDE9FE', color:'#5B21B6'},
        'まんだらけ':              {bg:'#FAE8FF', color:'#86198F'},
        '駿河屋':                  {bg:'#DBEAFE', color:'#1E40AF'},
        'デジマート':              {bg:'#E0E7FF', color:'#3730A3'},
        'GEO':                     {bg:'#D1FAE5', color:'#065F46'},
        'セカンドストリート':       {bg:'#CFFAFE', color:'#155E75'},
        'ネットモール(OFFモール)':  {bg:'#FEF3C7', color:'#92400E'},
        'トレファク':              {bg:'#FCE7F3', color:'#9D174D'},
    };
    const s = m[name] || {bg:'#E2E8F0', color:'#334155'};
    return `<span style="display:inline-block;padding:1px 6px;border-radius:8px;font-size:11px;background:${s.bg};color:${s.color};white-space:nowrap;">${esc(name || '-')}</span>`;
}

// ── ステータスバッジ ────────────────────────────────────
function buildProcStatusBadge(status) {
    const map = {
        'purchased':  { label: '購入済', bg: '#f59e0b', text: 'white' },
        'received':   { label: '入荷済', bg: '#3b82f6', text: 'white' },
        'listed':     { label: '出品中', bg: '#8b5cf6', text: 'white' },
        'sold':       { label: '販売済', bg: '#22c55e', text: 'white' },
        'shipped':    { label: '発送済', bg: '#06b6d4', text: 'white' },
        'returned':   { label: '返品',   bg: '#ef4444', text: 'white' },
        'cancelled':  { label: 'キャンセル', bg: '#6b7280', text: 'white' },
    };
    const c = map[status] || { label: status || '-', bg: '#e2e8f0', text: '#334155' };
    return `<span style="display:inline-block;padding:2px 6px;border-radius:8px;font-size:10px;background:${c.bg};color:${c.text};white-space:nowrap;">${c.label}</span>`;
}

// ── セル描画 ────────────────────────────────────────────
function renderProcCell(colId, p) {
    switch (colId) {
        case 'stock_no':
            return `<td style="font-size:12px;white-space:nowrap;">
                <input type="text" value="${esc(p.stock_number || '')}" placeholder="-"
                    style="width:72px;padding:2px 4px;font-size:12px;border:1px solid transparent;border-radius:4px;background:transparent;text-align:center;"
                    onfocus="this.style.borderColor='var(--brand-500)';this.style.background='white'"
                    onblur="this.style.borderColor='transparent';this.style.background='transparent';saveProcStockNo(${p.id},this.value)"
                    onclick="event.stopPropagation()">
            </td>`;
        case 'title':
            return `<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(p.title)}">
                ${p.image_url ? `<img src="${esc(p.image_url)}" style="width:22px;height:22px;object-fit:cover;border-radius:3px;vertical-align:middle;margin-right:5px;" onerror="this.style.display='none'">` : ''}
                ${esc(p.title)}
            </td>`;
        case 'sku':
            return `<td style="font-family:monospace;font-size:11px;color:#94A3B8;">${esc(p.sku || '-')}</td>`;
        case 'cost':
            return `<td class="num" style="font-weight:600;">¥${(p.total_cost_jpy || 0).toLocaleString()}</td>`;
        case 'date':
            return `<td style="white-space:nowrap;font-size:12px;">${p.purchase_date ? p.purchase_date.slice(0,10) : '-'}</td>`;
        case 'platform':
            return `<td>${platBadgeProc(p.platform)}</td>`;
        case 'status':
            return `<td>${buildProcStatusBadge(p.status)}</td>`;
        case 'location':
            return `<td style="font-size:12px;color:#64748B;">${esc(p.location || '-')}</td>`;
        case 'ebay_id':
            return p.ebay_item_id
                ? `<td><a href="https://www.ebay.com/itm/${encodeURIComponent(p.ebay_item_id)}" target="_blank" style="font-size:11px;color:#2563EB;">${esc(p.ebay_item_id)}</a></td>`
                : `<td style="color:#CBD5E1;font-size:11px;">-</td>`;
        case 'ebay_price':
            return p.ebay_price_usd
                ? `<td class="num" style="font-size:12px;">$${Number(p.ebay_price_usd).toFixed(2)}</td>`
                : `<td style="color:#CBD5E1;font-size:11px;">-</td>`;
        case 'listed_at':
            return `<td style="font-size:12px;">${p.listed_at ? p.listed_at.slice(0,10) : '-'}</td>`;
        case 'sold_at':
            return `<td style="font-size:12px;">${p.sold_at ? p.sold_at.slice(0,10) : '-'}</td>`;
        case 'shipped_at':
            return `<td style="font-size:12px;">${p.shipped_at ? p.shipped_at.slice(0,10) : '-'}</td>`;
        case 'quantity':
            return `<td class="num" style="font-size:12px;">${p.quantity || 1}</td>`;
        case 'condition':
            return `<td style="font-size:12px;color:#64748B;">${esc(p.condition || '-')}</td>`;
        case 'ss':
            return `<td style="text-align:center;">
                ${p.screenshot_path
                    ? `<button onclick="event.stopPropagation();viewProcScreenshot(${p.id},'${esc(p.title)}')" style="font-size:16px;background:none;border:none;cursor:pointer;" title="スクリーンショットを見る">🖼</button>`
                    : `<span style="color:#CBD5E1;font-size:11px;">-</span>`}
            </td>`;
        default:
            return `<td>-</td>`;
    }
}

// ── 一覧読み込み ────────────────────────────────────────
async function loadProcItems() {
    const tbody = document.getElementById('procBody');
    const vis = getProcColVisible();
    const colCount = PROC_ALL_COLUMNS.filter(c => vis[c.id]).length + 2;
    try {
        const data = await apiFetch('/api/procurements');
        procRawData = data;
        if (!data.length) {
            tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;padding:24px;color:#94A3B8;font-size:13px;">データなし</td></tr>`;
            updateProcBulkBar();
            return;
        }
        renderProcRows(data);
        updateProcBulkBar();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;padding:24px;color:#EF4444;">読み込みエラー</td></tr>`;
        console.error(e);
    }
}

function renderProcRows(items) {
    const tbody = document.getElementById('procBody');
    if (!tbody) return;

    const statusF = procFilterStatus;
    const platF = procFilterPlatform;
    const search = procSearchQuery.toLowerCase();

    let filtered = [...items];
    if (statusF !== 'all') filtered = filtered.filter(p => p.status === statusF);
    if (platF !== 'all') filtered = filtered.filter(p => p.platform === platF);
    if (search) filtered = filtered.filter(p =>
        (p.title || '').toLowerCase().includes(search) ||
        (p.sku || '').toLowerCase().includes(search) ||
        (p.platform || '').toLowerCase().includes(search) ||
        (p.stock_number || '').toLowerCase().includes(search) ||
        (p.notes || '').toLowerCase().includes(search)
    );

    filtered.sort(compareProc);

    const order = getProcColOrder();
    const vis = getProcColVisible();

    if (!filtered.length) {
        const colCount = order.filter(id => vis[id]).length + 2;
        tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;padding:24px;color:#94A3B8;font-size:13px;">データなし</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(p => {
        let cells = `<td><input type="checkbox" class="proc-row-check" data-id="${p.id}" onchange="updateProcBulkBar()" style="cursor:pointer;" onclick="event.stopPropagation()"></td>`;
        for (const colId of order) {
            if (!vis[colId]) continue;
            cells += renderProcCell(colId, p);
        }
        cells += `<td style="white-space:nowrap;">
            <button class="proc-btn outline sm" onclick="event.stopPropagation();openProcEditModal(${p.id})">編集</button>
        </td>`;
        return `<tr class="proc-row" onclick="toggleProcDetail(${p.id})" style="cursor:pointer;">${cells}</tr>
        <tr id="proc-detail-${p.id}" style="display:none;">
            <td colspan="99">
                <div style="padding:12px 20px;background:#F8FAFC;border-bottom:1px solid var(--border);display:grid;grid-template-columns:repeat(3,1fr);gap:16px;font-size:12px;">
                    <div>
                        <div style="font-weight:600;margin-bottom:4px;">費用内訳</div>
                        <div>仕入価格: ¥${(p.purchase_price_jpy||0).toLocaleString()}</div>
                        <div>消費税: ¥${(p.consumption_tax_jpy||0).toLocaleString()}</div>
                        <div>送料: ¥${(p.shipping_cost_jpy||0).toLocaleString()}</div>
                        <div>その他: ¥${(p.other_cost_jpy||0).toLocaleString()}</div>
                        <div style="font-weight:700;margin-top:4px;border-top:1px solid #E2E8F0;padding-top:4px;">合計: ¥${(p.total_cost_jpy||0).toLocaleString()}</div>
                    </div>
                    <div>
                        <div style="font-weight:600;margin-bottom:4px;">詳細</div>
                        <div>ID: #${p.id}</div>
                        ${p.purchase_date ? `<div>購入日: ${p.purchase_date.slice(0,10)}</div>` : ''}
                        ${p.received_date ? `<div>受取日: ${p.received_date.slice(0,10)}</div>` : ''}
                        ${p.seller_id ? `<div>出品者: ${esc(p.seller_id)}</div>` : ''}
                        ${p.location ? `<div>保管場所: ${esc(p.location)}</div>` : ''}
                        ${p.url ? `<div><a href="${esc(p.url)}" target="_blank" style="color:#2563EB;">仕入先リンク ↗</a></div>` : ''}
                        ${p.notes ? `<div style="color:#64748B;">📝 ${esc(p.notes)}</div>` : ''}
                    </div>
                    <div>
                        <div style="font-weight:600;margin-bottom:4px;">eBay情報</div>
                        ${p.ebay_item_id ? `<div>Item ID: <a href="https://www.ebay.com/itm/${encodeURIComponent(p.ebay_item_id)}" target="_blank" style="color:#2563EB;">${esc(p.ebay_item_id)}</a></div>` : ''}
                        ${p.ebay_order_id ? `<div>Order ID: ${esc(p.ebay_order_id)}</div>` : ''}
                        ${p.ebay_price_usd ? `<div>販売額: $${Number(p.ebay_price_usd).toFixed(2)} (≈¥${Math.round(p.ebay_price_usd * _procUsdJpy).toLocaleString()})</div>` : ''}
                        ${p.listed_at ? `<div>出品日: ${p.listed_at.slice(0,10)}</div>` : ''}
                        ${p.sold_at ? `<div>売却日: ${p.sold_at.slice(0,10)}</div>` : ''}
                        ${p.shipped_at ? `<div>発送日: ${p.shipped_at.slice(0,10)}</div>` : ''}
                        ${p.sale ? `<div style="color:#10B981;font-weight:600;">利益: ¥${(p.sale.net_profit_jpy||0).toLocaleString()}</div>` : ''}
                    </div>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function toggleProcDetail(id) {
    const row = document.getElementById(`proc-detail-${id}`);
    if (!row) return;
    row.style.display = row.style.display === 'none' ? '' : 'none';
}

// ── フィルタ ────────────────────────────────────────────
function filterProcStatus(status) {
    procFilterStatus = status;
    document.querySelectorAll('.proc-status-tab').forEach(b => {
        b.style.borderBottom = b.dataset.status === status ? '2px solid #2563EB' : '2px solid transparent';
        b.style.color = b.dataset.status === status ? '#2563EB' : '#64748B';
    });
    renderProcRows(procRawData);
}

function filterProcPlatform(plat) {
    procFilterPlatform = plat;
    renderProcRows(procRawData);
}

// ── 管理番号インライン保存 ──────────────────────────────
async function saveProcStockNo(id, value) {
    try {
        await apiFetch(`/api/procurements/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ stock_number: value }),
        });
    } catch (e) { console.error(e); }
}

// ── スクリーンショット表示 ──────────────────────────────
function viewProcScreenshot(id, title) {
    const overlay = document.getElementById('procSsOverlay');
    const img = document.getElementById('procSsImg');
    if (!overlay || !img) return;
    img.src = `/api/procurements/${id}/screenshot?t=${Date.now()}`;
    overlay.style.display = 'flex';
}

// ── 列設定モーダル ──────────────────────────────────────
function openProcColSettings() {
    const modal = document.getElementById('procColModal');
    if (!modal) return;
    const vis = getProcColVisible();
    let html = '';
    for (const col of PROC_ALL_COLUMNS) {
        html += `<label style="display:flex;align-items:center;gap:8px;padding:6px 0;cursor:pointer;">
            <input type="checkbox" data-col="${col.id}" ${vis[col.id] ? 'checked' : ''}>
            ${col.ja}
        </label>`;
    }
    document.getElementById('procColList').innerHTML = html;
    modal.style.display = 'flex';
}

function saveProcColSettings() {
    const vis = {};
    document.querySelectorAll('#procColList input[type=checkbox]').forEach(cb => {
        vis[cb.dataset.col] = cb.checked;
    });
    saveProcColVisible(vis);
    document.getElementById('procColModal').style.display = 'none';
    renderProcTableHeader();
    renderProcRows(procRawData);
}

// ── 初期化 ──────────────────────────────────────────────
async function initProcPage() {
    await fetchProcExchangeRate();
    renderProcTableHeader();
    await loadProcStats();
    await loadProcItems();
    updateProcBulkBar();
    const today = new Date().toISOString().slice(0, 10);
    const dateEl = document.getElementById('procDate');
    if (dateEl) dateEl.value = today;
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('procTable')) initProcPage();
});
```

- [ ] **Step 2: Verify syntax**

```bash
cd products/ebay-agent
node --check static/js/procurement-table.js
```

Expected: No output (no syntax errors)

- [ ] **Step 3: Commit**

```bash
git add static/js/procurement-table.js
git commit -m "feat: procurement-table.js core (columns, sort, KPI, render)"
```

---

### Task 10: `procurement-table.js` — add/edit, screenshot, bulk ops, URL-detect, scrape UI

**Files:**
- Modify: `static/js/procurement-table.js` (append new functions)

- [ ] **Step 1: Append add/edit/delete + screenshot functions**

Append to `static/js/procurement-table.js`:

```javascript
// ── 追加モーダル ──────────────────────────────────────────
function openProcAddModal() {
    const modal = document.getElementById('procModal');
    if (!modal) return;
    document.getElementById('procModalTitle').textContent = '仕入れ登録';
    document.getElementById('procEditId').value = '';
    clearProcForm();
    document.getElementById('procDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('procStatus').value = 'purchased';
    document.getElementById('procQty').value = '1';
    resetProcScreenshotUI();
    document.getElementById('procUrlStatus').textContent = '';
    modal.style.display = 'flex';
}

async function openProcEditModal(id) {
    const p = procRawData.find(x => x.id === id);
    if (!p) return;
    const modal = document.getElementById('procModal');
    if (!modal) return;
    document.getElementById('procModalTitle').textContent = '仕入れ編集';
    document.getElementById('procEditId').value = id;
    document.getElementById('procPlatform').value = p.platform || '';
    document.getElementById('procTitle').value = p.title || '';
    document.getElementById('procSku').value = p.sku || '';
    document.getElementById('procPrice').value = p.purchase_price_jpy || '';
    document.getElementById('procTax').value = p.consumption_tax_jpy || '';
    document.getElementById('procShipping').value = p.shipping_cost_jpy || '';
    document.getElementById('procOther').value = p.other_cost_jpy || '';
    document.getElementById('procDate').value = p.purchase_date ? p.purchase_date.slice(0,10) : '';
    document.getElementById('procRecvDate').value = p.received_date ? p.received_date.slice(0,10) : '';
    document.getElementById('procUrl').value = p.url || '';
    document.getElementById('procSellerId').value = p.seller_id || '';
    document.getElementById('procSellerUrl').value = p.seller_url || '';
    document.getElementById('procQty').value = p.quantity || 1;
    document.getElementById('procLocation').value = p.location || '';
    document.getElementById('procCondition').value = p.condition || '';
    document.getElementById('procStatus').value = p.status || 'purchased';
    document.getElementById('procCategory').value = p.category || '';
    document.getElementById('procStockNo').value = p.stock_number || '';
    document.getElementById('procEbayItemId').value = p.ebay_item_id || '';
    document.getElementById('procEbayOrderId').value = p.ebay_order_id || '';
    document.getElementById('procEbayPrice').value = p.ebay_price_usd || '';
    document.getElementById('procNotes').value = p.notes || '';
    document.getElementById('procUrlStatus').textContent = '';
    resetProcScreenshotUI();
    if (p.screenshot_path) {
        const preview = document.getElementById('procSsPreview');
        preview.innerHTML = `<img src="/api/procurements/${id}/screenshot?t=${Date.now()}" style="max-width:100%;max-height:120px;border-radius:4px;">`;
        preview.style.display = 'block';
        document.getElementById('procSsPrompt').textContent = '✓ 保存済み（新しい画像をドロップで上書き）';
    }
    modal.style.display = 'flex';
}

function closeProcModal() {
    const modal = document.getElementById('procModal');
    if (modal) modal.style.display = 'none';
    resetProcScreenshotUI();
}

function clearProcForm() {
    ['procPlatform','procTitle','procSku','procPrice','procTax','procShipping','procOther',
     'procDate','procRecvDate','procUrl','procSellerId','procSellerUrl','procQty','procLocation',
     'procCondition','procStatus','procCategory','procStockNo','procEbayItemId','procEbayOrderId',
     'procEbayPrice','procNotes'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.tagName === 'SELECT') el.selectedIndex = 0;
        else el.value = '';
    });
}

async function submitProcurement() {
    const editId = document.getElementById('procEditId').value;
    const body = {
        platform: document.getElementById('procPlatform').value,
        title: document.getElementById('procTitle').value,
        sku: document.getElementById('procSku').value,
        purchase_price_jpy: parseInt(document.getElementById('procPrice').value) || 0,
        consumption_tax_jpy: parseInt(document.getElementById('procTax').value) || 0,
        shipping_cost_jpy: parseInt(document.getElementById('procShipping').value) || 0,
        other_cost_jpy: parseInt(document.getElementById('procOther').value) || 0,
        purchase_date: document.getElementById('procDate').value,
        received_date: document.getElementById('procRecvDate').value,
        url: document.getElementById('procUrl').value,
        seller_id: document.getElementById('procSellerId').value,
        seller_url: document.getElementById('procSellerUrl').value,
        quantity: parseInt(document.getElementById('procQty').value) || 1,
        location: document.getElementById('procLocation').value,
        condition: document.getElementById('procCondition').value,
        status: document.getElementById('procStatus').value,
        category: document.getElementById('procCategory').value,
        stock_number: document.getElementById('procStockNo').value,
        ebay_item_id: document.getElementById('procEbayItemId').value,
        ebay_order_id: document.getElementById('procEbayOrderId').value,
        ebay_price_usd: parseFloat(document.getElementById('procEbayPrice').value) || 0,
        notes: document.getElementById('procNotes').value,
    };
    if (!body.title) { alert('商品名は必須です'); return; }

    try {
        const url = editId ? `/api/procurements/${editId}` : '/api/procurements';
        const method = editId ? 'PUT' : 'POST';
        const result = await apiFetch(url, { method, body: JSON.stringify(body) });
        const itemId = result.id || editId;
        if (_pendingProcSS && itemId) {
            await uploadProcScreenshot(itemId);
        }
        closeProcModal();
        await loadProcItems();
        await loadProcStats();
    } catch (e) {
        alert('保存に失敗しました: ' + (e.message || e));
    }
}

async function deleteProcurement() {
    const id = document.getElementById('procEditId').value;
    if (!id) return;
    if (!confirm('この仕入れ記録を削除しますか？')) return;
    try {
        await apiFetch(`/api/procurements/${id}`, { method: 'DELETE' });
        closeProcModal();
        await loadProcItems();
        await loadProcStats();
    } catch (e) { alert('削除に失敗しました'); }
}

// ── URL自動検出 ────────────────────────────────────────
function autoDetectProcUrl() {
    const url = document.getElementById('procUrl').value.trim();
    const statusEl = document.getElementById('procUrlStatus');
    if (!url) { statusEl.textContent = ''; return; }

    const platformMap = [
        { pattern: /jp\.mercari\.com|mercari\.com/, source: 'メルカリ' },
        { pattern: /page\.auctions\.yahoo\.co\.jp|auctions\.yahoo/, source: 'ヤフオク' },
        { pattern: /fril\.jp|rakuma/, source: 'ラクマ' },
        { pattern: /amazon\.co\.jp/, source: 'Amazon' },
        { pattern: /shopping\.yahoo\.co\.jp/, source: 'ヤフーショッピング' },
        { pattern: /rakuten\.co\.jp/, source: '楽天' },
        { pattern: /suruga-ya\.jp/, source: '駿河屋' },
        { pattern: /digimart\.net/, source: 'デジマート' },
        { pattern: /geo-online\.co\.jp/, source: 'GEO' },
        { pattern: /2ndstreet/, source: 'セカンドストリート' },
        { pattern: /mandarake\.co\.jp/, source: 'まんだらけ' },
        { pattern: /paypayfleamarket|yahoo.*flea/, source: 'Yahooフリマ' },
        { pattern: /netmall\.hardoff|ofmall/, source: 'ネットモール(OFFモール)' },
    ];

    let detected = null;
    for (const pm of platformMap) {
        if (pm.pattern.test(url)) { detected = pm.source; break; }
    }

    const sel = document.getElementById('procPlatform');
    if (detected && sel) {
        sel.value = detected;
        statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ ${detected} を検出</span>`;
    } else {
        statusEl.innerHTML = '<span style="color:#f59e0b;">自動判別できません</span>';
    }
}

// ── スクリーンショット D&D ──────────────────────────────
function resetProcScreenshotUI() {
    _pendingProcSS = null;
    const preview = document.getElementById('procSsPreview');
    const prompt = document.getElementById('procSsPrompt');
    const input = document.getElementById('procSsInput');
    if (preview) { preview.innerHTML = ''; preview.style.display = 'none'; }
    if (prompt) prompt.textContent = '📸 画像をドロップ or クリックして選択';
    if (input) input.value = '';
}

function handleProcSsDrop(event) {
    event.preventDefault();
    event.currentTarget.style.borderColor = 'var(--border)';
    const file = event.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) setProcSsPreview(file);
}

function handleProcSsSelect(event) {
    const file = event.target.files[0];
    if (file) setProcSsPreview(file);
}

function setProcSsPreview(file) {
    _pendingProcSS = file;
    const preview = document.getElementById('procSsPreview');
    const prompt = document.getElementById('procSsPrompt');
    const reader = new FileReader();
    reader.onload = e => {
        preview.innerHTML = `<img src="${e.target.result}" style="max-width:100%;max-height:120px;border-radius:4px;">`;
        preview.style.display = 'block';
        if (prompt) prompt.textContent = '✓ アップロード待機中';
    };
    reader.readAsDataURL(file);
}

async function uploadProcScreenshot(itemId) {
    if (!_pendingProcSS) return;
    try {
        const formData = new FormData();
        formData.append('file', _pendingProcSS, _pendingProcSS.name || 'screenshot.png');
        const resp = await fetch(`/api/procurements/${itemId}/screenshot`, {
            method: 'POST',
            body: formData,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        _pendingProcSS = null;
    } catch (e) {
        console.error('スクリーンショットアップロード失敗:', e);
    }
}

// ── 一括削除 ────────────────────────────────────────────
function toggleSelectAllProc(checked) {
    document.querySelectorAll('.proc-row-check').forEach(cb => { cb.checked = checked; });
    updateProcBulkBar();
}

function getProcSelectedIds() {
    return Array.from(document.querySelectorAll('.proc-row-check:checked'))
        .map(cb => parseInt(cb.dataset.id));
}

function updateProcBulkBar() {
    const ids = getProcSelectedIds();
    const bar = document.getElementById('procBulkBar');
    const cnt = document.getElementById('procBulkCount');
    if (!bar) return;
    if (ids.length > 0) {
        bar.style.display = 'flex';
        if (cnt) cnt.textContent = `${ids.length}件選択中`;
    } else {
        bar.style.display = 'none';
    }
}

async function bulkDeleteProcSelected() {
    const ids = getProcSelectedIds();
    if (!ids.length) return;
    if (!confirm(`${ids.length}件の仕入れ記録を削除しますか？`)) return;
    try {
        await apiFetch('/api/procurements/bulk-delete-ids', {
            method: 'POST',
            body: JSON.stringify({ ids }),
        });
        await loadProcItems();
        await loadProcStats();
        updateProcBulkBar();
    } catch (e) { alert('一括削除に失敗しました'); }
}

// ── 一括インポート ──────────────────────────────────────
function openProcBulkImport() {
    const modal = document.getElementById('procBulkModal');
    if (!modal) return;
    document.getElementById('procBulkData').value = '';
    document.getElementById('procBulkStatus').textContent = '';
    updateProcBulkHelp();
    modal.style.display = 'flex';
}

function closeProcBulkImport() {
    const modal = document.getElementById('procBulkModal');
    if (modal) modal.style.display = 'none';
}

function updateProcBulkHelp() {
    const platform = document.getElementById('procBulkPlatform').value;
    const helpEl = document.getElementById('procBulkHelp');
    const helpMap = {
        'ヤフオク': `<b>auctions.yahoo.co.jp/my/won</b> を開いて落札一覧をコピー→貼り付け。商品名・落札価格・日付を自動抽出します。`,
        'メルカリ': `<b>mercari.com/mypage/purchases/</b> を開いて購入履歴をコピー→貼り付け。<br>または手動入力: 1行1商品、タブ区切りで 商品名TAB価格TAB日付`,
        'ラクマ': `購入履歴ページからコピー→貼り付け。または手動入力: 商品名TAB価格TAB日付`,
        'その他': `1行1商品。タブ区切り: 商品名TAB価格TAB日付<br>例: Pioneer A-717&nbsp;&nbsp;8500&nbsp;&nbsp;2026-03-08`,
    };
    if (helpEl) helpEl.innerHTML = helpMap[platform] || helpMap['その他'];
}

function parseProcBulkData(platform, raw) {
    const rows = [];
    const lines = raw.split('\n').map(l => l.trim()).filter(l => l);
    for (const line of lines) {
        const parts = line.split(/\t/);
        if (parts.length >= 2) {
            const title = parts[0].trim();
            const price = parseInt(parts[1].replace(/[¥,円]/g, '')) || 0;
            const date = parts[2] ? parts[2].trim() : '';
            if (title && price) rows.push({ title, price, date, source: platform });
        }
    }
    return rows;
}

async function runProcBulkImport() {
    const platform = document.getElementById('procBulkPlatform').value;
    const raw = document.getElementById('procBulkData').value;
    const statusEl = document.getElementById('procBulkStatus');
    if (!raw.trim()) { statusEl.textContent = 'データを入力してください'; return; }

    const rows = parseProcBulkData(platform, raw);
    if (!rows.length) { statusEl.textContent = '取込可能な行が見つかりませんでした'; return; }

    statusEl.textContent = `${rows.length}件を登録中...`;
    try {
        const result = await apiFetch('/api/procurements/bulk-import', {
            method: 'POST',
            body: JSON.stringify({ rows, platform }),
        });
        statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ ${result.created}件登録、${result.skipped}件スキップ</span>`;
        await loadProcItems();
        await loadProcStats();
    } catch (e) {
        statusEl.innerHTML = `<span style="color:#EF4444;">エラー: ${e.message || e}</span>`;
    }
}

// ── スクレイピングUI ────────────────────────────────────
let _procScrapeJobId = null;
let _procScrapePoller2 = null;

function openProcScrapeModal(platform) {
    const modal = document.getElementById('procScrapeModal');
    if (!modal) return;
    document.getElementById('procScrapePlatform').textContent = platform;
    document.getElementById('procScrapeModal').dataset.platform = platform;
    document.getElementById('procScrapeStatus').textContent = '';
    document.getElementById('procScrapeProgress').style.display = 'none';
    document.getElementById('procScrapeImportBtn').style.display = 'none';
    _procScrapeJobId = null;
    modal.style.display = 'flex';
}

function closeProcScrapeModal() {
    if (_procScrapePoller2) clearInterval(_procScrapePoller2);
    const modal = document.getElementById('procScrapeModal');
    if (modal) modal.style.display = 'none';
}

async function startProcScrape() {
    const modal = document.getElementById('procScrapeModal');
    const platform = modal ? modal.dataset.platform : '';
    const platformEndpointMap = {
        'メルカリ': 'mercari',
        'ヤフオク': 'yahoo',
        'Yahooフリマ': 'yahoo-flea',
        'ラクマ': 'rakuma',
        'ネットモール(OFFモール)': 'hardoff',
        '駿河屋': 'surugaya',
    };
    const endpoint = platformEndpointMap[platform];
    if (!endpoint) { alert('対応していないプラットフォームです'); return; }

    const statusEl = document.getElementById('procScrapeStatus');
    const progressEl = document.getElementById('procScrapeProgress');
    statusEl.textContent = 'スクレイプ開始中...';
    progressEl.style.display = 'block';

    try {
        const result = await apiFetch(`/api/procurements/scrape/${endpoint}`, { method: 'POST' });
        _procScrapeJobId = result.job_id;
        statusEl.textContent = 'スクレイプ実行中...';
        pollProcScrapeStatus(endpoint);
    } catch (e) {
        statusEl.innerHTML = `<span style="color:#EF4444;">エラー: ${e.message || e}</span>`;
    }
}

function pollProcScrapeStatus(endpoint) {
    if (_procScrapePoller2) clearInterval(_procScrapePoller2);
    _procScrapePoller2 = setInterval(async () => {
        try {
            const job = await apiFetch(`/api/stock/scrape/status/${_procScrapeJobId}`);
            const statusEl = document.getElementById('procScrapeStatus');
            const msg = job.message || job.status;
            if (job.status === 'login_required') {
                clearInterval(_procScrapePoller2);
                statusEl.innerHTML = `<span style="color:#f59e0b;">🔐 ログインが必要です。ローカルMacで再ログイン後、cookie同期してください。</span>`;
            } else if (job.status === 'done') {
                clearInterval(_procScrapePoller2);
                const cnt = (job.results || []).length;
                statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ ${cnt}件取得完了</span>`;
                document.getElementById('procScrapeImportBtn').style.display = 'inline-block';
                document.getElementById('procScrapeImportBtn').onclick = () => importProcScrapeResults(endpoint);
            } else if (job.status === 'error') {
                clearInterval(_procScrapePoller2);
                statusEl.innerHTML = `<span style="color:#EF4444;">エラー: ${job.error || msg}</span>`;
            } else {
                const cur = job.current || 0;
                const tot = job.total || 0;
                statusEl.textContent = tot > 0 ? `${msg} (${cur}/${tot})` : msg;
            }
        } catch (e) { console.error('poll error:', e); }
    }, 2000);
}

async function importProcScrapeResults(endpoint) {
    if (!_procScrapeJobId) return;
    const statusEl = document.getElementById('procScrapeStatus');
    statusEl.textContent = 'インポート中...';
    try {
        const result = await apiFetch(`/api/procurements/scrape/${endpoint}/import/${_procScrapeJobId}`, { method: 'POST' });
        statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ ${result.created}件登録、${result.skipped}件スキップ</span>`;
        document.getElementById('procScrapeImportBtn').style.display = 'none';
        await loadProcItems();
        await loadProcStats();
    } catch (e) {
        statusEl.innerHTML = `<span style="color:#EF4444;">エラー: ${e.message || e}</span>`;
    }
}

// ── auto-SKU ────────────────────────────────────────────
async function procAutoSku() {
    if (!confirm('SKUなしの仕入れ記録に対してeBay出品とのマッチングを実行しますか？')) return;
    try {
        const result = await apiFetch('/api/procurements/auto-sku', { method: 'POST' });
        alert(`完了: ${result.assigned}件マッチ、${result.skipped}件スキップ`);
        await loadProcItems();
    } catch (e) { alert('エラー: ' + (e.message || e)); }
}
```

- [ ] **Step 2: Verify syntax**

```bash
cd products/ebay-agent
node --check static/js/procurement-table.js
```

Expected: No output

- [ ] **Step 3: Commit**

```bash
git add static/js/procurement-table.js
git commit -m "feat: procurement-table.js interactions (add/edit/scrape/bulk)"
```

---

### Task 11: Replace `sourcing.html` card UI with table UI

**Files:**
- Modify: `templates/pages/sourcing.html`

The existing `sourcing.html` has inline JS (~250 lines) and card-based HTML. Replace the `panelRecords` div content and the `<script>` block with table-based markup that loads `procurement-table.js`.

- [ ] **Step 1: Replace `panelRecords` content in `sourcing.html`**

Find the block `<div id="panelRecords">` through `</div><!-- /panelRecords -->` (approximately lines 243–494) and replace with:

```html
<div id="panelRecords">

<!-- KPIバー -->
<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px;">
    <div class="proc-kpi-card">
        <div class="proc-kpi-label">仕入件数</div>
        <div class="proc-kpi-val" id="procKpiTotal">--</div>
    </div>
    <div class="proc-kpi-card">
        <div class="proc-kpi-label">仕入総額</div>
        <div class="proc-kpi-val" id="procKpiCost">--</div>
    </div>
    <div class="proc-kpi-card">
        <div class="proc-kpi-label">消費税合計</div>
        <div class="proc-kpi-val" id="procKpiTax">--</div>
    </div>
    <div class="proc-kpi-card">
        <div class="proc-kpi-label">出品中</div>
        <div class="proc-kpi-val" id="procKpiListed">--</div>
    </div>
    <div class="proc-kpi-card">
        <div class="proc-kpi-label">販売済+発送済</div>
        <div class="proc-kpi-val" id="procKpiSold">--</div>
    </div>
</div>

<!-- ツールバー -->
<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
    <!-- ステータスフィルタ -->
    <div style="display:flex;gap:0;border:1px solid var(--border);border-radius:6px;overflow:hidden;">
        <button class="proc-status-tab" data-status="all"       onclick="filterProcStatus('all')"       style="padding:5px 10px;font-size:12px;border:none;border-right:1px solid var(--border);cursor:pointer;background:#2563EB;color:white;">全て</button>
        <button class="proc-status-tab" data-status="purchased" onclick="filterProcStatus('purchased')" style="padding:5px 10px;font-size:12px;border:none;border-right:1px solid var(--border);cursor:pointer;background:white;color:#374151;">購入済</button>
        <button class="proc-status-tab" data-status="received"  onclick="filterProcStatus('received')"  style="padding:5px 10px;font-size:12px;border:none;border-right:1px solid var(--border);cursor:pointer;background:white;color:#374151;">入荷済</button>
        <button class="proc-status-tab" data-status="listed"    onclick="filterProcStatus('listed')"    style="padding:5px 10px;font-size:12px;border:none;border-right:1px solid var(--border);cursor:pointer;background:white;color:#374151;">出品中</button>
        <button class="proc-status-tab" data-status="sold"      onclick="filterProcStatus('sold')"      style="padding:5px 10px;font-size:12px;border:none;border-right:1px solid var(--border);cursor:pointer;background:white;color:#374151;">販売済</button>
        <button class="proc-status-tab" data-status="shipped"   onclick="filterProcStatus('shipped')"   style="padding:5px 10px;font-size:12px;border:none;cursor:pointer;background:white;color:#374151;">発送済</button>
    </div>
    <!-- 検索 -->
    <input id="procSearch" placeholder="検索..." style="padding:5px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:180px;"
           oninput="procSearchQuery=this.value;renderProcRows(procRawData)">
    <div style="flex:1;"></div>
    <!-- ボタン群 -->
    <button onclick="openProcColSettings()" style="padding:5px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;cursor:pointer;background:white;">列設定 ▼</button>
    <button onclick="openProcAddModal()" style="padding:5px 12px;border:none;border-radius:6px;font-size:13px;cursor:pointer;background:#2563EB;color:white;">+ 仕入れ登録</button>
    <div style="position:relative;display:inline-block;">
        <button onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'"
                style="padding:5px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;cursor:pointer;background:white;">スクレイプ ▼</button>
        <div style="display:none;position:absolute;right:0;top:100%;background:white;border:1px solid var(--border);border-radius:6px;min-width:160px;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
            <button onclick="openProcScrapeModal('メルカリ')"           style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">メルカリ</button>
            <button onclick="openProcScrapeModal('ヤフオク')"           style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">ヤフオク</button>
            <button onclick="openProcScrapeModal('Yahooフリマ')"        style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">Yahooフリマ</button>
            <button onclick="openProcScrapeModal('ラクマ')"             style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">ラクマ</button>
            <button onclick="openProcScrapeModal('ネットモール(OFFモール)')" style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">ハードオフ</button>
            <button onclick="openProcScrapeModal('駿河屋')"             style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">駿河屋</button>
            <hr style="margin:4px 0;">
            <button onclick="openProcBulkImport()"                       style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">一括インポート (TSV)</button>
            <button onclick="procAutoSku()"                              style="display:block;width:100%;text-align:left;padding:8px 14px;border:none;background:none;cursor:pointer;font-size:13px;">Auto-SKU</button>
        </div>
    </div>
</div>

<!-- バルクバー -->
<div id="procBulkBar" style="display:none;align-items:center;gap:8px;padding:8px 12px;background:#FEF3C7;border-radius:6px;margin-bottom:8px;">
    <span id="procBulkCount" style="font-size:13px;font-weight:600;"></span>
    <button onclick="bulkDeleteProcSelected()" style="padding:4px 12px;border:none;border-radius:4px;background:#EF4444;color:white;font-size:12px;cursor:pointer;">削除</button>
    <button onclick="toggleSelectAllProc(false);updateProcBulkBar()" style="padding:4px 10px;border:1px solid var(--border);border-radius:4px;background:white;font-size:12px;cursor:pointer;">選択解除</button>
</div>

<!-- テーブル -->
<div style="overflow-x:auto;">
<table id="procTable" style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead style="background:#F8FAFC;border-bottom:2px solid var(--border);">
        <tr></tr>
    </thead>
    <tbody id="procBody">
        <tr><td colspan="10" style="text-align:center;padding:24px;color:#94A3B8;">読み込み中...</td></tr>
    </tbody>
</table>
</div>

<!-- ── 追加/編集モーダル ── -->
<div id="procModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;align-items:center;justify-content:center;">
    <div style="background:white;border-radius:12px;padding:24px;width:700px;max-width:95vw;max-height:90vh;overflow-y:auto;position:relative;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <h3 id="procModalTitle" style="margin:0;font-size:16px;">仕入れ登録</h3>
            <button onclick="closeProcModal()" style="background:none;border:none;font-size:20px;cursor:pointer;color:#94A3B8;">×</button>
        </div>
        <input type="hidden" id="procEditId">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
                <label style="font-size:12px;font-weight:600;">仕入先</label>
                <select id="procPlatform" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
                    <option value="Amazon">Amazon</option>
                    <option value="メルカリ">メルカリ</option>
                    <option value="メルカリShops">メルカリShops</option>
                    <option value="ラクマ">ラクマ</option>
                    <option value="ヤフオク">ヤフオク</option>
                    <option value="ヤフーショッピング">ヤフーショッピング</option>
                    <option value="楽天">楽天</option>
                    <option value="Yahooフリマ">Yahooフリマ</option>
                    <option value="駿河屋">駿河屋</option>
                    <option value="GEO">GEO</option>
                    <option value="デジマート">デジマート</option>
                    <option value="トレファク">トレファク</option>
                    <option value="まんだらけ">まんだらけ</option>
                    <option value="セカンドストリート">セカンドストリート</option>
                    <option value="ネットモール(OFFモール)">ネットモール(OFFモール)</option>
                    <option value="その他">その他</option>
                </select>
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">ステータス</label>
                <select id="procStatus" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
                    <option value="purchased">購入済</option>
                    <option value="received">入荷済</option>
                    <option value="listed">出品中</option>
                    <option value="sold">販売済</option>
                    <option value="shipped">発送済</option>
                    <option value="returned">返品</option>
                    <option value="cancelled">キャンセル</option>
                </select>
            </div>
            <div style="grid-column:1/-1;">
                <label style="font-size:12px;font-weight:600;">商品名 *</label>
                <input id="procTitle" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="商品名">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">SKU</label>
                <input id="procSku" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="eBay SKU（任意）">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">管理番号</label>
                <input id="procStockNo" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="P-001">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">仕入価格（税抜）</label>
                <input id="procPrice" type="number" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="¥">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">消費税</label>
                <input id="procTax" type="number" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="¥" value="0">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">国内送料</label>
                <input id="procShipping" type="number" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="¥" value="0">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">その他費用</label>
                <input id="procOther" type="number" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="¥" value="0">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">購入日</label>
                <input id="procDate" type="date" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">受取日</label>
                <input id="procRecvDate" type="date" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div style="grid-column:1/-1;">
                <label style="font-size:12px;font-weight:600;">仕入先URL</label>
                <div style="display:flex;gap:6px;">
                    <input id="procUrl" style="flex:1;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="https://..." oninput="autoDetectProcUrl()">
                    <button onclick="autoDetectProcUrl()" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;cursor:pointer;background:white;white-space:nowrap;">自動取得</button>
                </div>
                <div id="procUrlStatus" style="font-size:11px;margin-top:3px;"></div>
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">出品者ID</label>
                <input id="procSellerId" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">出品者URL</label>
                <input id="procSellerUrl" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">数量</label>
                <input id="procQty" type="number" value="1" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">保管場所</label>
                <input id="procLocation" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="例: 棚A-3">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">状態</label>
                <select id="procCondition" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
                    <option value="">未設定</option>
                    <option value="新品">新品</option>
                    <option value="中古A">中古A</option>
                    <option value="中古B">中古B</option>
                    <option value="ジャンク">ジャンク</option>
                </select>
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">古物区分</label>
                <select id="procCategory" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
                    <option value="">未設定</option>
                    <option value="美術品類">美術品類</option>
                    <option value="衣類">衣類</option>
                    <option value="時計・宝飾品類">時計・宝飾品類</option>
                    <option value="自動車・自動二輪類">自動車・自動二輪類</option>
                    <option value="自転車類">自転車類</option>
                    <option value="写真機類">写真機類</option>
                    <option value="事務機器類">事務機器類</option>
                    <option value="機械工具類">機械工具類</option>
                    <option value="道具類">道具類</option>
                    <option value="皮革・ゴム製品類">皮革・ゴム製品類</option>
                    <option value="書籍類">書籍類</option>
                    <option value="金券類">金券類</option>
                    <option value="その他">その他</option>
                </select>
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">eBay Item ID</label>
                <input id="procEbayItemId" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">eBay Order ID</label>
                <input id="procEbayOrderId" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div>
                <label style="font-size:12px;font-weight:600;">eBay 販売額 (USD)</label>
                <input id="procEbayPrice" type="number" step="0.01" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;" placeholder="0.00">
            </div>
            <div style="grid-column:1/-1;">
                <label style="font-size:12px;font-weight:600;">メモ</label>
                <input id="procNotes" style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
            </div>
            <div style="grid-column:1/-1;">
                <label style="font-size:12px;font-weight:600;">スクリーンショット</label>
                <div id="procSsZone"
                     ondrop="handleProcSsDrop(event)"
                     ondragover="event.preventDefault();this.style.borderColor='#2563EB';"
                     ondragleave="this.style.borderColor='var(--border)';"
                     onclick="document.getElementById('procSsInput').click()"
                     style="border:2px dashed var(--border);border-radius:8px;padding:12px;text-align:center;cursor:pointer;">
                    <div id="procSsPrompt" style="color:#94A3B8;font-size:12px;">📸 画像をドロップ or クリックして選択</div>
                    <div id="procSsPreview" style="display:none;"></div>
                </div>
                <input type="file" id="procSsInput" accept="image/*" style="display:none;" onchange="handleProcSsSelect(event)">
            </div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:16px;">
            <button onclick="deleteProcurement()" style="padding:6px 14px;border:1px solid #FECACA;border-radius:6px;background:white;color:#EF4444;font-size:13px;cursor:pointer;">削除</button>
            <div style="display:flex;gap:8px;">
                <button onclick="closeProcModal()" style="padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:white;font-size:13px;cursor:pointer;">キャンセル</button>
                <button onclick="submitProcurement()" style="padding:6px 16px;border:none;border-radius:6px;background:#2563EB;color:white;font-size:13px;cursor:pointer;">保存</button>
            </div>
        </div>
    </div>
</div>

<!-- ── 列設定モーダル ── -->
<div id="procColModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;align-items:center;justify-content:center;">
    <div style="background:white;border-radius:12px;padding:24px;width:320px;max-height:80vh;overflow-y:auto;">
        <h3 style="margin:0 0 12px;font-size:15px;">表示列の設定</h3>
        <div id="procColList"></div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;">
            <button onclick="document.getElementById('procColModal').style.display='none'" style="padding:6px 12px;border:1px solid var(--border);border-radius:6px;background:white;cursor:pointer;">キャンセル</button>
            <button onclick="saveProcColSettings()" style="padding:6px 14px;border:none;border-radius:6px;background:#2563EB;color:white;cursor:pointer;">保存</button>
        </div>
    </div>
</div>

<!-- ── スクレイプモーダル ── -->
<div id="procScrapeModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;align-items:center;justify-content:center;">
    <div style="background:white;border-radius:12px;padding:24px;width:400px;">
        <h3 style="margin:0 0 12px;font-size:15px;"><span id="procScrapePlatform"></span> スクレイプ</h3>
        <div id="procScrapeProgress" style="display:none;margin-bottom:12px;">
            <div style="height:4px;background:#E2E8F0;border-radius:2px;overflow:hidden;">
                <div style="height:100%;background:#2563EB;width:100%;animation:pulse 1.5s infinite;"></div>
            </div>
        </div>
        <div id="procScrapeStatus" style="font-size:13px;min-height:24px;margin-bottom:12px;"></div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <button onclick="closeProcScrapeModal()" style="padding:6px 12px;border:1px solid var(--border);border-radius:6px;background:white;cursor:pointer;font-size:13px;">閉じる</button>
            <div style="display:flex;gap:8px;">
                <button id="procScrapeImportBtn" style="display:none;padding:6px 14px;border:none;border-radius:6px;background:#10B981;color:white;cursor:pointer;font-size:13px;">インポート</button>
                <button onclick="startProcScrape()" style="padding:6px 14px;border:none;border-radius:6px;background:#2563EB;color:white;cursor:pointer;font-size:13px;">開始</button>
            </div>
        </div>
    </div>
</div>

<!-- ── 一括インポートモーダル ── -->
<div id="procBulkModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;align-items:center;justify-content:center;">
    <div style="background:white;border-radius:12px;padding:24px;width:560px;max-height:80vh;overflow-y:auto;">
        <h3 style="margin:0 0 12px;font-size:15px;">一括インポート (TSV)</h3>
        <div style="margin-bottom:12px;">
            <label style="font-size:12px;font-weight:600;">仕入先</label>
            <select id="procBulkPlatform" onchange="updateProcBulkHelp()" style="padding:5px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
                <option value="ヤフオク">ヤフオク</option>
                <option value="メルカリ">メルカリ</option>
                <option value="ラクマ">ラクマ</option>
                <option value="その他">その他</option>
            </select>
        </div>
        <div id="procBulkHelp" style="font-size:12px;color:#64748B;background:#F8FAFC;padding:10px;border-radius:6px;margin-bottom:12px;"></div>
        <textarea id="procBulkData" rows="8" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:8px;font-size:12px;font-family:monospace;" placeholder="ここに購入履歴テキストを貼り付けてください..."></textarea>
        <div id="procBulkStatus" style="font-size:13px;margin-top:8px;min-height:20px;"></div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;">
            <button onclick="closeProcBulkImport()" style="padding:6px 12px;border:1px solid var(--border);border-radius:6px;background:white;cursor:pointer;">キャンセル</button>
            <button onclick="runProcBulkImport()" style="padding:6px 14px;border:none;border-radius:6px;background:#2563EB;color:white;cursor:pointer;">インポート</button>
        </div>
    </div>
</div>

<!-- ── スクリーンショット表示オーバーレイ ── -->
<div id="procSsOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:2000;align-items:center;justify-content:center;" onclick="this.style.display='none'">
    <img id="procSsImg" src="" style="max-width:90vw;max-height:90vh;border-radius:8px;">
</div>

</div><!-- /panelRecords -->
```

- [ ] **Step 2: Replace the `<script>` block in `sourcing.html`**

Find `{% block scripts %}` through the closing `{% endblock %}` (approximately lines 502–800) and replace with:

```html
{% block scripts %}
<script src="/static/js/procurement-table.js"></script>
<script>
function switchTab(tab) {
    const isRec = tab === 'records';
    document.getElementById('panelRecords').style.display = isRec ? '' : 'none';
    document.getElementById('panelLedger').style.display  = isRec ? 'none' : '';
    document.getElementById('tabRecords').style.color = isRec ? '#2563EB' : '#64748B';
    document.getElementById('tabRecords').style.borderBottom = isRec ? '2px solid #2563EB' : '2px solid transparent';
    document.getElementById('tabLedger').style.color  = isRec ? '#64748B' : '#2563EB';
    document.getElementById('tabLedger').style.borderBottom  = isRec ? '2px solid transparent' : '2px solid #2563EB';
    if (!isRec) { loadStats(); loadItems(); }
}
</script>
{% endblock %}
```

- [ ] **Step 3: Start dev server and smoke test**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/python main.py &
```

Open `http://localhost:8002/sourcing` and verify:
- Table renders with column headers
- KPI bar shows numbers (not `--`)
- "+ 仕入れ登録" button opens modal
- Sort arrow appears on click

Kill the dev server: `pkill -f "python main.py"`

- [ ] **Step 4: Run tests (backend sanity)**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add templates/pages/sourcing.html
git commit -m "feat: sourcing.html — table UI + procurement-table.js integration"
```

---

### Task 12: Hide 在庫台帳 tab + delete dead code

**Files:**
- Modify: `templates/pages/sourcing.html` (hide 在庫台帳 tab)
- Delete: `templates/pages/_sourcing_content.html`
- Delete: `templates/pages/procurement.html`

- [ ] **Step 1: Hide 在庫台帳 tab in `sourcing.html`**

Find the tab button for 在庫台帳 (around line 240):

```html
    <button id="tabLedger"  onclick="switchTab('ledger')" ...>在庫台帳</button>
```

Replace with:

```html
    <button id="tabLedger"  onclick="switchTab('ledger')" style="display:none;">在庫台帳</button>
```

- [ ] **Step 2: Delete dead code files**

```bash
git rm products/ebay-agent/templates/pages/_sourcing_content.html
git rm products/ebay-agent/templates/pages/procurement.html
```

- [ ] **Step 3: Verify `/sourcing` still loads**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/python -c "
import main
from fastapi.testclient import TestClient
client = TestClient(main.app)
r = client.get('/sourcing')
print('status:', r.status_code)
assert r.status_code == 200, r.text[:200]
print('OK')
"
```

Expected: `status: 200` + `OK`

- [ ] **Step 4: Verify `/procurement` redirect still works**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/python -c "
import main
from fastapi.testclient import TestClient
client = TestClient(main.app, follow_redirects=False)
r = client.get('/procurement')
print('status:', r.status_code, r.headers.get('location'))
assert r.status_code == 301
print('OK')
"
```

Expected: `status: 301 /sourcing`

- [ ] **Step 5: Run all tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add templates/pages/sourcing.html
git commit -m "feat: hide 在庫台帳 tab + delete dead code (_sourcing_content, procurement.html)"
```

---

### Task 13: Push to VPS + final smoke test

- [ ] **Step 1: Push**

```bash
git push claude-workspace master
```

- [ ] **Step 2: Deploy on VPS**

```bash
ssh vps "cd /opt/apps/claude-workspace && git pull origin master && docker compose -f products/ebay-agent/docker-compose.yml up -d --build"
```

- [ ] **Step 3: Verify /sourcing loads on VPS**

```bash
ssh vps "curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/sourcing"
```

Expected: `200`

- [ ] **Step 4: Verify /api/procurements/stats on VPS**

```bash
ssh vps "curl -s http://localhost:8002/api/procurements/stats | python3 -m json.tool"
```

Expected: JSON with `total`, `listed`, etc.
