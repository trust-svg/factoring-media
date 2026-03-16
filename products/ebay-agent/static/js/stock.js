/* stock.js — 仕入れ台帳ページ */

// ── 為替レート ──────────────────────────────────────────
let _usdJpyRate = 149; // デフォルト

async function fetchExchangeRate() {
    try {
        const resp = await fetch('/api/exchange-rate');
        const data = await resp.json();
        if (data.usd_to_jpy) _usdJpyRate = data.usd_to_jpy;
    } catch (e) {
        console.warn('為替レート取得失敗、デフォルト使用:', _usdJpyRate);
    }
}

// ── カラム定義（並び替え可能） ──────────────────────────
const ALL_COLUMNS = [
    { id: 'stock_no',  label: 'No.',       labelJa: '管理番号' },
    { id: 'title',     label: 'Product',   labelJa: '商品名' },
    { id: 'sku',       label: 'SKU',       labelJa: 'SKU' },
    { id: 'cost',      label: 'Cost',      labelJa: '仕入原価' },
    { id: 'date',      label: 'Date',      labelJa: '仕入日' },
    { id: 'source',    label: 'Source',     labelJa: '仕入先' },
    { id: 'condition', label: 'Condition',  labelJa: '状態' },
    { id: 'status',    label: 'Status',     labelJa: 'ステータス' },
    { id: 'sold_at',   label: 'Sold',       labelJa: '売却日' },
    { id: 'ebay',      label: 'eBay',      labelJa: 'eBay' },
    { id: 'ss',        label: 'SS',        labelJa: 'SS' },
];

const STORAGE_KEY = 'stock_column_order';

function getColumnOrder() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const order = JSON.parse(saved);
            // 保存済みのカラムに新規カラムを追加（互換性）
            const savedIds = new Set(order);
            for (const col of ALL_COLUMNS) {
                if (!savedIds.has(col.id)) order.push(col.id);
            }
            // 削除されたカラムを除去
            return order.filter(id => ALL_COLUMNS.some(c => c.id === id));
        }
    } catch (e) {}
    return ALL_COLUMNS.map(c => c.id);
}

function saveColumnOrder(order) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(order));
}

function getColDef(id) {
    return ALL_COLUMNS.find(c => c.id === id);
}

// ── テーブルヘッダー（D&D対応） ────────────────────────
function renderTableHeader() {
    const thead = document.querySelector('#stockTable thead tr');
    const order = getColumnOrder();
    let html = '<th style="width:32px;"><input type="checkbox" id="selectAll" onchange="toggleSelectAll(this.checked)" style="cursor:pointer;"></th>';
    for (const colId of order) {
        const col = getColDef(colId);
        if (!col) continue;
        html += `<th draggable="true" data-col="${colId}" style="cursor:grab;user-select:none;" data-en="${col.label}" data-ja="${col.labelJa}">${col.label}</th>`;
    }
    html += '<th></th>'; // Actions column
    thead.innerHTML = html;
    initHeaderDragDrop();
}

let dragCol = null;

function initHeaderDragDrop() {
    const ths = document.querySelectorAll('#stockTable thead th[draggable]');
    ths.forEach(th => {
        th.addEventListener('dragstart', (e) => {
            dragCol = th.dataset.col;
            th.style.opacity = '0.4';
            e.dataTransfer.effectAllowed = 'move';
        });
        th.addEventListener('dragend', () => {
            th.style.opacity = '1';
            dragCol = null;
            document.querySelectorAll('#stockTable thead th').forEach(h => h.classList.remove('drag-over'));
        });
        th.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            th.classList.add('drag-over');
        });
        th.addEventListener('dragleave', () => {
            th.classList.remove('drag-over');
        });
        th.addEventListener('drop', (e) => {
            e.preventDefault();
            th.classList.remove('drag-over');
            if (!dragCol || dragCol === th.dataset.col) return;
            const order = getColumnOrder();
            const fromIdx = order.indexOf(dragCol);
            const toIdx = order.indexOf(th.dataset.col);
            if (fromIdx < 0 || toIdx < 0) return;
            order.splice(fromIdx, 1);
            order.splice(toIdx, 0, dragCol);
            saveColumnOrder(order);
            renderTableHeader();
            loadItems();
        });
    });
}

// ── セル描画 ────────────────────────────────────────────
function renderCell(colId, i) {
    switch (colId) {
        case 'stock_no':
            return `<td style="font-size:11px;white-space:nowrap;">
                <input type="text" value="${esc(i.stock_number || '')}" placeholder="-"
                    style="width:70px;padding:2px 4px;font-size:11px;border:1px solid transparent;border-radius:4px;background:transparent;text-align:center;"
                    onfocus="this.style.borderColor='var(--brand-500)';this.style.background='white'"
                    onblur="this.style.borderColor='transparent';this.style.background='transparent';saveStockNumber(${i.id},this.value)"
                    onkeydown="if(event.key==='Enter'){this.blur()}"
                ></td>`;
        case 'sku':
            return `<td style="font-size:11px;color:var(--text-secondary);white-space:nowrap;">${esc(i.sku || '-')}</td>`;
        case 'title': {
            const thumb = i.image_url
                ? `<img src="${esc(i.image_url)}" style="width:28px;height:28px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-right:6px;" onerror="this.style.display='none'">`
                : '';
            const titleText = esc((i.title || '').slice(0, 40));
            const titleContent = i.purchase_url
                ? `<a href="${esc(i.purchase_url)}" target="_blank" style="color:inherit;text-decoration:none;" onmouseover="this.style.color='var(--brand-500)'" onmouseout="this.style.color='inherit'">${titleText}</a>`
                : titleText;
            return `<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;" title="${esc(i.title)}">${thumb}${titleContent}</td>`;
        }
        case 'cost': {
            const totalCost = i.purchase_price_jpy + i.consumption_tax_jpy + (i.shipping_cost_jpy || 0);
            const details = [];
            if (i.purchase_price_jpy) details.push(`本体¥${i.purchase_price_jpy.toLocaleString()}`);
            if (i.consumption_tax_jpy) details.push(`税¥${i.consumption_tax_jpy.toLocaleString()}`);
            if (i.shipping_cost_jpy) details.push(`送¥${i.shipping_cost_jpy.toLocaleString()}`);
            const detailNote = details.length > 1 ? `<br><span style="font-size:10px;color:var(--text-muted);">${details.join(' + ')}</span>` : '';
            return `<td style="font-size:12px;">¥${totalCost.toLocaleString()}${detailNote}</td>`;
        }
        case 'date':
            return `<td style="font-size:12px;">${i.purchase_date || '-'}</td>`;
        case 'source': {
            const sourceLink = i.purchase_url
                ? `<a href="${esc(i.purchase_url)}" target="_blank" style="color:var(--text-secondary);font-size:11px;text-decoration:none;">${esc(i.purchase_source || '?')} ↗</a>`
                : esc(i.purchase_source || '-');
            const sellerInfo = i.seller_id
                ? (i.seller_url
                    ? `<br><a href="${esc(i.seller_url)}" target="_blank" style="color:var(--text-muted);font-size:10px;text-decoration:none;">${esc(i.seller_id)} ↗</a>`
                    : `<br><span style="font-size:10px;color:var(--text-muted);">${esc(i.seller_id)}</span>`)
                : '';
            return `<td style="font-size:12px;">${sourceLink}${sellerInfo}</td>`;
        }
        case 'condition':
            return `<td style="font-size:12px;">${esc(i.condition || '-')}</td>`;
        case 'status':
            return `<td style="font-size:11px;">${buildStatusBadge(i.status)}</td>`;
        case 'sold_at':
            return `<td style="font-size:12px;">${i.sold_at || '-'}</td>`;
        case 'ebay': {
            if (i.ebay_item_id) {
                const usd = i.ebay_price_usd || 0;
                const jpy = Math.round(usd * _usdJpyRate);
                const ebayLink = `<a href="https://www.ebay.com/itm/${i.ebay_item_id}" target="_blank" style="color:var(--accent-blue);font-size:11px;">$${usd} ↗</a>`;
                const jpyNote = jpy ? `<br><span style="font-size:10px;color:var(--text-muted);">≈¥${jpy.toLocaleString()}</span>` : '';
                return `<td style="font-size:11px;">${ebayLink}${jpyNote}</td>`;
            }
            return `<td style="font-size:11px;"><span style="color:var(--text-muted);">-</span></td>`;
        }
        case 'ss': {
            const ssIcon = i.screenshot_path
                ? `<button class="btn btn-sm btn-outline" onclick="viewScreenshot(${i.id}, '${esc(i.title)}')" style="padding:1px 5px;font-size:10px;">📸</button>`
                : '<span style="color:var(--text-muted);font-size:10px;">-</span>';
            return `<td style="font-size:11px;">${ssIcon}</td>`;
        }
        default:
            return '<td>-</td>';
    }
}

// ── 初期化 ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    renderTableHeader();
    await fetchExchangeRate();
    loadStats();
    loadItems();
});

// ── KPI ──────────────────────────────────────────────────
async function loadStats() {
    try {
        const resp = await fetch('/api/stock/stats');
        const s = await resp.json();

        const total = (s.ordered || 0) + (s.received || 0) + (s.in_stock || 0) + (s.listed || 0) + (s.sold || 0) + (s.shipped || 0) + (s.returned || 0) + (s.cancelled || 0);
        document.getElementById('kpiTotal').textContent = total;
        document.getElementById('kpiTotalSub').textContent = `返品${s.returned || 0} / キャンセル${s.cancelled || 0}`;
        document.getElementById('kpiValue').textContent = '¥' + (s.stock_value_jpy || 0).toLocaleString();
        document.getElementById('kpiOrdered').textContent = s.ordered || 0;
        document.getElementById('kpiReceived').textContent = (s.received || 0) + (s.in_stock || 0);
        document.getElementById('kpiListed').textContent = s.listed || 0;
        document.getElementById('kpiSold').textContent = (s.sold || 0) + (s.shipped || 0);
    } catch (e) { console.error(e); }
}

// ── 一覧読み込み ────────────────────────────────────────
async function loadItems() {
    const status = document.getElementById('statusFilter').value;
    const tbody = document.getElementById('stockBody');
    const colOrder = getColumnOrder();
    const colCount = colOrder.length + 1; // +1 for actions
    try {
        const resp = await fetch(`/api/stock?status=${status}`);
        const items = await resp.json();
        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-state">データなし</td></tr>`;
            return;
        }
        tbody.innerHTML = items.map(i => {
            let cells = `<td><input type="checkbox" class="row-check" data-id="${i.id}" onchange="updateBulkBar()" style="cursor:pointer;"></td>`;
            for (const colId of colOrder) {
                cells += renderCell(colId, i);
            }
            cells += `<td style="white-space:nowrap;">
                <button class="btn btn-sm btn-outline" onclick="openEditModal(${i.id})" style="padding:2px 8px;font-size:11px;">Edit</button>
                <button class="btn btn-sm btn-outline" onclick="deleteItem(${i.id})" style="padding:2px 6px;font-size:11px;color:var(--accent-red);border-color:var(--accent-red);">Del</button>
            </td>`;
            return `<tr>${cells}</tr>`;
        }).join('');
        updateBulkBar();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-state">読み込みエラー</td></tr>`;
        console.error(e);
    }
}

// ── ステータスバッジ ────────────────────────────────────
function buildStatusBadge(status) {
    const map = {
        'ordered': { label: '注文済み', bg: '#f59e0b', text: 'white' },
        'received': { label: '入荷済み', bg: '#3b82f6', text: 'white' },
        'in_stock': { label: '入荷済み', bg: '#3b82f6', text: 'white' },
        'listed': { label: '出品中', bg: '#8b5cf6', text: 'white' },
        'sold': { label: '販売済み', bg: '#22c55e', text: 'white' },
        'shipped': { label: '発送済み', bg: '#06b6d4', text: 'white' },
        'returned': { label: '返品', bg: '#ef4444', text: 'white' },
        'cancelled': { label: 'キャンセル', bg: '#6b7280', text: 'white' },
    };
    const c = map[status] || { label: status, bg: 'var(--border)', text: 'var(--text-tertiary)' };
    return `<span style="display:inline-block;padding:2px 6px;border-radius:8px;font-size:10px;background:${c.bg};color:${c.text};white-space:nowrap;">${c.label}</span>`;
}

// ── URL自動検出 ────────────────────────────────────────
function autoDetectUrl() {
    const url = document.getElementById('fUrl').value.trim();
    if (!url) { alert('URLを入力してください'); return; }

    const statusEl = document.getElementById('urlDetectStatus');
    statusEl.textContent = '検出中...';

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
        { pattern: /treasure-f|tf-.*\.com/, source: 'トレファク' },
        { pattern: /mandarake\.co\.jp/, source: 'まんだらけ' },
        { pattern: /paypayfleamarket|yahoo.*flea/, source: 'Yahooフリマ' },
        { pattern: /netmall\.hardoff|ofmall/, source: 'ネットモール(OFFモール)' },
    ];

    let detected = null;
    for (const pm of platformMap) {
        if (pm.pattern.test(url)) {
            detected = pm.source;
            break;
        }
    }

    if (detected) {
        document.getElementById('fSource').value = detected;
        statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ ${detected} を検出</span>`;
    } else {
        statusEl.innerHTML = '<span style="color:#f59e0b;">プラットフォームを自動判別できませんでした</span>';
    }

    if (!document.getElementById('fDate').value) {
        document.getElementById('fDate').value = new Date().toISOString().slice(0, 10);
    }
}

// ── スクリーンショット D&D ──────────────────────────────
let pendingScreenshot = null;

function handleScreenshotDrop(event) {
    event.preventDefault();
    event.currentTarget.style.borderColor = 'var(--border)';
    const file = event.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        setScreenshotPreview(file);
    }
}

function handleScreenshotSelect(event) {
    const file = event.target.files[0];
    if (file) setScreenshotPreview(file);
}

function setScreenshotPreview(file) {
    pendingScreenshot = file;
    const preview = document.getElementById('screenshotPreview');
    const prompt = document.getElementById('screenshotPrompt');
    const reader = new FileReader();
    reader.onload = (e) => {
        preview.innerHTML = `<img src="${e.target.result}" style="max-width:100%;max-height:150px;border-radius:4px;">`;
        preview.style.display = 'block';
        prompt.innerHTML = `<span style="font-size:11px;color:var(--accent-green);">✓ ${file.name} (${(file.size/1024).toFixed(0)}KB)</span>`;
    };
    reader.readAsDataURL(file);
}

async function uploadScreenshot(itemId) {
    if (!pendingScreenshot) return;
    const formData = new FormData();
    formData.append('file', pendingScreenshot);
    try {
        await fetch(`/api/stock/${itemId}/screenshot`, {
            method: 'POST',
            body: formData,
        });
    } catch (e) { console.error('Screenshot upload failed:', e); }
    pendingScreenshot = null;
}

function viewScreenshot(id, title) {
    document.getElementById('ssTitle').textContent = title;
    document.getElementById('ssImage').src = `/api/stock/screenshot/${id}?t=${Date.now()}`;
    document.getElementById('ssModal').style.display = 'flex';
}



// ── モーダル ────────────────────────────────────────────
let itemCache = {};

function openAddModal() {
    document.getElementById('editItemId').value = '';
    document.getElementById('modalTitle').textContent = '仕入れ登録';
    clearForm();
    document.getElementById('fDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('fStatus').value = 'ordered';
    document.getElementById('fQty').value = '1';
    document.getElementById('screenshotPreview').style.display = 'none';
    document.getElementById('screenshotPrompt').innerHTML = '<span style="font-size:24px;">📸</span><br><span style="font-size:12px;color:var(--text-muted);">スクリーンショットをドロップ、またはクリックして選択</span>';
    pendingScreenshot = null;
    document.getElementById('urlDetectStatus').textContent = '';
    document.getElementById('stockModal').style.display = 'flex';
}

async function openEditModal(id) {
    if (!itemCache[id]) {
        const resp = await fetch('/api/stock');
        const items = await resp.json();
        items.forEach(i => itemCache[i.id] = i);
    }
    const i = itemCache[id];
    if (!i) return;

    document.getElementById('editItemId').value = id;
    document.getElementById('modalTitle').textContent = '編集';
    document.getElementById('fTitle').value = i.title || '';
    document.getElementById('fPrice').value = i.purchase_price_jpy || '';
    document.getElementById('fTax').value = i.consumption_tax_jpy || '';
    document.getElementById('fShipping').value = i.shipping_cost_jpy || '';
    document.getElementById('fDate').value = i.purchase_date || '';
    document.getElementById('fSource').value = i.purchase_source || '';
    document.getElementById('fUrl').value = i.purchase_url || '';
    document.getElementById('fSellerId').value = i.seller_id || '';
    document.getElementById('fSellerUrl').value = i.seller_url || '';
    document.getElementById('fQty').value = i.quantity || 1;
    document.getElementById('fLocation').value = i.location || '';
    document.getElementById('fCondition').value = i.condition || '';
    document.getElementById('fStatus').value = i.status || 'ordered';
    document.getElementById('fStockNo').value = i.stock_number || '';
    document.getElementById('fSku').value = i.sku || '';
    document.getElementById('fEbayId').value = i.ebay_item_id || '';
    document.getElementById('fOrderId').value = i.ebay_order_id || '';
    document.getElementById('fEbayPrice').value = i.ebay_price_usd || '';
    document.getElementById('fImage').value = i.image_url || '';
    document.getElementById('fNotes').value = i.notes || '';
    document.getElementById('urlDetectStatus').textContent = '';

    // スクリーンショットプレビュー
    pendingScreenshot = null;
    const preview = document.getElementById('screenshotPreview');
    const prompt = document.getElementById('screenshotPrompt');
    if (i.screenshot_path) {
        preview.innerHTML = `<img src="/api/stock/screenshot/${id}?t=${Date.now()}" style="max-width:100%;max-height:150px;border-radius:4px;">`;
        preview.style.display = 'block';
        prompt.innerHTML = '<span style="font-size:11px;color:var(--accent-green);">✓ スクリーンショット保存済み（新しい画像をドロップで上書き）</span>';
    } else {
        preview.style.display = 'none';
        prompt.innerHTML = '<span style="font-size:24px;">📸</span><br><span style="font-size:12px;color:var(--text-muted);">スクリーンショットをドロップ、またはクリックして選択</span>';
    }

    document.getElementById('stockModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('stockModal').style.display = 'none';
}

function clearForm() {
    ['fTitle','fPrice','fTax','fShipping','fDate','fSource','fUrl','fQty','fSellerId','fSellerUrl',
     'fLocation','fCondition','fStatus','fStockNo','fSku','fEbayId','fOrderId','fEbayPrice','fImage','fNotes'].forEach(id => {
        const el = document.getElementById(id);
        if (el.tagName === 'SELECT') el.selectedIndex = 0;
        else el.value = '';
    });
}

async function saveItem() {
    const id = document.getElementById('editItemId').value;
    const body = {
        title: document.getElementById('fTitle').value,
        purchase_price_jpy: parseInt(document.getElementById('fPrice').value) || 0,
        consumption_tax_jpy: parseInt(document.getElementById('fTax').value) || 0,
        shipping_cost_jpy: parseInt(document.getElementById('fShipping').value) || 0,
        purchase_date: document.getElementById('fDate').value,
        purchase_source: document.getElementById('fSource').value,
        purchase_url: document.getElementById('fUrl').value,
        seller_id: document.getElementById('fSellerId').value,
        seller_url: document.getElementById('fSellerUrl').value,
        quantity: parseInt(document.getElementById('fQty').value) || 1,
        location: document.getElementById('fLocation').value,
        condition: document.getElementById('fCondition').value,
        status: document.getElementById('fStatus').value,
        stock_number: document.getElementById('fStockNo').value,
        sku: document.getElementById('fSku').value,
        ebay_item_id: document.getElementById('fEbayId').value,
        ebay_order_id: document.getElementById('fOrderId').value,
        ebay_price_usd: parseFloat(document.getElementById('fEbayPrice').value) || 0,
        image_url: document.getElementById('fImage').value,
        notes: document.getElementById('fNotes').value,
    };

    try {
        const url = id ? `/api/stock/${id}` : '/api/stock';
        const method = id ? 'PUT' : 'POST';
        const resp = await fetch(url, {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const result = await resp.json();
        if (resp.ok) {
            const itemId = result.id || id;
            if (pendingScreenshot && itemId) {
                await uploadScreenshot(itemId);
            }
            closeModal();
            itemCache = {};
            loadItems();
            loadStats();
        }
    } catch (e) { console.error(e); }
}

async function deleteItem(id) {
    if (!confirm('この仕入れ記録を削除しますか？')) return;
    try {
        await fetch(`/api/stock/${id}`, { method: 'DELETE' });
        itemCache = {};
        loadItems();
        loadStats();
    } catch (e) { console.error(e); }
}

// ── 設定 ────────────────────────────────────────────────
async function openSettings() {
    try {
        const resp = await fetch('/api/settings/screenshot-dir');
        const d = await resp.json();
        document.getElementById('ssDir').value = d.path || '';
    } catch (e) {}
    document.getElementById('settingsModal').style.display = 'flex';
}

async function saveScreenshotDir() {
    const path = document.getElementById('ssDir').value.trim();
    if (!path) { alert('パスを入力してください'); return; }
    try {
        await fetch('/api/settings/screenshot-dir', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
        });
        alert('保存しました（サーバー再起動後に反映）');
        document.getElementById('settingsModal').style.display = 'none';
    } catch (e) { console.error(e); }
}

// ── 一括取込 ──────────────────────────────────────────────
function openBulkImport() {
    document.getElementById('bulkData').value = '';
    document.getElementById('bulkStatus').textContent = '';
    updateBulkHelp();
    document.getElementById('bulkModal').style.display = 'flex';
}

function updateBulkHelp() {
    const platform = document.getElementById('bulkPlatform').value;
    const helpEl = document.getElementById('bulkHelp');
    const helpMap = {
        'ヤフオク': `<b>auctions.yahoo.co.jp/my/won</b> を開いて落札一覧をそのまま全選択→コピー→貼り付け。<br>
            ページ内のテキストから商品名・落札価格・日付を自動抽出します。<br>
            <span style="color:var(--text-muted);">※ 画像やボタン等のUI要素は自動的にスキップされます</span>`,
        'メルカリ': `<b>mercari.com/mypage/purchases/</b> を開いて購入履歴をコピー→貼り付け。<br>
            または手動入力: 1行1商品、タブ区切りで 商品名(TAB)価格(TAB)日付<br>
            <span style="color:var(--text-muted);">例: SONY WM-D6C ウォークマン&#9;15000&#9;2026-03-10</span>`,
        'ラクマ': `購入履歴ページからコピー→貼り付け。<br>
            または手動入力: 商品名(TAB)価格(TAB)日付`,
        'Amazon': `注文履歴ページからコピー→貼り付け。<br>
            または手動入力: 商品名(TAB)価格(TAB)日付`,
        'その他': `1行1商品。タブ区切り: 商品名(TAB)価格(TAB)日付<br>
            <span style="color:var(--text-muted);">日付は省略可（今日の日付になります）<br>
            例: Pioneer A-717&#9;8500&#9;2026-03-08</span>`,
    };
    helpEl.innerHTML = helpMap[platform] || helpMap['その他'];
}

// ── プラットフォーム別パーサー ──────────────────────────
function parseYahooAuctions(raw) {
    const rows = [];
    const lines = raw.split('\n').map(l => l.trim()).filter(l => l);

    const priceRe = /^[\d,]+\s*円$/;
    const dateRe1 = /(\d{4})[年\/\-](\d{1,2})[月\/\-](\d{1,2})/;
    const dateRe2 = /(\d{1,2})月(\d{1,2})日/;
    const skipRe = /^(入札|ウォッチ|商品画像|取引|質問|まとめて|値下げ|クーポン|送料無料|条件|表示|並び替え|落札済み|すべて|未払い|支払い|発送|受取|評価|メッセージ|\d+件|PR|おすすめ|前へ|次へ|ページ|件中|Yahoo|ログイン|マイ・オークション|落札分|ヘルプ|閉じる|もっと見る|落札価格|終了日時|タイトル|オプション|即決|新品|中古|個数|残り)/;

    let current = { title: '', price: 0, date: '', seller: '' };
    let phase = 'title';

    for (const line of lines) {
        if (skipRe.test(line)) continue;
        if (line.length < 2) continue;

        if (priceRe.test(line)) {
            if (phase === 'price' || phase === 'title') {
                current.price = parseInt(line.replace(/[^0-9]/g, '')) || 0;
                phase = 'date';
            }
            continue;
        }

        const m1 = line.match(dateRe1);
        if (m1) {
            current.date = `${m1[1]}-${m1[2].padStart(2,'0')}-${m1[3].padStart(2,'0')}`;
            phase = 'seller';
            continue;
        }
        const m2 = line.match(dateRe2);
        if (m2 && phase === 'date') {
            const year = new Date().getFullYear();
            current.date = `${year}-${m2[1].padStart(2,'0')}-${m2[2].padStart(2,'0')}`;
            phase = 'seller';
            continue;
        }

        if (phase === 'seller' && line.length >= 2 && line.length <= 60) {
            current.seller = line;
            if (current.title && current.price) {
                rows.push({ ...current });
            }
            current = { title: '', price: 0, date: '', seller: '' };
            phase = 'title';
            continue;
        }

        if (phase === 'title' && line.length >= 3 && !/^\d+$/.test(line)) {
            if (current.title && current.price) {
                if (!current.date) current.date = new Date().toISOString().slice(0, 10);
                rows.push({ ...current });
                current = { title: '', price: 0, date: '', seller: '' };
            }
            current.title = line;
            phase = 'price';
        }
    }
    if (current.title && current.price) {
        if (!current.date) current.date = new Date().toISOString().slice(0, 10);
        rows.push({ ...current });
    }

    return rows;
}

function parseGenericTSV(raw) {
    const lines = raw.split('\n').filter(l => l.trim());
    return lines.map(line => {
        const parts = line.split('\t');
        const title = (parts[0] || '').trim();
        const price = parseInt((parts[1] || '0').replace(/[^0-9]/g, '')) || 0;
        const date = (parts[2] || '').trim() || new Date().toISOString().slice(0, 10);
        return { title, price, date };
    }).filter(r => r.title && r.title.length >= 2);
}

function parseBulkData(platform, raw) {
    if (platform === 'ヤフオク') {
        const yaRows = parseYahooAuctions(raw);
        if (yaRows.length > 0) return yaRows;
    }
    return parseGenericTSV(raw);
}

async function runBulkImport() {
    const platform = document.getElementById('bulkPlatform').value;
    const raw = document.getElementById('bulkData').value.trim();
    if (!raw) { alert('データを貼り付けてください'); return; }

    const rows = parseBulkData(platform, raw);

    if (!rows.length) { alert('有効なデータを検出できませんでした。\n商品名・価格が含まれているか確認してください。'); return; }

    const preview = rows.slice(0, 3).map(r => {
        const seller = r.seller ? ` [${r.seller}]` : '';
        return `  ${r.title.slice(0, 30)}... ¥${r.price.toLocaleString()}${seller}`;
    }).join('\n');
    const more = rows.length > 3 ? `\n  ...他${rows.length - 3}件` : '';
    if (!confirm(`${rows.length}件の商品を検出しました:\n\n${preview}${more}\n\n取り込みますか？`)) return;

    document.getElementById('bulkStatus').innerHTML = `<span style="color:var(--accent-blue);">取り込み中... ${rows.length}件</span>`;

    try {
        const resp = await fetch('/api/stock/bulk-import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rows, platform }),
        });
        const result = await resp.json();
        if (resp.ok) {
            document.getElementById('bulkStatus').innerHTML =
                `<span style="color:var(--accent-green);">✓ ${result.created}件登録 / ${result.skipped}件スキップ（重複）</span>`;
            itemCache = {};
            loadItems();
            loadStats();
        } else {
            document.getElementById('bulkStatus').innerHTML =
                `<span style="color:var(--accent-red);">エラー: ${result.detail || 'Unknown'}</span>`;
        }
    } catch (e) {
        document.getElementById('bulkStatus').innerHTML =
            `<span style="color:var(--accent-red);">通信エラー</span>`;
        console.error(e);
    }
}

// ── タブ切替 ────────────────────────────────────────────
function switchBulkTab(tab) {
    const isAuto = tab === 'auto';
    document.getElementById('panelAuto').style.display = isAuto ? 'block' : 'none';
    document.getElementById('panelManual').style.display = isAuto ? 'none' : 'block';
    document.getElementById('tabAuto').className = isAuto ? 'btn btn-sm' : 'btn btn-sm btn-outline';
    document.getElementById('tabManual').className = isAuto ? 'btn btn-sm btn-outline' : 'btn btn-sm';
    document.getElementById('tabAuto').style.borderBottomColor = isAuto ? 'var(--accent-blue)' : 'transparent';
    document.getElementById('tabManual').style.borderBottomColor = isAuto ? 'transparent' : 'var(--accent-blue)';
    if (!isAuto) updateBulkHelp();
}

// ── ヤフオク自動取込 ────────────────────────────────────
let scrapeJobId = null;
let scrapePoller = null;

async function startYahooScrape() {
    const maxPages = parseInt(document.getElementById('scrapeMaxPages').value) || 50;
    const btn = document.getElementById('btnStartScrape');
    btn.disabled = true;
    btn.textContent = '取込開始中...';

    document.getElementById('scrapeProgress').style.display = 'block';
    document.getElementById('scrapeResult').style.display = 'none';
    document.getElementById('scrapeMsg').textContent = '初期化中...';
    document.getElementById('scrapeBar').style.width = '0%';
    document.getElementById('scrapeCount').textContent = '';

    try {
        const resp = await fetch('/api/stock/scrape/yahoo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_pages: maxPages }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to start');

        scrapeJobId = data.job_id;
        btn.textContent = '取込中...';

        // ポーリング開始
        scrapePoller = setInterval(pollScrapeStatus, 2000);
    } catch (e) {
        btn.disabled = false;
        btn.textContent = 'ヤフオク落札一覧を自動取込';
        document.getElementById('scrapeProgress').style.display = 'none';
        alert('エラー: ' + e.message);
    }
}

async function pollScrapeStatus() {
    if (!scrapeJobId) return;
    try {
        const resp = await fetch(`/api/stock/scrape/status/${scrapeJobId}`);
        const data = await resp.json();

        document.getElementById('scrapeMsg').textContent = data.message || '処理中...';
        if (data.total > 0) {
            const pct = Math.round((data.current / data.total) * 100);
            document.getElementById('scrapeBar').style.width = pct + '%';
            document.getElementById('scrapeCount').textContent = `${data.current} / ${data.total}`;
        }

        if (data.status === 'done') {
            clearInterval(scrapePoller);
            scrapePoller = null;
            document.getElementById('scrapeProgress').style.display = 'none';
            document.getElementById('scrapeBar').style.width = '100%';

            // 結果表示
            const resultEl = document.getElementById('scrapeResult');
            resultEl.style.display = 'block';
            resultEl.innerHTML = `
                <div style="padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                    <span style="color:var(--accent-green);font-weight:600;">${data.result_count}件の商品を取得しました</span>
                    <div style="margin-top:8px;">
                        <button class="btn btn-sm" onclick="importScrapeResults()">台帳に登録する</button>
                        <button class="btn btn-sm btn-outline" onclick="cancelScrape()" style="margin-left:4px;">キャンセル</button>
                    </div>
                </div>`;

            const btn = document.getElementById('btnStartScrape');
            btn.disabled = false;
            btn.textContent = 'ヤフオク落札一覧を自動取込';
        } else if (data.status === 'error' || data.status === 'login_required') {
            clearInterval(scrapePoller);
            scrapePoller = null;
            document.getElementById('scrapeProgress').style.display = 'none';

            const resultEl = document.getElementById('scrapeResult');
            resultEl.style.display = 'block';
            resultEl.innerHTML = `<div style="padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                <span style="color:var(--accent-red);">${data.message}</span></div>`;

            const btn = document.getElementById('btnStartScrape');
            btn.disabled = false;
            btn.textContent = 'ヤフオク落札一覧を自動取込';
        }
    } catch (e) {
        console.error('Poll error:', e);
    }
}

async function importScrapeResults() {
    if (!scrapeJobId) return;
    const resultEl = document.getElementById('scrapeResult');
    resultEl.innerHTML = '<span style="color:var(--accent-blue);">台帳に登録中...</span>';

    try {
        const resp = await fetch(`/api/stock/scrape/import/${scrapeJobId}`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (resp.ok) {
            resultEl.innerHTML = `<div style="padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                <span style="color:var(--accent-green);font-weight:600;">✓ ${data.created}件登録 / ${data.skipped}件スキップ（重複）</span></div>`;
            itemCache = {};
            loadItems();
            loadStats();
        } else {
            resultEl.innerHTML = `<span style="color:var(--accent-red);">エラー: ${data.detail || 'Unknown'}</span>`;
        }
    } catch (e) {
        resultEl.innerHTML = `<span style="color:var(--accent-red);">通信エラー</span>`;
    }
    scrapeJobId = null;
}

function cancelScrape() {
    scrapeJobId = null;
    document.getElementById('scrapeResult').style.display = 'none';
}

// ── メルカリ自動取込 ──────────────────────────────────
let mercariJobId = null;
let mercariPoller = null;

async function startMercariScrape() {
    const btn = document.getElementById('btnStartMercari');
    btn.disabled = true;
    btn.textContent = '取込開始中...';

    document.getElementById('mercariProgress').style.display = 'block';
    document.getElementById('mercariResult').style.display = 'none';
    document.getElementById('mercariMsg').textContent = '初期化中...';
    document.getElementById('mercariBar').style.width = '0%';
    document.getElementById('mercariCount').textContent = '';

    try {
        const resp = await fetch('/api/stock/scrape/mercari', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to start');

        mercariJobId = data.job_id;
        btn.textContent = '取込中...';
        mercariPoller = setInterval(pollMercariStatus, 2000);
    } catch (e) {
        btn.disabled = false;
        btn.textContent = 'メルカリ自動取込';
        document.getElementById('mercariProgress').style.display = 'none';
        alert('エラー: ' + e.message);
    }
}

async function pollMercariStatus() {
    if (!mercariJobId) return;
    try {
        const resp = await fetch(`/api/stock/scrape/status/${mercariJobId}`);
        const data = await resp.json();

        document.getElementById('mercariMsg').textContent = data.message || '処理中...';
        if (data.total > 0) {
            const pct = Math.round((data.current / data.total) * 100);
            document.getElementById('mercariBar').style.width = pct + '%';
            document.getElementById('mercariCount').textContent = `${data.current} / ${data.total}`;
        }

        if (data.status === 'done') {
            clearInterval(mercariPoller);
            mercariPoller = null;
            document.getElementById('mercariProgress').style.display = 'none';

            const resultEl = document.getElementById('mercariResult');
            resultEl.style.display = 'block';
            resultEl.innerHTML = `
                <div style="padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                    <span style="color:var(--accent-green);font-weight:600;">${data.result_count}件の商品を取得しました</span>
                    <div style="margin-top:8px;">
                        <button class="btn btn-sm" onclick="importMercariResults()" style="background:#ef4444;border-color:#ef4444;">台帳に登録する</button>
                        <button class="btn btn-sm btn-outline" onclick="cancelMercari()" style="margin-left:4px;">キャンセル</button>
                    </div>
                </div>`;

            document.getElementById('btnStartMercari').disabled = false;
            document.getElementById('btnStartMercari').textContent = 'メルカリ自動取込';
        } else if (data.status === 'error' || data.status === 'login_required') {
            clearInterval(mercariPoller);
            mercariPoller = null;
            document.getElementById('mercariProgress').style.display = 'none';

            const resultEl = document.getElementById('mercariResult');
            resultEl.style.display = 'block';
            resultEl.innerHTML = `<div style="padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                <span style="color:var(--accent-red);">${data.message}</span></div>`;

            document.getElementById('btnStartMercari').disabled = false;
            document.getElementById('btnStartMercari').textContent = 'メルカリ自動取込';
        }
    } catch (e) {
        console.error('Mercari poll error:', e);
    }
}

async function importMercariResults() {
    if (!mercariJobId) return;
    const resultEl = document.getElementById('mercariResult');
    resultEl.innerHTML = '<span style="color:var(--accent-blue);">台帳に登録中...</span>';

    try {
        const resp = await fetch(`/api/stock/scrape/mercari/import/${mercariJobId}`, { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            resultEl.innerHTML = `<div style="padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                <span style="color:var(--accent-green);font-weight:600;">✓ ${data.created}件登録 / ${data.skipped}件スキップ（重複）</span></div>`;
            itemCache = {};
            loadItems();
            loadStats();
        } else {
            resultEl.innerHTML = `<span style="color:var(--accent-red);">エラー: ${data.detail || 'Unknown'}</span>`;
        }
    } catch (e) {
        resultEl.innerHTML = `<span style="color:var(--accent-red);">通信エラー</span>`;
    }
    mercariJobId = null;
}

function cancelMercari() {
    mercariJobId = null;
    document.getElementById('mercariResult').style.display = 'none';
}

// ── チェックボックス一括操作 ────────────────────────────
function toggleSelectAll(checked) {
    document.querySelectorAll('.row-check').forEach(cb => cb.checked = checked);
    updateBulkBar();
}

function getSelectedIds() {
    return [...document.querySelectorAll('.row-check:checked')].map(cb => parseInt(cb.dataset.id));
}

function updateBulkBar() {
    const ids = getSelectedIds();
    const bar = document.getElementById('bulkActionBar');
    if (!bar) return;
    if (ids.length > 0) {
        bar.style.display = 'flex';
        document.getElementById('bulkCount').textContent = `${ids.length}件選択中`;
    } else {
        bar.style.display = 'none';
    }
    // ヘッダーチェックボックスの状態
    const allCbs = document.querySelectorAll('.row-check');
    const selectAll = document.getElementById('selectAll');
    if (selectAll && allCbs.length > 0) {
        selectAll.checked = ids.length === allCbs.length;
        selectAll.indeterminate = ids.length > 0 && ids.length < allCbs.length;
    }
}

async function bulkDeleteSelected() {
    const ids = getSelectedIds();
    if (!ids.length) return;
    if (!confirm(`${ids.length}件の仕入れ記録を削除しますか？\nこの操作は取り消せません。`)) return;

    try {
        const resp = await fetch('/api/stock/bulk-delete-ids', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids }),
        });
        const data = await resp.json();
        if (resp.ok) {
            itemCache = {};
            loadItems();
            loadStats();
        } else {
            alert('削除エラー: ' + (data.detail || 'Unknown'));
        }
    } catch (e) {
        alert('通信エラー');
        console.error(e);
    }
}

async function bulkChangeStatus(newStatus) {
    const ids = getSelectedIds();
    if (!ids.length) return;

    const statusLabels = {
        'ordered': '注文済み', 'received': '入荷済み', 'listed': '出品中',
        'sold': '販売済み', 'shipped': '発送済み', 'cancelled': 'キャンセル',
    };
    if (!confirm(`${ids.length}件を「${statusLabels[newStatus] || newStatus}」に変更しますか？`)) return;

    try {
        for (const id of ids) {
            await fetch(`/api/stock/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
        }
        itemCache = {};
        loadItems();
        loadStats();
    } catch (e) {
        alert('通信エラー');
        console.error(e);
    }
}

// ── 在庫管理番号 ──────────────────────────────────────
async function saveStockNumber(itemId, value) {
    try {
        await fetch(`/api/stock/${itemId}/stock-number`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stock_number: value.trim() }),
        });
        // キャッシュ更新
        if (itemCache[itemId]) {
            itemCache[itemId].stock_number = value.trim();
        }
    } catch (e) {
        console.error('Stock number save failed:', e);
    }
}

// ── SKU自動付与 ──────────────────────────────────────
async function autoAssignSku() {
    if (!confirm('型番からeBay出品を自動マッチしてSKUを付与します。\n既にSKUが設定済みの商品はスキップされます。')) return;
    const btn = document.getElementById('btnAutoSku');
    btn.disabled = true;
    btn.textContent = 'マッチング中...';

    try {
        const resp = await fetch('/api/stock/auto-sku', { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            let msg = `${data.assigned}件にSKUを付与（${data.skipped}件スキップ）`;
            if (data.matches && data.matches.length > 0) {
                msg += '\n\n例:';
                for (const m of data.matches.slice(0, 5)) {
                    msg += `\n  ${m.stock_number} ${m.matched_model} → ${m.sku}`;
                }
            }
            alert(msg);
            itemCache = {};
            loadItems();
        } else {
            alert('エラー: ' + (data.detail || 'Unknown'));
        }
    } catch (e) {
        alert('通信エラー');
    }
    btn.disabled = false;
    btn.textContent = '🔗 SKU自動付与';
}

// ── スクリーンショット再撮影 ──────────────────────────────
async function retakeScreenshots() {
    if (!confirm('全商品のスクリーンショットをページ全体で再撮影します。\n時間がかかりますが実行しますか？')) return;
    const btn = document.getElementById('btnRetakeSS');
    btn.disabled = true;
    btn.textContent = '再撮影中...';

    try {
        const resp = await fetch('/api/stock/retake-screenshots', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed');

        const jobId = data.job_id;
        const poll = setInterval(async () => {
            try {
                const sr = await fetch(`/api/stock/scrape/status/${jobId}`);
                const sd = await sr.json();
                btn.textContent = sd.message || '再撮影中...';
                if (sd.status === 'done') {
                    clearInterval(poll);
                    btn.disabled = false;
                    btn.textContent = '📸 SS全ページ再撮影';
                    alert('再撮影完了');
                    itemCache = {};
                    loadItems();
                } else if (sd.status === 'error') {
                    clearInterval(poll);
                    btn.disabled = false;
                    btn.textContent = '📸 SS全ページ再撮影';
                    alert('エラー: ' + (sd.error || sd.message));
                }
            } catch (e) { console.error(e); }
        }, 3000);
    } catch (e) {
        btn.disabled = false;
        btn.textContent = '📸 SS全ページ再撮影';
        alert('エラー: ' + e.message);
    }
}

// ── ユーティリティ ──────────────────────────────────────
function esc(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
