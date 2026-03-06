/* eBay Agent Hub — Shared Utilities */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function apiFetch(url, options = {}) {
    const resp = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        throw new Error(err.detail || 'API Error');
    }
    return resp.json();
}

function formatUSD(val) { return '$' + Number(val).toFixed(2); }
function formatJPY(val) { return '\u00a5' + Number(val).toLocaleString(); }
function formatPct(val) { return Number(val).toFixed(1) + '%'; }
function formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('ja-JP', { month: 'short', day: 'numeric' });
}
function formatDateTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('ja-JP') + ' ' + d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
}

function statusBadge(status) {
    const cls = {
        'found': 'stock', 'purchased': 'purchased', 'shipped': 'shipped',
        'received': 'received', 'listed': 'listed',
    }[status] || 'stock';
    return `<span class="badge ${cls}">${escapeHtml(status)}</span>`;
}

/* ── Language Toggle ── */

function getLang() {
    return localStorage.getItem('ebay-hub-lang') || 'en';
}

function t(en, ja) { return getLang() === 'ja' ? ja : en; }

function applyLang(lang) {
    document.querySelectorAll('[data-en][data-ja]').forEach(el => {
        el.textContent = el.dataset[lang];
    });
    document.querySelectorAll('[data-placeholder-en][data-placeholder-ja]').forEach(el => {
        el.placeholder = lang === 'ja' ? el.dataset.placeholderJa : el.dataset.placeholderEn;
    });
    const label = document.getElementById('langLabel');
    if (label) label.textContent = lang === 'ja' ? 'JA' : 'EN';
}

function toggleLang() {
    const next = getLang() === 'en' ? 'ja' : 'en';
    localStorage.setItem('ebay-hub-lang', next);
    location.reload();
}

// Apply saved language on load
document.addEventListener('DOMContentLoaded', () => applyLang(getLang()));
