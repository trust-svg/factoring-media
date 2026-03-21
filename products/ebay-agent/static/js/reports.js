/* Reports Page — eBay Agent Hub */

let currentTab = 'weekly';
let currentReport = null;

// ── 初期化 ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadReportList();
});

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
    loadReportList();
}

async function loadReportList() {
    try {
        const resp = await fetch(`/api/reports?type=${currentTab}`);
        const data = await resp.json();
        const select = document.getElementById('reportSelect');
        select.innerHTML = '<option value="">-- Choose --</option>';
        (data.reports || []).forEach(r => {
            const kpi = r.kpi || {};
            const label = `${r.period_label}  ($${(kpi.total_revenue_usd || 0).toFixed(0)} / ${kpi.total_orders || 0} orders)`;
            select.innerHTML += `<option value="${r.id}">${label}</option>`;
        });
        // 最新を自動選択
        if (data.reports && data.reports.length > 0) {
            select.value = data.reports[0].id;
            loadReport(data.reports[0].id);
        } else {
            document.getElementById('reportContent').style.display = 'none';
            document.getElementById('emptyState').style.display = 'flex';
        }
    } catch (e) {
        console.error('Failed to load reports:', e);
    }
}

async function loadReport(reportId) {
    if (!reportId) {
        document.getElementById('reportContent').style.display = 'none';
        document.getElementById('emptyState').style.display = 'flex';
        return;
    }
    try {
        const resp = await fetch(`/api/reports/${reportId}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        currentReport = data;
        renderReport(data);
    } catch (e) {
        console.error('Failed to load report:', e);
    }
}

async function generateReport() {
    const btn = document.getElementById('generateBtn');
    btn.disabled = true;
    btn.innerHTML = '<span>Generating...</span>';
    try {
        const resp = await fetch(`/api/reports/generate`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type: currentTab}),
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        await loadReportList();
        if (data.id) {
            document.getElementById('reportSelect').value = data.id;
            loadReport(data.id);
        }
    } catch (e) {
        console.error('Generate failed:', e);
        alert('Report generation failed: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:16px;height:16px"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" /></svg><span data-en="Generate Now" data-ja="今すぐ生成">Generate Now</span>`;
    }
}

// ── レンダリング ────────────────────────────────────────

function renderReport(data) {
    document.getElementById('reportContent').style.display = 'block';
    document.getElementById('emptyState').style.display = 'none';

    renderKPI(data.kpi);
    renderComparison(data.comparison);
    renderTopProducts(data.top_products, 'topProductsTable');
    renderTopProducts(data.worst_products, 'worstProductsTable', true);
    renderCategoryChart(data.categories);
    renderCountryChart(data.buyer_countries);
    renderInventory(data.inventory);
    renderProcurement(data.procurement);
    renderPriceComp(data.price_competitiveness);
    renderSuggestions(data.suggestions);
    renderToolSuggestions(data.tool_suggestions);
}

function renderKPI(kpi) {
    const grid = document.getElementById('kpiGrid');
    grid.innerHTML = `
        ${kpiCard('Revenue', `$${fmt(kpi.total_revenue_usd)}`, 'var(--brand-500)')}
        ${kpiCard('Profit', `$${fmt(kpi.total_profit_usd)}`, 'var(--success-500)')}
        ${kpiCard('Orders', kpi.total_orders, 'var(--purple-500)')}
        ${kpiCard('Avg Order', `$${fmt(kpi.avg_order_value_usd)}`, 'var(--warning-500)')}
        ${kpiCard('Margin', `${kpi.avg_margin_pct}%`, kpi.avg_margin_pct >= 20 ? 'var(--success-500)' : 'var(--error-500)')}
        ${kpiCard('eBay Fees', `$${fmt(kpi.total_ebay_fees_usd)}`, 'var(--gray-500)')}
    `;
}

function kpiCard(label, value, color) {
    return `<div class="kpi-card">
        <div class="kpi-value" style="color:${color}">${value}</div>
        <div class="kpi-label">${label}</div>
    </div>`;
}

function renderComparison(comp) {
    const grid = document.getElementById('comparisonGrid');
    const labels = {
        total_orders: 'Orders', total_revenue_usd: 'Revenue',
        total_profit_usd: 'Profit', avg_margin_pct: 'Margin',
    };
    let html = '';
    for (const [key, label] of Object.entries(labels)) {
        const d = comp[key] || {};
        const change = d.change_pct || 0;
        const arrow = change >= 0 ? '↑' : '↓';
        const cls = change >= 0 ? 'positive' : 'negative';
        const prev = key.includes('pct') ? `${d.previous || 0}%` : (key === 'total_orders' ? d.previous || 0 : `$${fmt(d.previous || 0)}`);
        const curr = key.includes('pct') ? `${d.current || 0}%` : (key === 'total_orders' ? d.current || 0 : `$${fmt(d.current || 0)}`);
        html += `<div class="comp-card">
            <div class="comp-label">${label}</div>
            <div class="comp-values">${prev} → ${curr}</div>
            <div class="comp-change ${cls}">${arrow} ${Math.abs(change)}%</div>
        </div>`;
    }
    grid.innerHTML = html;
}

function renderTopProducts(products, containerId, isWorst = false) {
    const el = document.getElementById(containerId);
    if (!products || !products.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:12px">No data</p>';
        return;
    }
    let html = '<table class="report-table"><thead><tr><th>#</th><th>Product</th><th>Revenue</th><th>Profit</th><th>Margin</th></tr></thead><tbody>';
    products.forEach((p, i) => {
        const marginCls = p.margin_pct < 10 ? 'negative' : (p.margin_pct >= 25 ? 'positive' : '');
        html += `<tr>
            <td>${i + 1}</td>
            <td class="product-title">${p.title}</td>
            <td>$${fmt(p.revenue_usd)}</td>
            <td class="${p.profit_usd < 0 ? 'negative' : ''}">${p.profit_usd < 0 ? '-' : ''}$${fmt(Math.abs(p.profit_usd))}</td>
            <td class="${marginCls}">${p.margin_pct}%</td>
        </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
}

function renderCategoryChart(categories) {
    const el = document.getElementById('categoryChart');
    el.innerHTML = '';
    if (!categories || !categories.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:12px">No data</p>';
        return;
    }
    const opts = {
        chart: {type: 'bar', height: 300, fontFamily: 'Inter', toolbar: {show: false}},
        series: [
            {name: 'Revenue', data: categories.map(c => c.revenue_usd)},
            {name: 'Profit', data: categories.map(c => c.profit_usd)},
        ],
        xaxis: {categories: categories.map(c => c.category.substring(0, 20))},
        colors: ['#007AFF', '#34C759'],
        plotOptions: {bar: {borderRadius: 4, columnWidth: '60%'}},
        dataLabels: {enabled: false},
        legend: {position: 'top'},
    };
    new ApexCharts(el, opts).render();
}

function renderCountryChart(countries) {
    const el = document.getElementById('countryChart');
    el.innerHTML = '';
    if (!countries || !countries.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:12px">No data</p>';
        return;
    }
    const top = countries.slice(0, 8);
    const opts = {
        chart: {type: 'donut', height: 300, fontFamily: 'Inter'},
        series: top.map(c => c.revenue_usd),
        labels: top.map(c => c.country),
        colors: ['#007AFF', '#34C759', '#FF9500', '#5856D6', '#FF2D55', '#5AC8FA', '#AF52DE', '#32ADE6'],
        legend: {position: 'bottom', fontSize: '12px'},
        dataLabels: {enabled: true, formatter: (val) => val.toFixed(0) + '%'},
    };
    new ApexCharts(el, opts).render();
}

function renderInventory(inv) {
    const grid = document.getElementById('inventoryGrid');
    grid.innerHTML = `
        ${statCard('Total Listings', inv.total_listings)}
        ${statCard('In Stock', inv.in_stock, 'var(--success-500)')}
        ${statCard('Out of Stock', inv.out_of_stock, 'var(--error-500)')}
        ${statCard('OOS Rate', inv.out_of_stock_rate_pct + '%', inv.out_of_stock_rate_pct > 20 ? 'var(--error-500)' : 'var(--success-500)')}
        ${statCard('Avg Turnover', inv.avg_turnover_days + ' days')}
        ${statCard('Dead Stock', inv.dead_stock_count, inv.dead_stock_count > 5 ? 'var(--warning-500)' : 'var(--success-500)')}
        ${statCard('Pending Proc.', inv.pending_procurements)}
    `;

    // デッドストックリスト
    const deadEl = document.getElementById('deadStockList');
    const items = inv.dead_stock_items || [];
    if (items.length) {
        let html = '<h3 style="font-size:14px;margin-bottom:8px;color:var(--warning-600)" data-en="Dead Stock Items" data-ja="デッドストック商品">Dead Stock Items</h3>';
        html += '<div class="dead-stock-pills">';
        items.forEach(d => {
            html += `<span class="dead-stock-pill">${d.title} <small>(${d.days}d / ¥${d.cost_jpy.toLocaleString()})</small></span>`;
        });
        html += '</div>';
        deadEl.innerHTML = html;
    } else {
        deadEl.innerHTML = '';
    }
}

function renderProcurement(proc) {
    const grid = document.getElementById('procurementGrid');
    grid.innerHTML = `
        ${statCard('Items Procured', proc.total_items)}
        ${statCard('Total Cost', '¥' + (proc.total_cost_jpy || 0).toLocaleString())}
        ${statCard('Avg Cost', '¥' + (proc.avg_cost_jpy || 0).toLocaleString())}
    `;
    const platforms = proc.platforms || [];
    if (platforms.length) {
        let html = '<div class="platform-breakdown" style="margin-top:12px">';
        platforms.forEach(p => {
            html += `<div class="platform-pill"><strong>${p.platform}</strong>: ${p.count} items / ¥${p.total_cost_jpy.toLocaleString()}</div>`;
        });
        html += '</div>';
        grid.insertAdjacentHTML('afterend', html);
    }
}

function renderPriceComp(pc) {
    const grid = document.getElementById('priceCompGrid');
    grid.innerHTML = `
        ${statCard('Checked', pc.checked)}
        ${statCard('Cheaper', pc.cheaper_than_lowest, 'var(--success-500)')}
        ${statCard('Competitive', pc.competitive, 'var(--brand-500)')}
        ${statCard('Expensive', pc.more_expensive, pc.more_expensive > 0 ? 'var(--error-500)' : 'var(--success-500)')}
    `;
}

function renderSuggestions(suggestions) {
    const el = document.getElementById('suggestionsList');
    if (!suggestions || !suggestions.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:12px" data-en="No suggestions for this period" data-ja="この期間の提案はありません">No suggestions for this period</p>';
        return;
    }
    let html = '';
    suggestions.forEach(s => {
        const icon = s.priority === 'high' ? '🔴' : s.priority === 'medium' ? '🟡' : '🟢';
        const cls = `suggestion-card priority-${s.priority}`;
        html += `<div class="${cls}">
            <div class="suggestion-header">
                <span class="priority-badge">${icon} ${s.priority.toUpperCase()}</span>
                <span class="suggestion-category">${s.category}</span>
            </div>
            <h3>${s.title}</h3>
            <p>${s.detail}</p>
            <div class="suggestion-action"><strong>Action:</strong> ${s.action}</div>
        </div>`;
    });
    el.innerHTML = html;
}

function renderToolSuggestions(tools) {
    const el = document.getElementById('toolSuggestionsList');
    if (!tools || !tools.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:12px">No tool suggestions</p>';
        return;
    }
    let html = '<div class="tool-suggestions-grid">';
    tools.forEach(t => {
        const priorityCls = `priority-${t.priority}`;
        html += `<div class="tool-card ${priorityCls}">
            <div class="tool-header">
                <h3>${t.name}</h3>
                <span class="tool-priority">${t.priority}</span>
            </div>
            <p>${t.description}</p>
            <div class="tool-reason"><strong>Reason:</strong> ${t.reason}</div>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

// ── ユーティリティ ──────────────────────────────────────

function fmt(n) {
    return (n || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function statCard(label, value, color) {
    const style = color ? `color:${color}` : '';
    return `<div class="stat-card-sm">
        <div class="stat-value-sm" style="${style}">${value}</div>
        <div class="stat-label-sm">${label}</div>
    </div>`;
}
