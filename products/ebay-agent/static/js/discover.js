/* discover.js — eBayディスカバリーページ */

let discoverData = [];

async function runDiscover() {
    const btn = document.getElementById('discoverBtn');
    const keyword = document.getElementById('searchKeyword').value.trim() || 'Japan';
    const category = document.getElementById('searchCategory').value;
    const limit = document.getElementById('searchLimit').value;
    const priceMin = document.getElementById('searchPriceMin').value;
    const priceMax = document.getElementById('searchPriceMax').value;
    const conditionIds = document.getElementById('searchCondition').value;

    btn.disabled = true;
    btn.textContent = 'Searching...';

    try {
        const resp = await fetch('/api/discover/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                keyword,
                category,
                limit: parseInt(limit),
                price_min: parseFloat(priceMin) || 0,
                price_max: parseFloat(priceMax) || 0,
                condition_ids: conditionIds,
            }),
        });
        const data = await resp.json();

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        discoverData = data.results || [];

        // KPI更新
        const kpi = document.getElementById('discoverKpi');
        kpi.style.display = 'grid';

        const marketTotal = data.market_total || 0;
        document.getElementById('kpiMarket').textContent = marketTotal.toLocaleString();
        const demandMap = {
            high: { label: 'High Demand', color: 'var(--accent-green,#22c55e)' },
            medium: { label: 'Medium Demand', color: '#f59e0b' },
            low: { label: 'Low Demand', color: 'var(--accent-red,#ef4444)' },
            very_low: { label: 'Very Low', color: 'var(--accent-red,#ef4444)' },
        };
        const dl = demandMap[data.demand_level] || demandMap.very_low;
        document.getElementById('kpiDemand').innerHTML = `<span style="color:${dl.color};font-weight:600;">${dl.label}</span>`;

        document.getElementById('kpiTotal').textContent = data.total || 0;
        document.getElementById('kpiNew').textContent = data.new_items || 0;
        document.getElementById('kpiKnown').textContent = (data.total || 0) - (data.new_items || 0);
        document.getElementById('kpiRate').textContent = '$1 = ¥' + Math.round(data.exchange_rate);

        document.getElementById('resultsSection').style.display = 'block';
        renderResults();
    } catch (e) {
        alert('Search failed: ' + e.message);
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Search eBay';
    }
}

function renderResults() {
    const filterNew = document.getElementById('filterNew').checked;
    const tbody = document.getElementById('discoverBody');

    let filtered = discoverData;
    if (filterNew) filtered = filtered.filter(r => !r.is_known);

    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No results matching filters</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map((r, idx) => {
        const scoreColor = r.score >= 70 ? 'var(--accent-green,#22c55e)' :
                           r.score >= 40 ? '#f59e0b' : 'var(--accent-red,#ef4444)';
        const statusBadge = r.is_known
            ? '<span style="display:inline-block;padding:2px 6px;border-radius:8px;font-size:10px;background:var(--border);color:var(--text-muted);white-space:nowrap;">Known</span>'
            : '<span style="display:inline-block;padding:2px 6px;border-radius:8px;font-size:10px;background:#22c55e;color:white;white-space:nowrap;">NEW</span>';
        const thumb = r.image_url
            ? `<img src="${esc(r.image_url)}" style="width:36px;height:36px;object-fit:cover;border-radius:4px;" onerror="this.style.display='none'">`
            : '';
        // セラー情報
        const sellerInfo = r.seller
            ? `${esc(r.seller)}${r.seller_feedback ? '<br><span style="font-size:10px;color:var(--text-muted);">FB:' + r.seller_feedback + '</span>' : ''}`
            : '-';

        return `<tr>
            <td style="text-align:center;">
                <span style="display:inline-block;width:32px;padding:2px 0;border-radius:8px;font-size:12px;font-weight:700;text-align:center;background:${scoreColor};color:white;">${r.score}</span>
            </td>
            <td style="padding:4px;">${thumb}</td>
            <td style="font-size:12px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(r.title)}">
                <a href="${esc(r.item_url)}" target="_blank" style="color:var(--text-primary);text-decoration:none;">${esc(r.title.length > 55 ? r.title.slice(0, 55) + '...' : r.title)}</a>
            </td>
            <td style="font-size:12px;font-weight:600;">$${r.price_usd.toFixed(0)}<br><span style="font-size:10px;color:var(--text-muted);">¥${r.price_jpy.toLocaleString()}</span></td>
            <td style="font-size:11px;">${sellerInfo}</td>
            <td style="font-size:11px;color:var(--text-secondary);">${esc(r.condition || '-')}</td>
            <td style="font-size:11px;">${statusBadge}</td>
            <td style="white-space:nowrap;">
                <button class="btn btn-sm btn-outline" onclick="openEstimate(${idx})" style="padding:2px 8px;font-size:10px;">Calc</button>
                <button class="btn btn-sm btn-outline" onclick="openSourceSearch('${esc(r.title.replace(/'/g, "\\'"))}')" style="padding:2px 8px;font-size:10px;">仕入</button>
            </td>
        </tr>`;
    }).join('');
}

// ── 利益シミュレーション ───────────────────────────────
let currentEstItem = null;

function openEstimate(idx) {
    const filterNew = document.getElementById('filterNew').checked;
    let filtered = discoverData;
    if (filterNew) filtered = filtered.filter(r => !r.is_known);

    currentEstItem = filtered[idx];
    if (!currentEstItem) return;

    document.getElementById('estProductTitle').textContent = currentEstItem.title;
    document.getElementById('estSellPrice').value = currentEstItem.price_usd.toFixed(2);
    document.getElementById('estSourceCost').value = '';
    document.getElementById('estShipping').value = '30';
    document.getElementById('estResult').style.display = 'none';
    document.getElementById('estimateModal').style.display = 'flex';
}

function closeEstimate() {
    document.getElementById('estimateModal').style.display = 'none';
}

async function calcEstimate() {
    const sellPrice = parseFloat(document.getElementById('estSellPrice').value) || 0;
    const sourceCost = parseInt(document.getElementById('estSourceCost').value) || 0;
    const shipping = parseFloat(document.getElementById('estShipping').value) || 0;

    if (!sourceCost) {
        alert('仕入原価を入力してください');
        return;
    }

    try {
        const resp = await fetch('/api/discover/estimate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sell_price_usd: sellPrice,
                source_cost_jpy: sourceCost,
                shipping_usd: shipping,
            }),
        });
        const d = await resp.json();

        document.getElementById('estEbayFee').textContent = '-$' + d.ebay_fee_usd.toFixed(2);
        document.getElementById('estPayoneerFee').textContent = '-$' + d.payoneer_fee_usd.toFixed(2);
        document.getElementById('estShipCost').textContent = '-$' + d.shipping_usd.toFixed(2);
        document.getElementById('estCostDisplay').textContent = '-$' + d.source_cost_usd.toFixed(2) + ' (¥' + d.source_cost_jpy.toLocaleString() + ')';

        const profitEl = document.getElementById('estProfit');
        const profitColor = d.profit_jpy >= 0 ? 'var(--accent-green,#22c55e)' : 'var(--accent-red,#ef4444)';
        profitEl.innerHTML = `<span style="color:${profitColor};">¥${d.profit_jpy.toLocaleString()} ($${d.profit_usd.toFixed(2)})</span>`;

        const marginEl = document.getElementById('estMargin');
        marginEl.innerHTML = `<span style="color:${profitColor};">${d.margin_pct}%</span>`;

        document.getElementById('estResult').style.display = 'block';
    } catch (e) {
        console.error(e);
    }
}

// ── セラー分析 ─────────────────────────────────────────

async function runSellerAnalysis() {
    const btn = document.getElementById('sellerBtn');
    const seller = document.getElementById('sellerInput').value.trim();
    if (!seller) { alert('セラー名を入力してください'); return; }

    btn.disabled = true;
    btn.textContent = 'Analyzing...';

    try {
        const resp = await fetch('/api/discover/seller-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seller }),
        });
        const d = await resp.json();
        if (d.error) { alert(d.error); return; }

        document.getElementById('sellerResults').style.display = 'block';

        // KPI
        document.getElementById('sellerTotal').textContent = d.total_listings.toLocaleString();
        document.getElementById('sellerFetched').textContent = `(${d.fetched} fetched)`;
        document.getElementById('sellerAvg').textContent = '$' + d.avg_price_usd;
        document.getElementById('sellerMedian').textContent = 'Median: $' + d.median_price_usd;
        document.getElementById('sellerRange').textContent = '$' + d.min_price_usd + ' - $' + d.max_price_usd;
        document.getElementById('sellerCatCount').textContent = d.categories.length;

        // カテゴリ構成（バー表示）
        const catEl = document.getElementById('sellerCategories');
        catEl.innerHTML = d.categories.slice(0, 10).map(c =>
            `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                <span style="font-size:11px;min-width:100px;color:var(--text-secondary);">${esc(c.name)}</span>
                <div style="flex:1;background:var(--bg-tertiary);border-radius:4px;height:16px;overflow:hidden;">
                    <div style="height:100%;width:${c.pct}%;background:var(--accent-blue,#3b82f6);border-radius:4px;min-width:2px;"></div>
                </div>
                <span style="font-size:10px;color:var(--text-muted);min-width:50px;text-align:right;">${c.count} (${c.pct}%)</span>
            </div>`
        ).join('');

        // 価格帯分布
        const prEl = document.getElementById('sellerPriceRanges');
        const maxPr = Math.max(...Object.values(d.price_ranges));
        prEl.innerHTML = Object.entries(d.price_ranges).map(([range, count]) =>
            `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                <span style="font-size:11px;min-width:70px;color:var(--text-secondary);">${range}</span>
                <div style="flex:1;background:var(--bg-tertiary);border-radius:4px;height:16px;overflow:hidden;">
                    <div style="height:100%;width:${maxPr ? count/maxPr*100 : 0}%;background:#f59e0b;border-radius:4px;min-width:2px;"></div>
                </div>
                <span style="font-size:10px;color:var(--text-muted);min-width:30px;text-align:right;">${count}</span>
            </div>`
        ).join('');

        // キーワードTOP（タグクラウド）
        const kwEl = document.getElementById('sellerKeywords');
        const maxKw = d.top_keywords[0]?.count || 1;
        kwEl.innerHTML = d.top_keywords.map(kw => {
            const size = Math.max(10, Math.round(10 + (kw.count / maxKw) * 10));
            const opacity = 0.4 + (kw.count / maxKw) * 0.6;
            return `<span style="font-size:${size}px;opacity:${opacity};padding:2px 6px;background:var(--bg-tertiary);border-radius:4px;white-space:nowrap;" title="${kw.count}">${esc(kw.word)}</span>`;
        }).join('');

        // Gap Analysis
        const gapEl = document.getElementById('sellerGaps');
        gapEl.innerHTML = '<table class="data-table"><thead><tr>' +
            '<th>Category</th><th>Seller</th><th>You</th><th>Gap</th></tr></thead><tbody>' +
            d.gap_analysis.map(g => {
                const gap = g.my_count === 0 ? '<span style="color:var(--accent-red,#ef4444);font-weight:600;">NEW OPP</span>' :
                    g.seller_pct > 10 && g.my_count < 3 ? '<span style="color:#f59e0b;">Weak</span>' : '<span style="color:var(--text-muted);">OK</span>';
                return `<tr>
                    <td style="font-size:12px;">${esc(g.category)}</td>
                    <td style="font-size:12px;">${g.seller_count} (${g.seller_pct}%)</td>
                    <td style="font-size:12px;">${g.my_count}</td>
                    <td style="font-size:12px;">${gap}</td>
                </tr>`;
            }).join('') + '</tbody></table>';

        // セラー商品一覧
        const itemsEl = document.getElementById('sellerItemsBody');
        itemsEl.innerHTML = (d.items || []).map(item => {
            const thumb = item.image_url
                ? `<img src="${esc(item.image_url)}" style="width:36px;height:36px;object-fit:cover;border-radius:4px;" onerror="this.style.display='none'">`
                : '';
            return `<tr>
                <td style="padding:4px;">${thumb}</td>
                <td style="font-size:12px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(item.title)}">
                    <a href="${esc(item.item_url)}" target="_blank" style="color:var(--text-primary);text-decoration:none;">${esc(item.title.length > 50 ? item.title.slice(0, 50) + '...' : item.title)}</a>
                </td>
                <td style="font-size:12px;font-weight:600;">$${item.price_usd.toFixed(0)}<br><span style="font-size:10px;color:var(--text-muted);">¥${item.price_jpy.toLocaleString()}</span></td>
                <td style="font-size:11px;">${esc(item.category)}</td>
                <td style="font-size:11px;">${esc(item.condition)}</td>
                <td><button class="btn btn-sm btn-outline" onclick="openSourceSearch('${esc(item.title.replace(/'/g, "\\'"))}')" style="padding:2px 8px;font-size:10px;">仕入れ検索</button></td>
            </tr>`;
        }).join('');

    } catch (e) {
        alert('Analysis failed: ' + e.message);
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Analyze';
    }
}


// ── 仕入れサイト検索 ──────────────────────────────────────

async function openSourceSearch(title) {
    try {
        const resp = await fetch('/api/discover/source-search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        const d = await resp.json();
        if (d.error) { alert(d.error); return; }

        document.getElementById('sourceTitle').textContent = d.title;
        document.getElementById('sourceQuery').textContent = 'Search: ' + d.search_query;

        const linksEl = document.getElementById('sourceLinks');
        linksEl.innerHTML = d.sources.map(s =>
            `<a href="${esc(s.url)}" target="_blank" style="display:flex;align-items:center;gap:8px;padding:10px 14px;background:var(--bg-tertiary);border-radius:8px;text-decoration:none;color:var(--text-primary);font-size:13px;border:1px solid var(--border);transition:border-color 0.2s;" onmouseenter="this.style.borderColor='var(--accent-blue,#3b82f6)'" onmouseleave="this.style.borderColor='var(--border)'">
                <span style="font-size:18px;">${s.icon}</span>
                <span style="font-weight:600;">${esc(s.site)}</span>
                <span style="margin-left:auto;font-size:11px;color:var(--text-muted);">Open →</span>
            </a>`
        ).join('');

        document.getElementById('sourceModal').style.display = 'flex';
    } catch (e) {
        console.error(e);
    }
}


// ── ユーティリティ ──────────────────────────────────────
function esc(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
