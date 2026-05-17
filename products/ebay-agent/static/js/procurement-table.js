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
