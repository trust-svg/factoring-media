/* procurement-table.js — 仕入れ記録テーブルUI */

// ── ソート状態 ──────────────────────────────────────────
let procSortCol = 'purchase_date';
let procSortDir = 'desc';
let procRawData = [];
let procFilterStatus = 'all';
let procFilterPlatform = 'all';
let procSearchQuery = '';
let procDateFrom = '';
let procDateTo = '';
let _procUsdJpy = 149;
let _pendingProcSS = null; // pending screenshot file
let _procScrapePoller = null;

// ── カラム定義 ──────────────────────────────────────────
const PROC_ALL_COLUMNS = [
    { id: 'stock_no',    label: 'No.',       ja: '管理番号',   sortKey: 'stock_number' },
    { id: 'title',       label: 'Product',   ja: '商品名',     sortKey: 'title' },
    { id: 'sku',         label: 'SKU',       ja: 'SKU',        sortKey: 'sku' },
    { id: 'cost',        label: 'Cost',      ja: '原価',       sortKey: 'total_cost_jpy' },
    { id: 'tax',         label: 'Tax',       ja: '消費税',     sortKey: 'consumption_tax_jpy' },
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
    { id: 'sale_price',  label: '$Sold',     ja: '売上(USD)',  sortKey: null },
    { id: 'profit',      label: '利益',      ja: '利益(JPY)',  sortKey: null },
    { id: 'refund',      label: '還付込',    ja: '還付込利益', sortKey: null },
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
        case 'title': {
            const thumb = p.image_url
                ? `<img src="${esc(p.image_url)}" style="width:28px;height:28px;object-fit:cover;border-radius:3px;vertical-align:middle;margin-right:6px;" onerror="this.style.display='none'">`
                : p.screenshot_path
                    ? `<img src="/api/procurements/${encodeURIComponent(p.id)}/screenshot" style="width:28px;height:28px;object-fit:cover;border-radius:3px;vertical-align:middle;margin-right:6px;" onerror="this.style.display='none'">`
                    : '';
            return `<td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(p.title)}">${thumb}${esc(p.title)}</td>`;
        }
        case 'sku':
            return `<td style="font-family:monospace;font-size:11px;color:#94A3B8;">${esc(p.sku || '-')}</td>`;
        case 'cost': {
            const details = [];
            if (p.purchase_price_jpy) details.push(`本体¥${p.purchase_price_jpy.toLocaleString()}`);
            if (p.consumption_tax_jpy) details.push(`税¥${p.consumption_tax_jpy.toLocaleString()}`);
            if (p.shipping_cost_jpy) details.push(`送¥${p.shipping_cost_jpy.toLocaleString()}`);
            const sub = details.length > 1
                ? `<br><span style="font-size:10px;color:#94A3B8;">${details.join(' + ')}</span>`
                : '';
            return `<td class="num" style="font-weight:600;">¥${(p.total_cost_jpy || 0).toLocaleString()}${sub}</td>`;
        }
        case 'tax':
            return `<td class="num" style="font-size:12px;color:#64748B;">${p.consumption_tax_jpy ? '¥' + p.consumption_tax_jpy.toLocaleString() : '-'}</td>`;
        case 'date':
            return `<td style="white-space:nowrap;font-size:12px;">${p.purchase_date ? p.purchase_date.slice(0,10) : '-'}</td>`;
        case 'platform': {
            const badge = platBadgeProc(p.platform);
            const srcLink = p.url
                ? `<a href="${esc(p.url)}" target="_blank" style="color:#94A3B8;font-size:10px;text-decoration:none;vertical-align:middle;margin-left:3px;">↗</a>`
                : '';
            const seller = p.seller_id
                ? (p.seller_url
                    ? `<br><a href="${esc(p.seller_url)}" target="_blank" style="color:#94A3B8;font-size:10px;text-decoration:none;">${esc(p.seller_id)} ↗</a>`
                    : `<br><span style="font-size:10px;color:#94A3B8;">${esc(p.seller_id)}</span>`)
                : '';
            return `<td>${badge}${srcLink}${seller}</td>`;
        }
        case 'status':
            return `<td>${buildProcStatusBadge(p.status)}</td>`;
        case 'location': {
            const locVal = p.location || '';
            const locOpts = ['', '自宅', 'オークレボ'].map(v =>
                `<option value="${v}" ${locVal === v ? 'selected' : ''}>${v || '未設定'}</option>`
            ).join('');
            return `<td>
                <select style="font-size:11px;padding:2px 4px;border:1px solid transparent;border-radius:4px;background:transparent;color:#64748B;cursor:pointer;"
                    onfocus="this.style.borderColor='var(--brand-500)'"
                    onblur="this.style.borderColor='transparent'"
                    onchange="event.stopPropagation();saveProcLocation(${p.id},this.value)"
                    onclick="event.stopPropagation()">
                    ${locOpts}
                </select>
            </td>`;
        }
        case 'ebay_id': {
            const linked = p.ebay_order_id
                ? `<span title="Order: ${esc(p.ebay_order_id)}" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22C55E;margin-right:4px;vertical-align:middle;"></span>`
                : p.ebay_item_id
                    ? `<span title="出品済・未売上" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#F97316;margin-right:4px;vertical-align:middle;"></span>`
                    : '';
            return p.ebay_item_id
                ? `<td>${linked}<a href="https://www.ebay.com/itm/${encodeURIComponent(p.ebay_item_id)}" target="_blank" style="font-size:11px;color:#2563EB;">${esc(p.ebay_item_id)}</a></td>`
                : `<td>${linked}<span style="color:#CBD5E1;font-size:11px;">—</span></td>`;
        }
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
        case 'sale_price':
            return p.sale && p.sale.sale_price_usd
                ? `<td class="num" style="font-size:12px;color:#10B981;font-weight:600;">$${Number(p.sale.sale_price_usd).toFixed(2)}</td>`
                : `<td style="color:#CBD5E1;font-size:11px;text-align:right;">-</td>`;
        case 'profit':
            return p.sale && p.sale.net_profit_jpy != null
                ? `<td class="num" style="font-size:12px;font-weight:700;color:${p.sale.net_profit_jpy >= 0 ? '#10B981' : '#EF4444'};">¥${p.sale.net_profit_jpy.toLocaleString()}</td>`
                : `<td style="color:#CBD5E1;font-size:11px;text-align:right;">-</td>`;
        case 'refund': {
            if (p.sale && p.sale.net_profit_jpy != null) {
                const r = p.sale.net_profit_jpy + (p.consumption_tax_jpy || 0);
                return `<td class="num" style="font-size:12px;font-weight:700;color:${r >= 0 ? '#7C3AED' : '#EF4444'};">¥${r.toLocaleString()}</td>`;
            }
            return `<td style="color:#CBD5E1;font-size:11px;text-align:right;">-</td>`;
        }
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
    if (procDateFrom) filtered = filtered.filter(p =>
        p.purchase_date && p.purchase_date.slice(0, 10) >= procDateFrom
    );
    if (procDateTo) filtered = filtered.filter(p =>
        p.purchase_date && p.purchase_date.slice(0, 10) <= procDateTo
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
                        ${p.ebay_item_id ? `<div style="margin-top:4px;">Item ID: <a href="https://www.ebay.com/itm/${encodeURIComponent(p.ebay_item_id)}" target="_blank" style="color:#2563EB;">${esc(p.ebay_item_id)}</a>${!p.ebay_order_id ? ` <button data-item-id="${esc(p.ebay_item_id)}" onclick="fifoAssign(this.dataset.itemId)" style="margin-left:6px;font-size:10px;padding:1px 6px;border:1px solid #E2E8F0;border-radius:4px;cursor:pointer;background:#F8FAFC;">FIFO割当</button>` : ''}</div>` : ''}
                        ${p.ebay_order_id ? `<div style="margin-top:2px;font-size:11px;color:#64748B;">Order: ${esc(p.ebay_order_id)} <span style="color:#22C55E;">●</span></div>` : ''}
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

async function saveProcLocation(id, value) {
    try {
        const idx = procRawData.findIndex(x => x.id === id);
        if (idx !== -1) procRawData[idx].location = value;
        await apiFetch(`/api/procurements/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ location: value }),
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
        const img = document.createElement('img');
        img.src = `/api/procurements/${encodeURIComponent(id)}/screenshot?t=${Date.now()}`;
        img.style.cssText = 'max-width:100%;max-height:120px;border-radius:4px;';
        preview.innerHTML = '';
        preview.appendChild(img);
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
        .map(cb => parseInt(cb.dataset.id, 10))
        .filter(n => !isNaN(n));
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
        const allCb = document.getElementById('procSelectAll');
        if (allCb) allCb.checked = false;
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
let _procScrapePoller2 = null; // setInterval handle for scrape modal polling (_procScrapePoller at line 12 is reserved, unused)

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

async function fifoAssign(ebayItemId) {
    if (!confirm(`Item ID: ${ebayItemId} の仕入れ記録を売上と FIFO 自動紐付けしますか？`)) return;
    const resp = await fetch('/api/procurements/fifo-assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ebay_item_id: ebayItemId }),
    });
    if (!resp.ok) throw new Error(`サーバーエラー: ${resp.status}`);
    const data = await resp.json();
    if (data.count === 0) {
        alert('紐付け対象なし（売上記録が見つからないか、すでに紐付け済みです）');
    } else {
        alert(`${data.count}件 紐付けました`);
        location.reload();
    }
}
