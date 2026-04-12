/* eBay Agent Hub — Overview Dashboard JS */

/* ── Helpers ── */
const fmt = (n) => formatJPY(n);   // from app.js
const pct = (n) => formatPct(n);   // from app.js

const MONTH_NAMES    = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTH_NAMES_JA = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

/* ── Alert Strip ── */
async function loadAlerts() {
    try {
        const data = await apiFetch('/api/overview/alerts');
        renderAlerts(data);
    } catch (e) {
        console.warn('alerts load failed', e);
    }
}

function renderAlerts(data) {
    const strip = document.getElementById('alertStrip');
    if (!strip) return;
    const items = [];
    if (data.out_of_stock > 0) {
        const cls = data.out_of_stock >= 10 ? 'critical' : '';
        items.push(`<a href="/listings" class="alert-item ${cls}">⚠️ Out of Stock: ${data.out_of_stock}</a>`);
    }
    if (data.unread_messages > 0) {
        const cls = data.unread_messages >= 5 ? 'critical' : '';
        items.push(`<a href="/chat" class="alert-item ${cls}">💬 Unread Messages: ${data.unread_messages}</a>`);
    }
    if (data.price_alerts > 0) {
        items.push(`<a href="/listings?tab=pricing" class="alert-item">📉 Price Alerts: ${data.price_alerts}</a>`);
    }
    if (items.length === 0) {
        strip.style.display = 'none';
        return;
    }
    strip.innerHTML = items.join('');
    strip.style.display = 'flex';
    strip.className = `alert-strip ${data.severity}`;
}

/* ── Achievement Board ── */
async function loadAchievement() {
    try {
        const data = await apiFetch('/api/overview/achievement');
        renderAchievement(data);
    } catch (e) {
        console.warn('achievement load failed', e);
    }
}

function setProgressBar(barId, ratePct, color) {
    const bar = document.getElementById(barId);
    if (!bar) return;
    const capped = Math.min(ratePct, 100);
    bar.style.width = capped + '%';
    bar.style.background = color;
}

function renderAchievement(data) {
    const rev    = data.revenue;
    const margin = data.profit_margin;
    const profit = data.profit;

    /* Revenue card */
    const revColor = rev.rate >= 100 ? 'var(--green)' : 'var(--blue)';
    if (document.getElementById('revActual'))
        document.getElementById('revActual').textContent = fmt(rev.actual);
    setProgressBar('revBar', rev.rate, revColor);
    if (document.getElementById('revRate'))
        document.getElementById('revRate').textContent = pct(rev.rate);
    const revPaceEl = document.getElementById('revPace');
    if (revPaceEl) {
        const icon = rev.projected_eom >= rev.target ? '✅' : '📉';
        const cls  = rev.projected_eom >= rev.target ? 'on-track' : 'off-track';
        revPaceEl.textContent = `Projected: ${fmt(rev.projected_eom)} ${icon}`;
        revPaceEl.className = `ach-pace ${cls}`;
    }

    /* Margin card */
    const marginRatePct = margin.target > 0 ? margin.actual / margin.target * 100 : 0;
    const marginColor   = marginRatePct >= 100 ? 'var(--green)' : marginRatePct >= 80 ? 'var(--orange)' : 'var(--red)';
    if (document.getElementById('marginActual'))
        document.getElementById('marginActual').textContent = pct(margin.actual);
    setProgressBar('marginBar', marginRatePct, marginColor);
    if (document.getElementById('marginRate'))
        document.getElementById('marginRate').textContent = `${pct(margin.actual)} / ${pct(margin.target)}`;
    const marginPaceEl = document.getElementById('marginPace');
    if (marginPaceEl) {
        const diff = margin.actual - (margin.prev_month_same_day || 0);
        const sign = diff >= 0 ? '+' : '';
        const cls  = diff >= 0 ? 'on-track' : 'off-track';
        marginPaceEl.textContent = `vs last month: ${sign}${diff.toFixed(1)}pp`;
        marginPaceEl.className = `ach-pace ${cls}`;
    }

    /* Profit card */
    const profitColor = profit.rate >= 100 ? 'var(--green)' : 'var(--indigo)';
    if (document.getElementById('profitActual'))
        document.getElementById('profitActual').textContent = fmt(profit.actual);
    setProgressBar('profitBar', profit.rate, profitColor);
    if (document.getElementById('profitRate'))
        document.getElementById('profitRate').textContent = pct(profit.rate);
    const profitPaceEl = document.getElementById('profitPace');
    if (profitPaceEl) {
        const icon = profit.projected_eom >= profit.target ? '✅' : '📉';
        const cls  = profit.projected_eom >= profit.target ? 'on-track' : 'off-track';
        profitPaceEl.textContent = `Projected: ${fmt(profit.projected_eom)} ${icon}`;
        profitPaceEl.className = `ach-pace ${cls}`;
    }
}

/* ── Sales Calendar ── */
async function loadCalendar() {
    try {
        const data = await apiFetch('/api/overview/calendar');
        renderCalendar(data);
    } catch (e) {
        const el = document.getElementById('salesCalendar');
        if (el) el.innerHTML = '<div class="empty-state">Could not load calendar</div>';
    }
}

function renderCalendar(data) {
    const { year, month, days } = data;
    const todayStr = new Date().toISOString().slice(0, 10);
    const maxRev   = Math.max(...days.map(d => d.revenue), 1);
    const firstDow = new Date(year, month - 1, 1).getDay(); // 0=Sun

    const cal     = document.getElementById('salesCalendar');
    const titleEl = document.getElementById('calendarTitle');
    if (!cal) return;

    if (titleEl) {
        const mName = t(MONTH_NAMES[month - 1], MONTH_NAMES_JA[month - 1]);
        titleEl.textContent = `${mName} ${year} Sales Calendar`;
    }

    const headers = ['Su','Mo','Tu','We','Th','Fr','Sa'];
    const headJa  = ['日','月','火','水','木','金','土'];
    let html = '<div class="cal-grid">';
    headers.forEach((h, i) => {
        html += `<div class="cal-header">${t(h, headJa[i])}</div>`;
    });

    // 先頭の空マス
    for (let i = 0; i < firstDow; i++) {
        html += '<div class="cal-day empty"></div>';
    }

    days.forEach(d => {
        const isToday  = d.date === todayStr;
        const isFuture = d.date > todayStr;
        const hasSales = d.revenue > 0;
        const intensity = hasSales ? Math.max(0.15, d.revenue / maxRev * 0.85) : 0;
        const dayNum    = parseInt(d.date.slice(8));
        const tooltip   = hasSales
            ? `${d.date}: ${fmt(d.revenue)} / ${d.orders} orders`
            : d.date;

        let cls = 'cal-day';
        if (isToday)  cls += ' is-today';
        if (isFuture) cls += ' is-future';
        if (hasSales) cls += ' has-sales';

        const style = hasSales ? ` style="--intensity:${intensity}"` : '';
        const dotHtml = hasSales
            ? '<span class="cal-dot">●</span>'
            : (isFuture ? '' : '<span class="cal-dot empty-dot">○</span>');
        const todayRevHtml = (isToday && hasSales)
            ? `<span class="cal-today-rev">${fmt(d.revenue)}</span>`
            : '';

        html += `<div class="${cls}"${style} title="${escapeHtml(tooltip)}">
            <span class="cal-day-num">${dayNum}</span>
            ${dotHtml}
            ${todayRevHtml}
        </div>`;
    });

    html += '</div>';
    cal.innerHTML = html;
}

/* ── KPI Comparison (Pace) ── */
async function loadPace() {
    try {
        const data = await apiFetch('/api/overview/pace');
        renderPace(data);
    } catch (e) {
        const el = document.getElementById('kpiTable');
        if (el) el.innerHTML = '<div class="empty-state">Could not load KPI data</div>';
    }
}

function renderPace(data) {
    const { today_revenue, today_orders, daily_avg, prev_month_comparison } = data;
    const { revenue_diff, revenue_diff_pct } = prev_month_comparison;

    const sign  = revenue_diff >= 0 ? '+' : '';
    const arrow = revenue_diff >= 0 ? '↑' : '↓';
    const diffCls = revenue_diff >= 0 ? 'up' : 'down';

    const kpiTable = document.getElementById('kpiTable');
    if (!kpiTable) return;

    kpiTable.innerHTML = `
        <div class="kpi-row">
            <span class="kpi-label" data-en="Today's Revenue" data-ja="本日売上">Today's Revenue</span>
            <span class="kpi-value">${fmt(today_revenue)}</span>
            <span class="kpi-diff neutral">${today_orders} orders</span>
        </div>
        <div class="kpi-row">
            <span class="kpi-label" data-en="Daily Avg (this month)" data-ja="日次平均（今月）">Daily Avg</span>
            <span class="kpi-value">${fmt(daily_avg)}</span>
            <span class="kpi-diff neutral">/ day</span>
        </div>
        <div class="kpi-row">
            <span class="kpi-label" data-en="vs Last Month Same Day" data-ja="前月同日比">vs Last Month</span>
            <span class="kpi-value">${sign}${fmt(revenue_diff)} ${arrow}</span>
            <span class="kpi-diff ${diffCls}">${sign}${revenue_diff_pct}%</span>
        </div>
    `;
}

/* ── 30-Day Chart (moved from inline) ── */
async function loadChart() {
    try {
        const data  = await apiFetch('/api/sales/analytics?days=30');
        const trend = data.daily_trend || [];
        const el    = document.getElementById('revenueChart');
        if (!el) return;
        if (trend.length === 0) {
            el.innerHTML = `<div class="empty-state">${t('No sales data yet.','売上データがありません。')}</div>`;
            return;
        }
        const options = {
            chart: {
                type: 'area', height: 220,
                fontFamily: 'Inter, sans-serif',
                toolbar: { show: false }, zoom: { enabled: false },
            },
            colors: ['#007AFF', '#34C759'],
            series: [
                { name: t('Revenue ($)', '売上($)'), data: trend.map(d => d.revenue_usd) },
                { name: t('Profit ($)', '利益($)'),  data: trend.map(d => d.profit_usd) },
            ],
            xaxis: {
                categories: trend.map(d => d.date.slice(5)),
                axisBorder: { show: false }, axisTicks: { show: false },
                labels: { style: { colors: '#9CA3AF', fontSize: '11px' } },
            },
            yaxis: { labels: { style: { colors: '#9CA3AF', fontSize: '11px' } } },
            grid: { borderColor: '#E5E7EB', xaxis: { lines: { show: false } } },
            stroke: { curve: 'straight', width: 2 },
            fill: { type: 'gradient', gradient: { opacityFrom: 0.45, opacityTo: 0 } },
            dataLabels: { enabled: false },
            legend: {
                position: 'top', horizontalAlign: 'left',
                fontFamily: 'Inter, sans-serif', fontSize: '13px',
                labels: { colors: '#9CA3AF' }, markers: { radius: 99 },
            },
            tooltip: { theme: 'light', style: { fontFamily: 'Inter, sans-serif' } },
        };
        new ApexCharts(el, options).render();
    } catch (e) {
        const el = document.getElementById('revenueChart');
        if (el) el.innerHTML = '<div class="empty-state">Could not load chart</div>';
    }
}

/* ── Activity Feed ── */
async function loadActivity() {
    try {
        const activities = await apiFetch('/api/activity/recent?limit=8');
        const container = document.getElementById('activityFeed');
        if (!container) return;
        if (!activities.length) {
            container.innerHTML = `<div class="empty-state">${t('No recent activity','最近のアクティビティはありません')}</div>`;
            return;
        }
        container.innerHTML = activities.map(a => `
            <div class="activity-item">
                <span class="activity-icon">${a.type === 'sale' ? '💰' : '🔧'}</span>
                <div>
                    <div class="activity-text">${escapeHtml(a.text)}</div>
                    <div class="activity-time">${formatDateTime(a.time)}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        const el = document.getElementById('activityFeed');
        if (el) el.innerHTML = '<div class="empty-state">Could not load activity</div>';
    }
}

/* ── Entry Point ── */
async function initOverview() {
    await Promise.all([
        loadAlerts(),
        loadAchievement(),
        loadCalendar(),
        loadPace(),
        loadChart(),
        loadActivity(),
    ]);
}

initOverview();
