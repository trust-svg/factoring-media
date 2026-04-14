/* eBay Agent Hub — Overview Dashboard JS (redesign 2026-04) */

/* ── Helpers ─────────────────────────────────────────────── */
const fmt  = (n) => formatJPY(n);
const pct  = (n) => formatPct(n);
const fmtM = (n) => {
    if (n >= 1_000_000) return `¥${(n / 1_000_000).toFixed(1)}M`;
    return fmt(n);
};
const CAT_COLORS = ['#2563EB','#10B981','#F97316','#8B5CF6','#EF4444','#F59E0B','#06B6D4','#84CC16'];

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

/* ── USD/JPY chip ────────────────────────────────────────── */
async function loadFxRate() {
    try {
        const data = await apiFetch('/api/fx/usdjpy');
        setText('fxRate', `¥${data.rate.toFixed(2)}`);
        const diffEl = document.getElementById('fxDiff');
        if (diffEl) {
            const sign = data.direction === 'up' ? '+' : '-';
            const cls  = data.direction === 'up' ? 'up' : 'dn';
            diffEl.textContent = `${sign}${Math.abs(data.change).toFixed(2)} ${data.direction === 'up' ? '↑' : '↓'}`;
            diffEl.className = `fx-diff ${cls}`;
        }
    } catch (e) {
        console.warn('fx rate load failed', e);
    }
}

/* ── Alert Strip ─────────────────────────────────────────── */
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
        items.push(`<a href="/listings" class="alert-item ${cls}">⚠️ 在庫切れ ${data.out_of_stock}件</a>`);
    }
    if (data.unread_messages > 0) {
        const cls = data.unread_messages >= 5 ? 'critical' : '';
        items.push(`<a href="/chat" class="alert-item ${cls}">💬 未読 ${data.unread_messages}件</a>`);
    }
    if (data.price_alerts > 0) {
        items.push(`<a href="/listings?tab=pricing" class="alert-item">📉 価格アラート ${data.price_alerts}件</a>`);
    }
    if (items.length === 0) { strip.style.display = 'none'; return; }
    strip.innerHTML = items.join('');
    strip.style.display = 'flex';
    strip.className = `alert-strip ${data.severity}`;
}

/* ── Achievement Board ───────────────────────────────────── */
async function loadAchievement() {
    try {
        const data = await apiFetch('/api/overview/achievement');
        renderAchievement(data);
        return data;
    } catch (e) {
        console.warn('achievement load failed', e);
        return null;
    }
}

function setBar(id, ratePct, color) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.width  = Math.min(ratePct, 100) + '%';
    el.style.background = color;
}

function renderAchievement(data) {
    const rev    = data.revenue;
    const margin = data.profit_margin;
    const profit = data.profit;

    /* Revenue */
    const revColor = rev.rate >= 100 ? 'var(--green)' : 'var(--blue)';
    setText('revActual', fmt(rev.actual));
    setBar('revBar', rev.rate, revColor);
    setText('revRate', pct(rev.rate));
    const revPaceEl = document.getElementById('revPace');
    if (revPaceEl) {
        const icon = rev.projected_eom >= rev.target ? '✅' : '📉';
        const cls  = rev.projected_eom >= rev.target ? 'on-track' : 'off-track';
        revPaceEl.textContent = `予測: ${fmtM(rev.projected_eom)} ${icon}`;
        revPaceEl.className = `ach-pace ${cls}`;
    }

    const revBadge = document.getElementById('revBadge');
    if (revBadge) {
        revBadge.textContent = `${Math.round(rev.rate)}% 達成`;
        revBadge.className = `badge ${rev.rate >= 100 ? 'g' : rev.rate >= 80 ? 'y' : 'r'}`;
    }
    const revRemainEl = document.getElementById('revRemain');
    if (revRemainEl) revRemainEl.textContent = `残 ${fmtM(Math.max(rev.target - rev.actual, 0))}`;

    /* Margin */
    const marginRatePct = margin.target > 0 ? margin.actual / margin.target * 100 : 0;
    const marginColor   = marginRatePct >= 100 ? 'var(--green)' : marginRatePct >= 80 ? 'var(--orange)' : 'var(--red)';
    setText('marginActual', `${margin.actual.toFixed(1)}%`);
    setBar('marginBar', marginRatePct, marginColor);
    setText('marginRate', `${margin.actual.toFixed(1)}% / ${margin.target.toFixed(1)}%`);
    const marginPaceEl = document.getElementById('marginPace');
    if (marginPaceEl) {
        const diff = margin.actual - (margin.prev_month_same_day || 0);
        const sign = diff >= 0 ? '+' : '';
        const cls  = diff >= 0 ? 'on-track' : 'off-track';
        marginPaceEl.textContent = `前月比 ${sign}${diff.toFixed(1)}pp`;
        marginPaceEl.className = `ach-pace ${cls}`;
    }

    const marginBadge = document.getElementById('marginBadge');
    if (marginBadge) {
        marginBadge.textContent = `${Math.round(marginRatePct)}% 達成`;
        marginBadge.className = `badge ${marginRatePct >= 100 ? 'g' : marginRatePct >= 80 ? 'y' : 'r'}`;
    }

    /* Profit */
    const profitColor = profit.rate >= 100 ? 'var(--green)' : 'var(--indigo)';
    setText('profitActual', fmt(profit.actual));
    setBar('profitBar', profit.rate, profitColor);
    setText('profitRate', pct(profit.rate));

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
}

/* ── Payoneer card (static placeholder) ─────────────────── */
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

/* ── KPI Comparison Table ────────────────────────────────── */
async function loadKpiComparison() {
    try {
        const [paceData, achData] = await Promise.all([
            apiFetch('/api/overview/pace'),
            apiFetch('/api/overview/achievement'),
        ]);
        renderKpiComparison(paceData, achData);
    } catch (e) {
        console.warn('kpi comparison load failed', e);
    }
}

function kpiRow(name, value, fillPct, fillClass, diff, diffClass) {
    return `<tr>
        <td class="kn">${escapeHtml(name)}</td>
        <td class="kv">${escapeHtml(value)}</td>
        <td class="mb-w"><div class="mini-bar"><div class="mini-fill ${fillClass}" style="width:${Math.min(fillPct,100)}%"></div></div></td>
        <td class="kd ${diffClass}">${escapeHtml(diff)}</td>
    </tr>`;
}

function renderKpiComparison(pace, ach) {
    const tbl = document.getElementById('kpiTable');
    if (!tbl) return;

    const rev          = ach.revenue;
    const margin       = ach.profit_margin;
    const revDiffPct   = pace.prev_month_comparison.revenue_diff_pct;
    const revDiff      = pace.prev_month_comparison.revenue_diff;
    const marginDiff   = margin.actual - (pace.profit_margin_prev || margin.prev_month_same_day || 0);
    const listingCount = pace.listing_count || 0;
    const oosCount     = pace.out_of_stock_count || 0;
    const orderCount   = pace.month_order_count || 0;
    const prevOrderCount = pace.prev_month_order_count || 0;
    const orderDiffPct = prevOrderCount > 0
        ? Math.round((orderCount - prevOrderCount) / prevOrderCount * 100)
        : 0;

    const revSign  = revDiff >= 0 ? '+' : '';
    const revCls   = revDiff >= 0 ? 'up' : 'dn';
    const margSign = marginDiff >= 0 ? '+' : '';
    const margCls  = marginDiff >= 0 ? 'up' : 'dn';
    const ordSign  = orderDiffPct >= 0 ? '+' : '';
    const ordCls   = orderDiffPct >= 0 ? 'up' : 'dn';

    tbl.innerHTML =
        kpiRow('売上',    fmt(rev.actual),              rev.rate,                              'mf-b',   `${revSign}${revDiffPct}%`,          revCls)  +
        kpiRow('利益率',  `${margin.actual.toFixed(1)}%`, margin.target > 0 ? margin.actual / margin.target * 100 : 0, 'mf-b', `${margSign}${marginDiff.toFixed(1)}pp`, margCls) +
        kpiRow('出品数',  `${listingCount}件`,            Math.min(listingCount / 200 * 100, 100), 'mf-b',   '—',                             'or') +
        kpiRow('在庫切れ',`${oosCount}件`,                Math.min(oosCount / 20 * 100, 100),    'mf-r',    '—',                             'or') +
        kpiRow('注文数',  `${orderCount}件`,              Math.min(orderCount / 100 * 100, 100), 'mf-b',   `${ordSign}${orderDiffPct}%`,       ordCls) +
        kpiRow('Payoneer','$2,840',                      70,                                    'mf-o',   '+$580',                             'or');
}

/* ── freee Cashflow (static placeholder) ─────────────────── */
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

/* ── Chart tab switching ─────────────────────────────────── */
function switchChart(mode) {
    ['daily','monthly'].forEach(m => {
        document.getElementById(`tab-${m}`).classList.toggle('on', m === mode);
        document.getElementById(`panel-${m}`).classList.toggle('on', m === mode);
    });
}

/* ── Calendar tab switching ─────────────────────────────── */
function switchCal(mode) {
    const s = mode === 'sale';
    document.getElementById('salesCalendar').style.display = s ? '' : 'none';
    document.getElementById('payCalendar').style.display   = s ? 'none' : '';
    document.getElementById('cal-tab-sale').classList.toggle('on', s);
    document.getElementById('cal-tab-pay').classList.toggle('on', !s);
}

/* ── Daily Bar Chart ─────────────────────────────────────── */
function renderDailyChart(calData) {
    const el = document.getElementById('dailyBarChart');
    if (!el) return;

    const today    = new Date().toISOString().slice(0, 10);
    const pastDays = calData.days.filter(d => d.date <= today).slice(-12);

    const subLabel = document.getElementById('dailySubLabel');
    if (subLabel && pastDays.length > 0) {
        const m = new Date().getMonth() + 1;
        subLabel.textContent = `日別売上（${m}月1日〜${pastDays.length}日）`;
    }

    if (pastDays.length === 0) {
        el.innerHTML = `<div style="grid-column:1/-1;text-align:center;color:var(--gray-400);padding:20px">データなし</div>`;
        return;
    }

    const maxRev = Math.max(...pastDays.map(d => d.revenue), 1);
    el.innerHTML = pastDays.map(d => {
        const ratio  = d.revenue / maxRev;
        const height = Math.max(Math.round(ratio * 64), d.revenue > 0 ? 4 : 1);
        const cls    = ratio > 0.7 ? 'hi' : ratio > 0.35 ? 'md' : 'lo';
        const numCls = ratio > 0.7 ? 'hi' : '';
        const dayNum = d.date.slice(8).replace(/^0/, '');
        const label  = d.revenue > 0 ? `¥${d.revenue.toLocaleString()}` : '—';
        return `<div class="vbar-col">
            <div class="vbar-num ${numCls}">${label}</div>
            <div class="vbar ${cls}" style="height:${height}px"></div>
            <div class="vbar-day">${dayNum}</div>
        </div>`;
    }).join('');
}

/* ── Monthly Cumulative SVG Chart ────────────────────────── */
function renderMonthlyCumulativeChart(calData, achData) {
    const svgEl     = document.getElementById('monthlyChartSvg');
    const yLabelsEl = document.getElementById('monthlyYLabels');
    const xLabelsEl = document.getElementById('monthlyXLabels');
    if (!svgEl) return;

    const target    = achData.revenue.target;
    const today     = new Date().toISOString().slice(0, 10);
    const totalDays = calData.days.length;

    // 今月累計
    let cumThis = 0;
    const thisMonthPoints = calData.days.map(d => {
        if (d.date <= today) cumThis += d.revenue;
        return cumThis;
    });

    // 目標累計（日割り）
    const targetPoints = calData.days.map((_, i) => Math.round(target / totalDays * (i + 1)));

    // 前月累計（実データ、なければ推定）
    const todayIdx    = calData.days.findIndex(d => d.date > today);
    const activeUntil = todayIdx === -1 ? totalDays - 1 : Math.max(todayIdx - 1, 0);
    let prevMonthPoints;
    if (_prevCalendarData && _prevCalendarData.days && _prevCalendarData.days.length > 0) {
        const prevDays = _prevCalendarData.days;
        const prevDim  = prevDays.length;
        let cum = 0;
        const prevCumul = prevDays.map(d => { cum += d.revenue; return cum; });
        // 先月の日数を今月のx軸にスケール
        prevMonthPoints = calData.days.map((_, i) => {
            const idx = Math.min(Math.round(i * prevDim / totalDays), prevDim - 1);
            return prevCumul[idx] || 0;
        });
    } else {
        const pmFinalEst = Math.round(thisMonthPoints[activeUntil] / Math.max(activeUntil + 1, 1) * totalDays * 0.88);
        prevMonthPoints = calData.days.map((_, i) => Math.round(pmFinalEst / totalDays * (i + 1)));
    }

    const svgWidth  = svgEl.clientWidth || 280;
    const svgHeight = 120;
    const padBottom = 16;
    const chartH    = svgHeight - padBottom;
    const maxVal    = Math.max(...targetPoints, ...thisMonthPoints, 1);

    const toX = (i) => (i / Math.max(totalDays - 1, 1)) * svgWidth;
    const toY = (v) => chartH - (v / maxVal * chartH);
    const makePath = (points, until) =>
        points.slice(0, until + 1)
              .map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
              .join(' ');

    // Y labels
    if (yLabelsEl) {
        yLabelsEl.innerHTML = [1.0, 0.75, 0.5, 0.25, 0].map(f => {
            const v = Math.round(maxVal * f);
            const lbl = v >= 1_000_000 ? `${(v/1_000_000).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(0)}K` : String(v);
            return `<div class="monthly-y-lbl">${lbl}</div>`;
        }).join('');
    }

    // X labels
    if (xLabelsEl) {
        xLabelsEl.innerHTML = calData.days
            .filter((_, i) => i % 5 === 0 || i === totalDays - 1)
            .map(d => `<div class="monthly-x-lbl">${d.date.slice(8).replace(/^0/,'')}</div>`)
            .join('');
    }

    svgEl.innerHTML = `
        <defs>
          <linearGradient id="mgr" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#2563EB" stop-opacity=".25"/>
            <stop offset="100%" stop-color="#2563EB" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <path d="${makePath(thisMonthPoints, activeUntil)} L${toX(activeUntil).toFixed(1)},${chartH} L0,${chartH} Z"
              fill="url(#mgr)" />
        <path d="${makePath(targetPoints, totalDays - 1)}" fill="none" stroke="#F97316"
              stroke-width="1.5" stroke-dasharray="5,4" opacity=".8"/>
        <path d="${makePath(prevMonthPoints, totalDays - 1)}" fill="none" stroke="#94A3B8"
              stroke-width="1.5" stroke-dasharray="5,4" opacity=".7"/>
        <path d="${makePath(thisMonthPoints, activeUntil)}" fill="none" stroke="#2563EB" stroke-width="2"/>
    `;

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
}

/* ── Sales Calendar ──────────────────────────────────────── */
let _calendarData = null;
let _prevCalendarData = null;

async function loadCalendar() {
    try {
        const [data, prevData] = await Promise.all([
            apiFetch('/api/overview/calendar'),
            apiFetch('/api/overview/calendar_prev').catch(() => null),
        ]);
        _calendarData = data;
        _prevCalendarData = prevData;
        renderSalesCal(data);
        renderPayCal(data);
        return data;
    } catch (e) {
        const el = document.getElementById('salesCalendar');
        if (el) el.innerHTML = '<div class="empty-state">カレンダーを読み込めませんでした</div>';
        return null;
    }
}

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

/* ── Out-of-stock list ───────────────────────────────────── */
async function loadOOS() {
    try {
        const items = await apiFetch('/api/overview/out_of_stock');
        renderOOS(items);
    } catch (e) {
        const tb = document.getElementById('oosTableBody');
        if (tb) tb.innerHTML = '<tr><td colspan="4" class="oos-empty-row">読み込みエラー</td></tr>';
    }
}

function renderOOS(items) {
    const tb = document.getElementById('oosTableBody');
    if (!tb) return;
    if (!items.length) {
        tb.innerHTML = '<tr><td colspan="4" class="oos-empty-row">在庫切れ商品はありません ✅</td></tr>';
        const countEl = document.getElementById('oosCount');
        if (countEl) countEl.textContent = '';
        const moreEl = document.getElementById('oosMore');
        if (moreEl) moreEl.textContent = '';
        return;
    }
    tb.innerHTML = items.map(item => {
        const days  = item.days_out_of_stock != null ? `${item.days_out_of_stock}日` : '—';
        const price = item.last_sale_price_jpy > 0 ? fmt(item.last_sale_price_jpy) : `$${item.price_usd}`;
        const t2 = item.title || '';
        const query = encodeURIComponent(t2.slice(0, 40));
        const title = t2.length > 45 ? t2.slice(0, 45) + '…' : t2;
        return `<tr>
            <td>${escapeHtml(title)}</td>
            <td>${price}</td>
            <td><span class="oos-days">${days}</span></td>
            <td><a class="oos-btn" href="/sourcing?q=${query}" target="_blank">仕入れ検索</a></td>
        </tr>`;
    }).join('');
    const countEl = document.getElementById('oosCount');
    if (countEl) countEl.textContent = items.length > 0 ? `— ${items.length}件` : '';
    const moreEl = document.getElementById('oosMore');
    if (moreEl) moreEl.textContent = '';
}

/* ── Category Profit Modal ───────────────────────────────── */
let _catData = null;

async function openModal() {
    document.getElementById('catModal').classList.add('open');
    if (_catData) { renderCatModal(_catData); return; }
    try {
        const data = await apiFetch('/api/overview/category_profit');
        _catData = data;
        renderCatModal(data);
    } catch (e) {
        const tb = document.getElementById('catModalTableBody');
        if (tb) tb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--gray-400);padding:16px">データなし</td></tr>';
    }
}

function closeModal() {
    document.getElementById('catModal').classList.remove('open');
}

function renderCatModal(items) {
    const tb     = document.getElementById('catModalTableBody');
    const svgEl  = document.getElementById('catDonutSvg');
    const footEl = document.getElementById('catModalFoot');
    if (!tb) return;

    if (!items.length) {
        tb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--gray-400);padding:16px">データなし</td></tr>';
        return;
    }

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

    if (svgEl) {
        const cx = 60, cy = 60, r = 42, r2 = 26;
        const total = items.reduce((s, item) => s + item.profit, 0);
        let angle = -Math.PI / 2;
        const slices = items.map((item, i) => {
            const sweep = (item.profit / total) * 2 * Math.PI;
            const x1 = cx + r  * Math.cos(angle),       y1 = cy + r  * Math.sin(angle);
            angle += sweep;
            const x2 = cx + r  * Math.cos(angle),       y2 = cy + r  * Math.sin(angle);
            const x3 = cx + r2 * Math.cos(angle),       y3 = cy + r2 * Math.sin(angle);
            const x4 = cx + r2 * Math.cos(angle - sweep), y4 = cy + r2 * Math.sin(angle - sweep);
            const large = sweep > Math.PI ? 1 : 0;
            const color = CAT_COLORS[i % CAT_COLORS.length];
            return `<path d="M${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 ${large},1 ${x2.toFixed(1)},${y2.toFixed(1)} L${x3.toFixed(1)},${y3.toFixed(1)} A${r2},${r2} 0 ${large},0 ${x4.toFixed(1)},${y4.toFixed(1)} Z" fill="${color}" opacity=".9"/>`;
        });
        svgEl.innerHTML = slices.join('') +
            `<text x="${cx}" y="${cy+4}" text-anchor="middle" font-size="10" font-weight="700" fill="#374151">${items.length}カテゴリ</text>`;
    }

    if (footEl && items[0]) {
        const top = items[0];
        footEl.textContent = `最大利益カテゴリ: ${top.category} (${top.pct_of_total}% / 利益率 ${top.margin}%)`;
    }
}

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
        const t = r.title || '';
        const title = t.length > 40 ? t.slice(0, 40) + '…' : t;
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

/* ── Entry Point ─────────────────────────────────────────── */
async function initOverview() {
    // Today tag
    const todayEl = document.getElementById('todayTag');
    if (todayEl) {
        const now = new Date();
        todayEl.textContent = `本日 ${now.getMonth()+1}/${now.getDate()}`;
    }

    renderPayoneerStatic();
    renderFreeeStatic();

    const [calData, achData] = await Promise.all([
        loadCalendar(),
        loadAchievement(),
        loadFxRate(),
        loadAlerts(),
        loadKpiComparison(),
        loadOOS(),
        loadSalesTable(),
    ]);

    if (calData && achData) {
        renderDailyChart(calData);
        renderMonthlyCumulativeChart(calData, achData);
    }
}

initOverview();
