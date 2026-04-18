/* profit.js — 利益管理ページ (ApexCharts版) */

let trendChart = null, breakdownChart = null, dailyChartInstance = null;
let summaryData = [];
let txSortCol = 'sold_at', txSortDir = 'desc';
let txRawRecords = [];

// ApexCharts共通テーマ
const chartFont = 'Inter, sans-serif';
const chartColors = {
    brand:      '#2563EB',
    brandLight: '#93C5FD',
    success:    '#10B981',
    error:      '#EF4444',
    warning:    '#F59E0B',
    purple:     '#7C3AED',
    indigo:     '#6366F1',
    gray400:    '#94A3B8',
    gray500:    '#64748B',
    gray200:    '#F1F5F9',
};

// ── 初期化 ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    populateMonthSelectors();
    loadSummary(1);
    loadTransactions();
    loadExpenses();
    loadDailyAnalytics(60);

    // 自動同期ラベル初期化
    updateAutoSyncLabel();

    // 5分ごとに取引一覧を自動更新
    setInterval(() => {
        loadTransactions();
        updateAutoSyncLabel();
    }, 5 * 60 * 1000);
});

function updateAutoSyncLabel() {
    const el = document.getElementById('autoSyncLabel');
    if (el) el.textContent = `自動同期: ${new Date().toLocaleTimeString('ja-JP', {hour:'2-digit', minute:'2-digit'})}`;
}

function populateMonthSelectors() {
    const now = new Date();
    const exportYearSel = document.getElementById('exportYear');
    const txMonthSel = document.getElementById('txMonth');
    for (let y = now.getFullYear(); y >= now.getFullYear() - 2; y--) {
        exportYearSel.add(new Option(y, y));
    }
    txMonthSel.add(new Option('All', ''));
    for (let i = 0; i < 18; i++) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        const ym = d.toISOString().slice(0, 7);
        const label = d.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short' });
        txMonthSel.add(new Option(label, ym));
    }
    txMonthSel.value = now.toISOString().slice(0, 7);

    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    document.getElementById('dateFrom').value = firstDay.toISOString().slice(0, 10);
    document.getElementById('dateTo').value = now.toISOString().slice(0, 10);
}

// ── サマリー読み込み ──────────────────────────────────
async function loadSummary(months) {
    document.querySelectorAll('.filter-pills .pill').forEach(b => b.classList.remove('active'));
    const btn = document.getElementById('btn' + months + 'm');
    if (btn) btn.classList.add('active');

    try {
        const resp = await fetch(`/api/profit/summary?months=${months}`);
        summaryData = await resp.json();
        updateKPI(summaryData);
        _profitSummaryData = summaryData;
        if (summaryData.length > 0) {
            loadBreakdown(summaryData[0].year_month);
        }
    } catch (e) {
        console.error('Failed to load summary:', e);
    }
}

function loadByDateRange() {
    const from = document.getElementById('dateFrom').value;
    const to = document.getElementById('dateTo').value;
    if (!from || !to) return;
    const fd = new Date(from);
    const td = new Date(to);
    const diffMonths = Math.max(1, Math.ceil((td - fd) / (30 * 24 * 60 * 60 * 1000)));
    document.getElementById('txMonth').value = '';
    document.querySelectorAll('.filter-pills .pill').forEach(b => b.classList.remove('active'));
    loadSummary(diffMonths);
    loadTransactions(from, to);
}

function updateKPI(data) {
    if (!data.length) {
        document.getElementById('kpiRevenue').textContent = '$0';
        document.getElementById('kpiProfit').textContent = '\u00a50';
        document.getElementById('kpiProfitRefund').textContent = '\u00a50';
        document.getElementById('kpiMargin').textContent = '0%';
        document.getElementById('kpiTaxRefund').textContent = '\u00a50';
        document.getElementById('kpiCosts').textContent = '\u00a50';
        return;
    }
    const latest = data[0];
    const taxRefund = latest.consumption_tax_jpy || 0;
    const profitWithRefund = latest.net_profit_jpy + taxRefund;
    const margin = latest.revenue_usd > 0 ? (latest.net_profit_usd / latest.revenue_usd * 100) : 0;

    document.getElementById('kpiRevenue').textContent = '$' + latest.revenue_usd.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0});
    document.getElementById('kpiRevenueJpy').textContent = '\u00a5' + latest.revenue_jpy.toLocaleString() + ' (' + latest.sales_count + '件)';

    document.getElementById('kpiProfit').textContent = '\u00a5' + latest.net_profit_jpy.toLocaleString();
    document.getElementById('kpiProfitJpy').textContent = '$' + latest.net_profit_usd.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0});

    document.getElementById('kpiProfitRefund').textContent = '\u00a5' + profitWithRefund.toLocaleString();
    document.getElementById('kpiProfitRefundSub').textContent = '利益 + 還付\u00a5' + taxRefund.toLocaleString();

    document.getElementById('kpiMargin').textContent = margin.toFixed(1) + '%';
    document.getElementById('kpiSalesCount').textContent = latest.sales_count + ' transactions';

    document.getElementById('kpiTaxRefund').textContent = '\u00a5' + taxRefund.toLocaleString();
    document.getElementById('kpiTaxRefundSub').textContent = latest.sales_count + '件の仕入消費税';

    const totalCost = latest.total_cost_jpy + (latest.fixed_cost_jpy || 0);
    document.getElementById('kpiCosts').textContent = '\u00a5' + totalCost.toLocaleString();
    document.getElementById('kpiCostBreak').textContent = `仕入:\u00a5${latest.source_cost_jpy.toLocaleString()} / 送料:\u00a5${(latest.shipping_jpy + latest.intl_shipping_jpy).toLocaleString()}`;
}

// ── 売上トレンドチャート（ダッシュボード同スタイル）────────────────
let _profitTrendData = null;
let _profitSummaryData = [];

function switchProfitChart(mode) {
    ['daily', 'monthly'].forEach(m => {
        const panel = document.getElementById(`profit-panel-${m}`);
        const btn   = document.getElementById(`profit-tab-${m}`);
        if (panel) panel.style.display = m === mode ? '' : 'none';
        if (btn)   btn.classList.toggle('on', m === mode);
    });
    if (mode === 'monthly' && _profitTrendData) {
        renderProfitMonthlyChart(_profitTrendData, _profitSummaryData);
    }
}

function renderProfitDailyChart(trend) {
    const el = document.getElementById('profitDailyChart');
    if (!el) return;
    const today = new Date().toISOString().slice(0, 10);
    const days  = trend.filter(d => d.date <= today).slice(-14);
    if (days.length === 0) {
        el.innerHTML = `<div style="grid-column:1/-1;text-align:center;color:#94A3B8;padding:20px;font-size:12px">データなし</div>`;
        return;
    }
    const maxRev = Math.max(...days.map(d => d.revenue_usd), 1);
    el.innerHTML = days.map(d => {
        const ratio = d.revenue_usd / maxRev;
        const h     = Math.max(Math.round(ratio * 64), d.revenue_usd > 0 ? 4 : 1);
        const cls   = ratio > 0.7 ? 'hi' : ratio > 0.35 ? 'md' : 'lo';
        const label = d.revenue_usd > 0 ? `$${Math.round(d.revenue_usd)}` : '—';
        return `<div class="vbar-col">
            <div class="vbar-num ${ratio > 0.7 ? 'hi' : ''}">${label}</div>
            <div class="vbar ${cls}" style="height:${h}px"></div>
            <div class="vbar-day">${d.date.slice(8).replace(/^0/, '')}</div>
        </div>`;
    }).join('');
    const sub = document.getElementById('profitDailySubLabel');
    if (sub) sub.textContent = `日別売上（直近${days.length}日）`;
}

function renderProfitMonthlyChart(trend, summary) {
    const svgEl = document.getElementById('profitMonthlySvg');
    const yEl   = document.getElementById('profitMonthlyYLabels');
    const xEl   = document.getElementById('profitMonthlyXLabels');
    if (!svgEl) return;

    const today = new Date().toISOString().slice(0, 10);
    const now   = new Date();
    const yr = now.getFullYear(), mo = now.getMonth() + 1;
    const dim   = new Date(yr, mo, 0).getDate();

    // 実際の為替レートをsummaryから計算
    const s0 = summary[0] || {};
    const rate = (s0.revenue_usd > 0) ? s0.revenue_jpy / s0.revenue_usd : 155;

    // 今月の実日次データ
    const currPfx = `${yr}-${String(mo).padStart(2,'0')}`;
    const days = Array.from({length: dim}, (_, i) => {
        const d = `${currPfx}-${String(i+1).padStart(2,'0')}`;
        const t = trend.find(x => x.date === d);
        return { date: d, rev: t ? Math.round(t.revenue_usd * rate) : 0 };
    });

    // 先月の実日次データ
    const prevMo  = mo === 1 ? 12 : mo - 1;
    const prevYr  = mo === 1 ? yr - 1 : yr;
    const prevDim = new Date(prevYr, prevMo, 0).getDate();
    const prevPfx = `${prevYr}-${String(prevMo).padStart(2,'0')}`;
    const prevDays = Array.from({length: prevDim}, (_, i) => {
        const d = `${prevPfx}-${String(i+1).padStart(2,'0')}`;
        const t = trend.find(x => x.date === d);
        return t ? Math.round(t.revenue_usd * rate) : 0;
    });

    const TARGET = 5_000_000;
    let cum = 0;
    const thisPoints = days.map(d => { if (d.date <= today) cum += d.rev; return cum; });
    const tgtPoints  = days.map((_, i) => Math.round(TARGET / dim * (i + 1)));
    const tidx   = days.findIndex(d => d.date > today);
    const active = tidx === -1 ? dim - 1 : Math.max(tidx - 1, 0);

    // 先月累計を今月のx軸にスケール
    let cumPrev = 0;
    const pmCumul = prevDays.map(v => { cumPrev += v; return cumPrev; });
    const pmPoints = days.map((_, i) => {
        const prevIdx = Math.min(Math.round(i * prevDim / dim), prevDim - 1);
        return pmCumul[prevIdx] || 0;
    });

    const svgW = svgEl.clientWidth || 280;
    const svgH = 120, padB = 16, chartH = svgH - padB;
    const maxV = Math.max(...tgtPoints, ...thisPoints, 1);
    const toX  = i => (i / Math.max(dim - 1, 1)) * svgW;
    const toY  = v => chartH - (v / maxV * chartH);
    const mkPath = (pts, n) => pts.slice(0, n + 1)
        .map((v, i) => `${i===0?'M':'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');

    if (yEl) yEl.innerHTML = [1, .75, .5, .25, 0].map(f => {
        const v = Math.round(maxV * f);
        const s = v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(0)}K` : String(v);
        return `<div style="font-size:10px;color:#94A3B8;">${s}</div>`;
    }).join('');
    if (xEl) xEl.innerHTML = days
        .filter((_, i) => i % 5 === 0 || i === dim - 1)
        .map(d => `<div style="font-size:10px;color:#94A3B8;">${d.date.slice(8).replace(/^0/,'')}</div>`).join('');

    svgEl.innerHTML = `
        <defs><linearGradient id="pgr" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#2563EB" stop-opacity=".2"/>
            <stop offset="100%" stop-color="#2563EB" stop-opacity="0"/>
        </linearGradient></defs>
        <path d="${mkPath(thisPoints,active)} L${toX(active).toFixed(1)},${chartH} L0,${chartH} Z" fill="url(#pgr)"/>
        <path d="${mkPath(tgtPoints,dim-1)}" fill="none" stroke="#F97316" stroke-width="1.5" stroke-dasharray="5,4" opacity=".8"/>
        <path d="${mkPath(pmPoints,dim-1)}" fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-dasharray="5,4" opacity=".7"/>
        <path d="${mkPath(thisPoints,active)}" fill="none" stroke="#2563EB" stroke-width="2"/>`;

    const fmtM = v => v >= 1e6 ? `¥${(v/1e6).toFixed(2)}M` : `¥${v.toLocaleString()}`;
    const cur = thisPoints[active] || 0;

    const pe = document.getElementById('profitCsPace');
    if (pe) {
        const d = cur - pmPoints[active];
        const p = pmPoints[active] > 0 ? Math.abs(Math.round(d / pmPoints[active] * 100)) : 0;
        pe.textContent = `${d>=0?'+':'-'}${fmtM(Math.abs(d))} (${p}%)`;
    }
    const te = document.getElementById('profitCsTarget');
    if (te) {
        const g = cur - tgtPoints[active];
        const p = tgtPoints[active] > 0 ? Math.abs(Math.round(g / tgtPoints[active] * 100)) : 0;
        te.textContent = `${g>=0?'+':'-'}${fmtM(Math.abs(g))} ${g>=0?'↑':'↓'}${p}%`;
    }
    const ee = document.getElementById('profitCsEom');
    const es = document.getElementById('profitCsEomSub');
    if (ee) {
        const proj = cur > 0 && active >= 0 ? Math.round(cur / (active + 1) * dim) : 0;
        ee.textContent = fmtM(proj);
        if (es) { es.textContent = proj >= TARGET ? '目標達成 ✅' : '目標未達 📉'; es.style.color = proj >= TARGET ? '#10B981' : '#EF4444'; }
    }
}

async function loadBreakdown(month) {
    try {
        const resp = await fetch(`/api/profit/breakdown?month=${month}`);
        const data = await resp.json();
        renderBreakdownChart(data);
    } catch (e) { console.error(e); }
}

function renderBreakdownChart(data) {
    const c = data.costs;
    const avgRate = data.avg_exchange_rate || 150;
    const labels = ['仕入原価', '国内送料', '国際送料', 'eBay手数料', 'Payoneer', 'その他', '固定費'];
    const values = [
        c.source_cost_jpy,
        c.domestic_shipping_jpy,
        c.intl_shipping_jpy,
        Math.round(c.ebay_fees_usd * avgRate),
        Math.round(c.payoneer_fees_usd * avgRate),
        c.other_cost_jpy,
        c.fixed_cost_jpy,
    ];

    if (breakdownChart) breakdownChart.destroy();

    const options = {
        chart: {
            type: 'donut',
            height: 200,
            fontFamily: chartFont,
        },
        colors: [chartColors.brand, chartColors.purple, chartColors.warning, chartColors.error, chartColors.indigo, chartColors.gray400, chartColors.gray500],
        series: values,
        labels: labels,
        legend: {
            position: 'right',
            fontFamily: chartFont,
            fontSize: '12px',
            labels: { colors: chartColors.gray500 },
        },
        dataLabels: { enabled: false },
        plotOptions: {
            pie: {
                donut: {
                    size: '65%',
                    labels: {
                        show: true,
                        total: {
                            show: true,
                            label: '合計',
                            fontFamily: chartFont,
                            fontSize: '14px',
                            color: chartColors.gray500,
                            formatter: w => '\u00a5' + w.globals.seriesTotals.reduce((a, b) => a + b, 0).toLocaleString(),
                        },
                    },
                },
            },
        },
        stroke: { width: 0 },
        tooltip: {
            style: { fontFamily: chartFont },
            y: { formatter: v => '\u00a5' + v.toLocaleString() },
        },
    };

    breakdownChart = new ApexCharts(document.getElementById('breakdownChart'), options);
    breakdownChart.render();

    // 費用一覧テーブル
    const listEl = document.getElementById('costBreakdownList');
    if (listEl) {
        const total = values.reduce((a, b) => a + b, 0);
        const colors = ['#2563EB','#7C3AED','#F59E0B','#EF4444','#6366F1','#94A3B8','#64748B'];
        listEl.innerHTML = '<table style="width:100%;border-collapse:collapse;">' +
            values.map((v, i) => {
                if (v === 0) return '';
                const pct = total > 0 ? (v / total * 100).toFixed(1) : '0';
                return `<tr style="border-bottom:1px solid #F1F5F9;">
                    <td style="padding:4px 0;font-size:12px;color:#1e293b;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${colors[i]};margin-right:6px;vertical-align:middle;"></span>${labels[i]}</td>
                    <td style="padding:4px 0;font-size:13px;font-weight:700;color:#1e293b;text-align:right;">¥${v.toLocaleString()}</td>
                    <td style="padding:4px 0;font-size:11px;color:#94A3B8;text-align:right;width:40px;">${pct}%</td>
                </tr>`;
            }).join('') +
            `<tr><td style="padding:5px 0;font-size:12px;font-weight:700;color:#64748B;">合計</td>
                 <td style="padding:5px 0;font-size:13px;font-weight:800;color:#0F172A;text-align:right;">¥${total.toLocaleString()}</td>
                 <td style="padding:5px 0;font-size:11px;color:#94A3B8;text-align:right;">100%</td></tr>` +
            '</table>';
    }
}

// ── 取引一覧 ──────────────────────────────────────────
function sortTransactions(col) {
    if (txSortCol === col) {
        txSortDir = txSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        txSortCol = col;
        txSortDir = 'desc';
    }
    renderTransactions(txRawRecords);
    updateTxSortIcons();
}

function updateTxSortIcons() {
    document.querySelectorAll('#txTable thead th[data-sort]').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (!icon) return;
        if (th.dataset.sort === txSortCol) {
            icon.textContent = txSortDir === 'asc' ? ' ▲' : ' ▼';
            icon.style.opacity = '1';
        } else {
            icon.textContent = ' ⇅';
            icon.style.opacity = '0.3';
        }
    });
}

function compareTx(a, b) {
    let va, vb;
    switch (txSortCol) {
        case 'sold_at':       va = a.sold_at || ''; vb = b.sold_at || ''; break;
        case 'title':         va = a.title || ''; vb = b.title || ''; break;
        case 'sale_price':    va = a.sale_price_usd; vb = b.sale_price_usd; break;
        case 'source_cost':   va = a.source_cost_jpy; vb = b.source_cost_jpy; break;
        case 'net_profit':    va = a.net_profit_jpy; vb = b.net_profit_jpy; break;
        case 'margin':        va = a.profit_margin_pct; vb = b.profit_margin_pct; break;
        default:              va = a.sold_at || ''; vb = b.sold_at || '';
    }
    if (typeof va === 'string') {
        const cmp = va.localeCompare(vb);
        return txSortDir === 'asc' ? cmp : -cmp;
    }
    return txSortDir === 'asc' ? va - vb : vb - va;
}

async function loadTransactions(fromDate, toDate) {
    const month = document.getElementById('txMonth').value;
    const tbody = document.getElementById('txBody');
    let url = `/api/sales/records?month=${month}`;
    if (fromDate) url += `&from_date=${fromDate}`;
    if (toDate) url += `&to_date=${toDate}`;

    try {
        const resp = await fetch(url);
        const records = await resp.json();
        txCache = {};
        records.forEach(r => txCache[r.id] = r);
        txRawRecords = records;

        if (!records.length) {
            tbody.innerHTML = '<tr><td colspan="14" class="empty-state">取引データなし</td></tr>';
            return;
        }
        renderTransactions(records);
        updateTxSortIcons();
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="14" class="empty-state">読み込みエラー</td></tr>';
        console.error(e);
    }
}

function platBadge(name) {
    const m = {
        'メルカリ':           {bg:'#FFE4E6', color:'#BE123C'},
        'メルカリShops':      {bg:'#FFE4E6', color:'#BE123C'},
        '楽天':               {bg:'#CCFBF1', color:'#0F766E'},
        'Amazon':             {bg:'#FFEDD5', color:'#9A3412'},
        'ヤフオク':           {bg:'#FEF9C3', color:'#854D0E'},
        'ヤフーショッピング': {bg:'#DCFCE7', color:'#166534'},
        'Yahooフリマ':        {bg:'#E0F2FE', color:'#075985'},
        'ラクマ':             {bg:'#EDE9FE', color:'#5B21B6'},
        'まんだらけ':         {bg:'#FAE8FF', color:'#86198F'},
        '駿河屋':             {bg:'#DBEAFE', color:'#1E40AF'},
        'デジマート':         {bg:'#E0E7FF', color:'#3730A3'},
        'GEO':                {bg:'#D1FAE5', color:'#065F46'},
        'セカンドストリート': {bg:'#CFFAFE', color:'#155E75'},
        'ネットモール(OFFモール)': {bg:'#FEF3C7', color:'#92400E'},
        'トレファク':         {bg:'#FCE7F3', color:'#9D174D'},
    };
    const s = m[name] || {bg:'#E2E8F0', color:'#334155'};
    return `<span class="plat-badge" style="background:${s.bg};color:${s.color}">${esc(name)}</span>`;
}

function renderTransactions(records) {
        const tbody = document.getElementById('txBody');
        const sorted = [...records].sort(compareTx);
        tbody.innerHTML = sorted.map(r => {
            const shipTotal = r.shipping_cost_jpy + r.intl_shipping_cost_jpy;
            const feesTotal = r.ebay_fees_usd + r.payoneer_fee_usd;
            const profitColor = r.net_profit_jpy >= 0 ? 'var(--success-500)' : 'var(--error-500)';
            const profitWithRefund = r.net_profit_jpy + (r.consumption_tax_jpy || 0);
            const refundColor = profitWithRefund >= 0 ? 'var(--success-500)' : 'var(--error-500)';
            const marginColor = r.profit_margin_pct >= 0 ? 'var(--success-500)' : 'var(--error-500)';
            const proc = r.procurement;

            const thumb = r.image_url
                ? `<img src="${esc(r.image_url)}" style="width:32px;height:32px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-right:6px;" onerror="this.style.display='none'">`
                : '<span style="display:inline-block;width:32px;height:32px;background:var(--gray-100);border-radius:4px;vertical-align:middle;margin-right:6px;"></span>';

            const progress = buildProgressBadge(r);
            const mpBadge = buildMarketplaceBadge(r);

            const detailHtml = `
                <tr id="detail-${r.id}" style="display:none;">
                    <td colspan="14" style="padding:10px 14px;background:var(--gray-50);font-size:11px;">
                        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
                            <div>
                                <div style="font-weight:600;margin-bottom:4px;color:var(--gray-500);">eBay情報</div>
                                <div>注文番号: <span style="color:var(--gray-800);">${r.order_id || '-'}</span></div>
                                <div>Item ID: ${r.item_id ? `<a href="https://www.ebay.com/itm/${r.item_id}" target="_blank" style="color:var(--brand-500);">${r.item_id} ↗</a>` : '-'}</div>
                                <div>SKU: <span style="color:var(--gray-800);">${r.sku || '-'}</span></div>
                                <div>追跡番号: <span style="color:var(--gray-800);">${r.tracking_number || '-'}</span></div>
                                <div>為替: <span style="color:var(--gray-800);">$1 = \u00a5${r.exchange_rate ? r.exchange_rate.toFixed(2) : '-'}</span></div>
                                <div>発送期限: <span style="color:${r.ship_by_date ? 'var(--gray-800)' : 'var(--gray-400)'};">${r.ship_by_date || '未設定'}</span></div>
                            </div>
                            <div>
                                <div style="font-weight:600;margin-bottom:4px;color:var(--gray-500);">費用内訳</div>
                                <div>仕入原価: \u00a5${r.source_cost_jpy.toLocaleString()}</div>
                                <div>消費税(還付): \u00a5${r.consumption_tax_jpy.toLocaleString()}</div>
                                <div>国内送料: \u00a5${r.shipping_cost_jpy.toLocaleString()}</div>
                                <div>国際送料: \u00a5${r.intl_shipping_cost_jpy.toLocaleString()} ${r.shipping_method ? '<span style="color:var(--brand-500);">(' + r.shipping_method + ')</span>' : ''}</div>
                                <div>関税: \u00a5${(r.customs_duty_jpy || 0).toLocaleString()}</div>
                                <div>eBay手数料: $${r.ebay_fees_usd.toFixed(2)} (\u00a5${r.fees_jpy ? r.fees_jpy.toLocaleString() : '-'})</div>
                                <div>Payoneer手数料: $${r.payoneer_fee_usd.toFixed(2)}</div>
                                <div>その他: \u00a5${r.other_cost_jpy.toLocaleString()} ${r.cost_note ? '<span style="color:var(--gray-400);">(' + esc(r.cost_note) + ')</span>' : ''}</div>
                            </div>
                            <div>
                                <div style="font-weight:600;margin-bottom:4px;color:var(--gray-500);">仕入れ情報</div>
                                ${proc ? `
                                    <div>購入日: ${proc.purchase_date || '-'}</div>
                                    <div>仕入価格: \u00a5${proc.purchase_price_jpy.toLocaleString()}</div>
                                    <div>消費税: \u00a5${(proc.consumption_tax_jpy || 0).toLocaleString()}</div>
                                    <div>合計: \u00a5${proc.total_cost_jpy.toLocaleString()}</div>
                                    <div>仕入先: ${proc.platform || '-'}</div>
                                    ${proc.url ? '<div><a href="' + esc(proc.url) + '" target="_blank" style="color:var(--brand-500);">仕入先リンク ↗</a></div>' : ''}
                                ` : '<div style="color:var(--gray-400);">仕入れデータなし</div>'}
                                ${r.inventory_item_id ? '<div style="margin-top:6px;"><a href="/procurement" onclick="localStorage.setItem(\'highlight_stock\',\'' + r.inventory_item_id + '\');" style="color:var(--brand-500);font-weight:600;font-size:13px;">📦 仕入れ台帳を表示 ↗</a></div>' : ''}
                            </div>
                        </div>
                    </td>
                </tr>`;

            const isUnordered = !r.progress || r.progress === '未注文';
            const rowBg = isUnordered ? 'background:#FEF2F2;' : '';

            return `
                <tr class="proc-row" style="cursor:pointer;${rowBg}" onclick="toggleDetail(${r.id})">
                    <td style="width:24px;text-align:center;font-size:11px;color:var(--gray-400);" id="chevron-${r.id}">\u25B6</td>
                    <td style="white-space:nowrap;font-size:12px;">${r.sold_at}</td>
                    <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;" title="${esc(r.title)}">${thumb}${esc(r.title.slice(0, 30))}</td>
                    <td style="font-size:12px;white-space:nowrap;">${esc(r.buyer_name || '-')}<br>${mpBadge}</td>
                    <td style="font-size:12px;">$${r.sale_price_usd.toFixed(0)}<br><span style="font-size:11px;color:var(--gray-400);">\u00a5${(r.sale_price_jpy || 0).toLocaleString()}</span></td>
                    <td style="font-size:12px;">\u00a5${r.source_cost_jpy.toLocaleString()}${proc && proc.platform ? '<br>' + platBadge(proc.platform) : ''}</td>
                    <td style="font-size:12px;">\u00a5${shipTotal.toLocaleString()}${r.shipping_method ? '<br><span style="font-size:11px;color:var(--gray-400);">' + r.shipping_method + '</span>' : ''}</td>
                    <td style="font-size:12px;">${r.customs_duty_jpy ? '\u00a5' + r.customs_duty_jpy.toLocaleString() : '-'}</td>
                    <td style="font-size:12px;">$${feesTotal.toFixed(0)}<br><span style="font-size:11px;color:var(--gray-400);">\u00a5${(r.fees_jpy || 0).toLocaleString()}</span></td>
                    <td style="font-weight:600;color:${profitColor};font-size:13px;">\u00a5${r.net_profit_jpy.toLocaleString()}<br><span style="font-size:11px;">$${r.net_profit_usd.toFixed(0)}</span></td>
                    <td style="font-weight:600;color:${refundColor};font-size:13px;">\u00a5${profitWithRefund.toLocaleString()}${r.consumption_tax_jpy ? '<br><span style="font-size:11px;color:var(--gray-400);">+\u00a5' + r.consumption_tax_jpy.toLocaleString() + '</span>' : ''}</td>
                    <td style="color:${marginColor};font-size:12px;">${r.profit_margin_pct.toFixed(1)}%</td>
                    <td>${progress}</td>
                    <td><button class="proc-edit-btn" onclick="event.stopPropagation();openEditModal(${r.id})">Edit</button></td>
                </tr>
                ${detailHtml}`;
        }).join('');
}

// ── 進捗バッジ (TailAdmin pill style) ──
function buildProgressBadge(r) {
    const status = r.progress || '未注文';
    const styles = {
        '未注文':       'background:#6B7280;color:#fff;',
        '注文済':       'background:#007AFF;color:#fff;',
        '発送済':       'background:#FF9500;color:#fff;',
        '納品済':       'background:#34C759;color:#fff;',
        'キャンセル':     'background:#FF3B30;color:#fff;',
        '返品・返金':     'background:#FF3B30;color:#fff;',
        '返品・一部返金':  'background:#D97706;color:#fff;',
        '返品なし返金':   'background:#DC2626;color:#fff;',
        '未着返金':      'background:#B91C1C;color:#fff;',
    };
    const s = styles[status] || 'background:#6B7280;color:#fff;';
    return `<span style="display:inline-block;padding:2px 8px;border-radius:9999px;font-size:10px;font-weight:600;${s}white-space:nowrap;">${esc(status)}</span>`;
}

function buildMarketplaceBadge(r) {
    const purchase = r.marketplace || '';
    const listing = r.listing_site || '';
    if (!purchase && !listing) return '';
    const flags = { US:'🇺🇸', UK:'🇬🇧', DE:'🇩🇪', FR:'🇫🇷', CA:'🇨🇦', AU:'🇦🇺', IT:'🇮🇹', ES:'🇪🇸', BE:'🇧🇪', AT:'🇦🇹', SE:'🇸🇪', NO:'🇳🇴', FI:'🇫🇮', AE:'🇦🇪' };
    if (listing && purchase && listing !== purchase) {
        return `<span style="font-size:10px;" title="出品:eBay ${listing} → 購入:eBay ${purchase}">${flags[listing]||''}${listing}→${flags[purchase]||''}${purchase}</span>`;
    }
    const mp = purchase || listing;
    return `<span style="font-size:10px;" title="eBay ${mp}">${flags[mp]||''}${mp}</span>`;
}

function toggleDetail(id) {
    const row = document.getElementById('detail-' + id);
    const chevron = document.getElementById('chevron-' + id);
    if (!row) return;
    if (row.style.display === 'none') {
        row.style.display = '';
        chevron.textContent = '\u25BC';
    } else {
        row.style.display = 'none';
        chevron.textContent = '\u25B6';
    }
}

// ── 編集モーダル ──────────────────────────────────────
let txCache = {};
async function openEditModal(id) {
    if (!txCache[id]) {
        const month = document.getElementById('txMonth').value;
        const resp = await fetch(`/api/sales/records?month=${month}`);
        const records = await resp.json();
        records.forEach(r => txCache[r.id] = r);
    }
    const r = txCache[id];
    if (!r) return;

    document.getElementById('editId').value = id;
    document.getElementById('editIntlShip').value = r.intl_shipping_cost_jpy || '';
    document.getElementById('editShipMethod').value = r.shipping_method || '';
    document.getElementById('editSourceCost').value = r.source_cost_jpy || '';
    document.getElementById('editTax').value = r.consumption_tax_jpy || '';
    document.getElementById('editPayRate').value = r.payoneer_rate || '';
    document.getElementById('editReceived').value = r.received_jpy || '';
    document.getElementById('editCustomsDuty').value = r.customs_duty_jpy || '';
    document.getElementById('editOther').value = r.other_cost_jpy || '';
    document.getElementById('editNote').value = r.cost_note || '';
    document.getElementById('editProgress').value = r.progress || '';

    const thumb = r.image_url
        ? `<img src="${esc(r.image_url)}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;margin-right:8px;vertical-align:middle;" onerror="this.style.display='none'">`
        : '';
    document.getElementById('editSaleInfo').innerHTML = `
        <div style="display:flex;align-items:center;">
            ${thumb}
            <div>
                <div style="font-weight:600;">${esc(r.title.slice(0, 50))}</div>
                <div style="color:var(--gray-500);margin-top:2px;">$${r.sale_price_usd.toFixed(2)} | ${r.sold_at} | ${esc(r.buyer_name || '-')} ${r.marketplace ? '(' + r.marketplace + ')' : ''} ${r.item_id ? '| <a href="https://www.ebay.com/itm/' + r.item_id + '" target="_blank" style="color:var(--brand-500);">#' + r.item_id + '</a>' : ''}</div>
            </div>
        </div>`;

    const proc = r.procurement;
    document.getElementById('editProcId').value = proc ? proc.id : '';
    document.getElementById('editProcPlatform').value = proc ? (proc.platform || '') : '';
    document.getElementById('editProcPrice').value = proc ? proc.purchase_price_jpy : '';
    document.getElementById('editProcDate').value = proc ? (proc.purchase_date || '') : '';
    document.getElementById('editProcUrl').value = proc ? (proc.url || '') : '';
    document.getElementById('editProcStatus').textContent = proc ? `ID #${proc.id} (${proc.status})` : 'New';

    document.getElementById('editModal').style.display = 'flex';
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
}

async function saveEdit() {
    const id = document.getElementById('editId').value;
    const r = txCache[id];
    const body = {};
    const intlShip = document.getElementById('editIntlShip').value;
    const shipMethod = document.getElementById('editShipMethod').value;
    const sourceCost = document.getElementById('editSourceCost').value;
    const tax = document.getElementById('editTax').value;
    const payRate = document.getElementById('editPayRate').value;
    const received = document.getElementById('editReceived').value;
    const customsDuty = document.getElementById('editCustomsDuty').value;
    const other = document.getElementById('editOther').value;
    const note = document.getElementById('editNote').value;

    if (intlShip !== '') body.intl_shipping_cost_jpy = parseInt(intlShip) || 0;
    if (shipMethod) body.shipping_method = shipMethod;
    if (sourceCost !== '') body.source_cost_jpy = parseInt(sourceCost) || 0;
    if (tax !== '') body.consumption_tax_jpy = parseInt(tax) || 0;
    if (payRate !== '') body.payoneer_rate = parseFloat(payRate) || 0;
    if (received !== '') body.received_jpy = parseInt(received) || 0;
    if (customsDuty !== '') body.customs_duty_jpy = parseInt(customsDuty) || 0;
    if (other !== '') body.other_cost_jpy = parseInt(other) || 0;
    body.cost_note = note;
    const progress = document.getElementById('editProgress').value;
    body.progress = progress;

    try {
        const resp = await fetch(`/api/sales/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const procId = document.getElementById('editProcId').value;
        const procPlatform = document.getElementById('editProcPlatform').value;
        const procPrice = document.getElementById('editProcPrice').value;
        const procDate = document.getElementById('editProcDate').value;
        const procUrl = document.getElementById('editProcUrl').value;

        if (procPlatform && procPrice) {
            const procBody = {
                platform: procPlatform,
                title: r ? r.title : '',
                sku: r ? r.sku : '',
                purchase_price_jpy: parseInt(procPrice) || 0,
                consumption_tax_jpy: parseInt(tax) || 0,
                purchase_date: procDate,
                url: procUrl,
                status: 'listed',
            };

            if (procId) {
                await fetch(`/api/procurements/${procId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(procBody),
                });
            } else {
                await fetch('/api/procurements', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(procBody),
                });
            }
        }

        if (resp.ok) {
            closeEditModal();
            txCache = {};
            loadTransactions();
            const activeBtn = document.querySelector('.filter-pills .pill.active');
            const months = activeBtn ? parseInt(activeBtn.textContent) : 3;
            loadSummary(months);
        }
    } catch (e) { console.error(e); }
}

// ── 固定費 ────────────────────────────────────────────
function showAddExpense() {
    const form = document.getElementById('expenseForm');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function saveExpense() {
    const now = new Date();
    const ym = now.toISOString().slice(0, 7);
    const body = {
        year_month: ym,
        category: document.getElementById('expCategory').value,
        description: document.getElementById('expDesc').value,
        amount_jpy: parseInt(document.getElementById('expAmount').value) || 0,
        is_recurring: document.getElementById('expRecurring').checked ? 1 : 0,
    };
    try {
        await fetch('/api/expenses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        document.getElementById('expenseForm').style.display = 'none';
        document.getElementById('expDesc').value = '';
        document.getElementById('expAmount').value = '';
        loadExpenses();
    } catch (e) { console.error(e); }
}

async function loadExpenses() {
    const now = new Date();
    const ym = now.toISOString().slice(0, 7);
    const tbody = document.getElementById('expBody');
    try {
        const resp = await fetch(`/api/expenses?month=${ym}`);
        const expenses = await resp.json();
        if (!expenses.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">今月の固定費なし</td></tr>';
            return;
        }
        const catLabels = { store_subscription: 'Store', tools: 'Tools', packaging: 'Packaging', storage: 'Storage', insurance: 'Insurance', other: 'Other' };
        tbody.innerHTML = expenses.map(e => `
            <tr>
                <td><span class="badge purchased">${catLabels[e.category] || e.category}</span></td>
                <td>${esc(e.description)}</td>
                <td>\u00a5${e.amount_jpy.toLocaleString()}</td>
                <td>${e.is_recurring ? '<span style="color:var(--brand-500);">Monthly</span>' : 'One-time'}</td>
                <td><button class="btn btn-sm btn-outline" onclick="deleteExpense(${e.id})" style="padding:2px 8px;font-size:11px;color:var(--error-500);border-color:var(--error-500);">Del</button></td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Error</td></tr>';
    }
}

async function deleteExpense(id) {
    if (!confirm('Delete this expense?')) return;
    await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
    loadExpenses();
}

// ── エクスポート ──────────────────────────────────────
function toggleExportMenu() {
    const menu = document.getElementById('exportMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('#exportBtn') && !e.target.closest('#exportMenu')) {
        document.getElementById('exportMenu').style.display = 'none';
    }
});

function exportCSV(type) {
    const year = document.getElementById('exportYear').value;
    window.location.href = `/api/export/tax-report?type=${type}&year=${year}`;
    document.getElementById('exportMenu').style.display = 'none';
}

// ── CPaaS送料インポート ──────────────────────────────────
function toggleShippingImport() {
    const form = document.getElementById('shippingImportForm');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function uploadShippingCsv() {
    const fileInput = document.getElementById('shippingCsvFile');
    const resultDiv = document.getElementById('shippingImportResult');
    const btn = document.getElementById('uploadShipBtn');

    if (!fileInput.files.length) {
        resultDiv.style.display = 'block';
        resultDiv.style.background = 'var(--error-50)';
        resultDiv.style.color = 'var(--error-600)';
        resultDiv.textContent = 'CSVファイルを選択してください';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Importing...';
    resultDiv.style.display = 'none';

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const resp = await fetch('/api/shipping/import', { method: 'POST', body: formData });
        const data = await resp.json();

        resultDiv.style.display = 'block';
        if (data.matched > 0) {
            resultDiv.style.background = 'var(--success-50)';
            resultDiv.style.color = 'var(--success-600)';
        } else {
            resultDiv.style.background = 'var(--warning-50)';
            resultDiv.style.color = 'var(--warning-600)';
        }

        let html = `<strong>\u2713 ${data.matched}件マッチ</strong> / ${data.skipped}件スキップ`;
        if (data.not_found_count > 0) {
            html += ` / <span style="color:var(--error-500);">${data.not_found_count}件未マッチ</span>`;
            html += '<div style="margin-top:6px;max-height:120px;overflow-y:auto;font-size:11px;">';
            for (const nf of data.not_found) {
                html += `<div style="padding:2px 0;">${nf.tracking} \u2014 ${esc(nf.product)} (\u00a5${nf.total.toLocaleString()})</div>`;
            }
            html += '</div>';
        }
        resultDiv.innerHTML = html;

        if (data.matched > 0) {
            txCache = {};
            loadTransactions();
            const activeBtn = document.querySelector('.filter-pills .pill.active');
            const months = activeBtn ? parseInt(activeBtn.textContent) : 3;
            loadSummary(months);
        }
    } catch (e) {
        resultDiv.style.display = 'block';
        resultDiv.style.background = 'var(--error-50)';
        resultDiv.style.color = 'var(--error-600)';
        resultDiv.textContent = 'Error: ' + e.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Import';
    }
}

async function backfillTracking() {
    const btn = document.getElementById('backfillBtn');
    const resultDiv = document.getElementById('shippingImportResult');
    btn.disabled = true;
    btn.textContent = 'Syncing...';
    resultDiv.style.display = 'none';

    try {
        const resp = await fetch('/api/shipping/backfill-tracking', { method: 'POST' });
        const data = await resp.json();
        resultDiv.style.display = 'block';
        resultDiv.style.background = 'var(--brand-50)';
        resultDiv.style.color = 'var(--brand-600)';
        resultDiv.innerHTML = `<strong>${data.updated}件</strong>の追跡番号を同期 (${data.orders_fetched}件のeBay注文から / 未設定: ${data.total_empty}件)`;
    } catch (e) {
        resultDiv.style.display = 'block';
        resultDiv.style.background = 'var(--error-50)';
        resultDiv.style.color = 'var(--error-600)';
        resultDiv.textContent = 'Error: ' + e.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Sync Tracking from eBay';
    }
}

async function quickSyncSales() {
    const btn = document.getElementById('quickSyncBtn');
    const resultSpan = document.getElementById('quickSyncResult');
    btn.disabled = true;
    btn.textContent = '同期中...';
    resultSpan.style.display = 'none';
    try {
        const resp = await fetch('/api/sales/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ days: 30 }),
        });
        const data = await resp.json();
        resultSpan.style.display = '';
        resultSpan.style.color = 'var(--success-600)';
        resultSpan.textContent = `✓ ${data.new_sales_recorded ?? 0}件追加 (${data.orders_fetched ?? 0}件取得)`;
        loadSummary(parseInt(document.querySelector('.filter-pills .pill.active')?.dataset?.months || '3'));
        loadTransactions();
    } catch (e) {
        resultSpan.style.display = '';
        resultSpan.style.color = 'var(--error-600)';
        resultSpan.textContent = 'エラー: ' + e.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'eBay同期';
    }
}

async function syncAllSales() {
    const btn = document.getElementById('syncAllBtn');
    const resultDiv = document.getElementById('shippingImportResult');

    const fromDate = prompt('開始日 (YYYY-MM-DD):', '2024-01-01');
    if (!fromDate) return;

    btn.disabled = true;
    btn.textContent = 'Syncing...';
    resultDiv.style.display = 'block';
    resultDiv.style.background = 'var(--brand-50)';
    resultDiv.style.color = 'var(--brand-600)';
    resultDiv.textContent = 'eBay Fulfillment APIから全注文を取得中... (数分かかる場合があります)';

    try {
        const resp = await fetch('/api/sales/sync-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from_date: fromDate }),
        });
        const data = await resp.json();
        resultDiv.style.background = 'var(--success-50)';
        resultDiv.style.color = 'var(--success-600)';
        resultDiv.innerHTML = `<strong>${data.orders_fetched}件</strong>の注文を取得 \u2192 <strong>${data.new_records}件</strong>を新規追加 (${data.skipped_existing}件は既存)`;
        loadSummary(12);
        loadTransactions();
    } catch (e) {
        resultDiv.style.background = 'var(--error-50)';
        resultDiv.style.color = 'var(--error-600)';
        resultDiv.textContent = 'Error: ' + e.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Sync All Orders (Full)';
    }
}

// ── 日次チャート・トップ商品 ────────────────────────
async function loadDailyAnalytics(days) {
    try {
        const data = await (await fetch(`/api/sales/analytics?days=${days}`)).json();
        _profitTrendData = data.daily_trend || [];
        renderProfitDailyChart(_profitTrendData);
        renderProfitMonthlyChart(_profitTrendData, _profitSummaryData);

        // Top Products
        const tp = data.top_products || [];
        const container = document.getElementById('topProducts');
        if (tp.length) {
            let html = '<table class="proc-table"><thead><tr><th style="width:44px;"></th><th>商品</th><th>売上</th><th>利益</th><th>数</th></tr></thead><tbody>';
            for (const p of tp.slice(0, 10)) {
                const thumb = p.image_url
                    ? `<img src="${esc(p.image_url)}" style="width:36px;height:36px;object-fit:cover;border-radius:5px;display:block;" onerror="this.style.display='none'">`
                    : `<div style="width:36px;height:36px;border-radius:5px;background:#F1F5F9;"></div>`;
                html += `<tr class="proc-row">
                    <td style="padding:6px 8px;">${thumb}</td>
                    <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(p.title)}</td>
                    <td>$${(p.revenue_usd||0).toLocaleString(undefined,{maximumFractionDigits:0})}</td>
                    <td style="color:${(p.profit_usd||0)>=0?'#10B981':'#EF4444'};">$${(p.profit_usd||0).toLocaleString(undefined,{maximumFractionDigits:0})}</td>
                    <td>${p.sales_count}</td>
                </tr>`;
            }
            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<div class="empty-state">データなし</div>';
        }
    } catch (e) {
        console.error('Daily analytics error:', e);
    }
}

// ── ユーティリティ ────────────────────────────────────
function esc(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
