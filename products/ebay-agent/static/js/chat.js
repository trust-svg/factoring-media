/**
 * eBay Buyer Messaging — Frontend Logic
 */

// ── State ───────────────────────────────────────────
let currentFilter = 'all';
let currentBuyer = '';
let currentItemId = '';
let conversations = [];
let itemsList = [];
let currentThread = [];
let uploadedImageUrls = [];
let lastMessageId = null;
let currentBuyerSort = 'date';
let _knownConvKeys = new Set(); // for new message detection
let _audioCtx = null;

// ── Seller Avatar ────────────────────────────────────
const AVATAR_KEY = 'chat_seller_avatar';
function getSellerAvatar() { return localStorage.getItem(AVATAR_KEY) || ''; }
function setSellerAvatar(dataUrl) {
    localStorage.setItem(AVATAR_KEY, dataUrl);
    _updateAvatarPreviews(dataUrl);
}
function _updateAvatarPreviews(dataUrl) {
    // Header preview button
    const preview = document.getElementById('sellerAvatarPreview');
    if (preview) {
        preview.innerHTML = dataUrl
            ? `<img src="${dataUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`
            : 'H';
    }
}
function onAvatarFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        setSellerAvatar(ev.target.result);
        renderThread(); // re-render to update all bubbles
    };
    reader.readAsDataURL(file);
    e.target.value = ''; // reset so same file can be re-selected
}
// Avatar for buyer — colored circle with initial
const _buyerColors = ['#0B7FDE','#059669','#D97706','#DC2626','#7C3AED','#0891B2','#BE185D'];
function _buyerColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xFFFF;
    return _buyerColors[h % _buyerColors.length];
}
function _buyerAvatarHtml(name) {
    const initial = (name || '?')[0].toUpperCase();
    const color = _buyerColor(name || '');
    return `<div class="msg-avatar-buyer" style="background:${color};">${initial}</div>`;
}
function _sellerAvatarHtml() {
    const dataUrl = getSellerAvatar();
    return dataUrl
        ? `<div class="msg-avatar-seller"><img src="${dataUrl}" alt="me"></div>`
        : `<div class="msg-avatar-seller">H</div>`;
}

// ── Cache ───────────────────────────────────────────
const _cache = {
    threads: {},        // key: "buyer|item_id" → {data, ts}
    scores: {},         // key: buyer → {data, ts}
    histories: {},      // key: buyer → {data, ts}
    items: {},          // key: item_id → {data, ts}
    TTL: 5 * 60 * 1000, // 5分
    TTL_ITEM: 30 * 60 * 1000, // 商品情報は30分
};

function cacheGet(store, key, ttl) {
    const entry = store[key];
    if (!entry) return null;
    if (Date.now() - entry.ts > (ttl || _cache.TTL)) {
        delete store[key];
        return null;
    }
    return entry.data;
}

function cacheSet(store, key, data) {
    store[key] = { data, ts: Date.now() };
}

function cacheInvalidate(store, key) {
    if (key) delete store[key];
    else Object.keys(store).forEach(k => delete store[k]);
}

// ── Init ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Restore seller avatar from localStorage
    const savedAvatar = getSellerAvatar();
    if (savedAvatar) _updateAvatarPreviews(savedAvatar);
    // DBから即座に表示
    await loadConversations();
    // 初回sync: ページ表示完了から30秒後に実行（UIをブロックしない）
    setTimeout(() => syncMessages(true), 30000);
    // 以降は5分毎
    setInterval(() => syncMessages(true), 5 * 60 * 1000);
});

// ── Conversations ───────────────────────────────────
async function loadConversations() {
    try {
        const params = new URLSearchParams({
            status: currentFilter,
            search: document.getElementById('searchInput')?.value || '',
        });
        const resp = await fetch(`/api/chat/conversations?${params}`);
        const data = await resp.json();

        // Detect new unread messages → play sound
        const newKeys = new Set();
        (data.conversations || []).forEach(c => {
            if (c.unread_count > 0) newKeys.add(`${c.buyer}|${c.item_id}`);
        });
        if (_knownConvKeys.size > 0) {
            for (const k of newKeys) {
                if (!_knownConvKeys.has(k)) { playNewMessageSound(); break; }
            }
        }
        _knownConvKeys = newKeys;

        conversations = data.conversations || [];
        itemsList = data.items || [];
        renderProductList();
        updateUnreadBadge(data.unread_total || 0);
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
}

// ── Product List (left column) ──────────────────────
function renderProductList() {
    const container = document.getElementById('productList');
    if (!container) { renderConversations(); return; }

    if (!itemsList.length) {
        container.innerHTML = `<div class="thread-empty"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/></svg><span>${getLang() === 'ja' ? '同期してください' : 'Click Sync'}</span></div>`;
        return;
    }

    container.innerHTML = itemsList.map((item, i) => {
        const isActive = item.item_id === currentItemId;
        const thumbHtml = item.thumbnail
            ? `<img class="product-thumb" src="${escapeHtml(item.thumbnail)}" alt="" loading="lazy">`
            : `<div class="product-thumb-placeholder" data-item-id="${escapeHtml(item.item_id)}"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" width="18" height="18"><path stroke-linecap="round" stroke-linejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"/></svg></div>`;
        const unreadHtml = item.unread_count > 0
            ? `<span class="product-unread-badge">${item.unread_count}</span>`
            : '';

        return `<div class="product-item ${isActive ? 'active' : ''}" onclick="selectProduct('${escapeHtml(item.item_id)}')" style="animation-delay:${i*30}ms" title="${escapeHtml(item.title)}">
            <div class="product-thumb-wrap">${thumbHtml}${unreadHtml}</div>
            <div class="product-info">
                <div class="product-title">${escapeHtml((item.title || '#' + item.item_id).substring(0, 40))}</div>
                <div class="product-buyers-count"><span style="display:inline-block;padding:1px 8px;border-radius:10px;background:#E8EAF6;color:#3949AB;font-weight:700;font-size:11px;">${item.buyers?.length || 0}</span> ${getLang() === 'ja' ? 'バイヤー' : 'buyers'}</div>
            </div>
        </div>`;
    }).join('');

    // Lazy-load missing thumbnails from item API
    const missingThumbs = container.querySelectorAll('.product-thumb-placeholder[data-item-id]');
    missingThumbs.forEach(el => {
        const itemId = el.dataset.itemId;
        if (!itemId) return;
        const cached = cacheGet(_cache.items, itemId, _cache.TTL_ITEM);
        if (cached && cached.thumbnail) {
            el.outerHTML = `<img class="product-thumb" src="${escapeHtml(cached.thumbnail)}" alt="" loading="lazy">`;
            return;
        }
        fetch(`/api/chat/item/${itemId}`).then(r => r.json()).then(data => {
            if (data.thumbnail) {
                cacheSet(_cache.items, itemId, data);
                // Update itemsList too
                const item = itemsList.find(i => i.item_id === itemId);
                if (item) {
                    item.thumbnail = data.thumbnail;
                    if (!item.title && data.title) item.title = data.title;
                }
                el.outerHTML = `<img class="product-thumb" src="${escapeHtml(data.thumbnail)}" alt="" loading="lazy">`;
            }
        }).catch(() => {});
    });
}

function selectProduct(itemId) {
    currentItemId = itemId;
    renderProductList();

    // Show buyers for this product
    const item = itemsList.find(i => i.item_id === itemId);
    if (item) {
        renderBuyerList(item.buyers || []);
        // Auto-select first buyer
        if (item.buyers?.length === 1) {
            openThread(item.buyers[0].buyer, itemId);
        }
    }
}

// ── Buyer Sort ───────────────────────────────────────
function setBuyerSort(val) {
    currentBuyerSort = val;
    const item = itemsList.find(i => i.item_id === currentItemId);
    if (item) renderBuyerList(item.buyers || []);
}

function _sortBuyers(buyers) {
    const arr = [...buyers];
    if (currentBuyerSort === 'unread') {
        arr.sort((a, b) => (b.unread_count || 0) - (a.unread_count || 0) || (b.last_date || '').localeCompare(a.last_date || ''));
    } else if (currentBuyerSort === 'purchased') {
        const hasPurchased = b => (b.status || []).includes('purchased') ? 0 : 1;
        arr.sort((a, b) => hasPurchased(a) - hasPurchased(b) || (b.last_date || '').localeCompare(a.last_date || ''));
    } else if (currentBuyerSort === 'trouble') {
        const hasTrouble = b => (b.status || []).some(s => ['return','cancel','refund','dispute'].includes(s)) ? 0 : 1;
        arr.sort((a, b) => hasTrouble(a) - hasTrouble(b) || (b.last_date || '').localeCompare(a.last_date || ''));
    } else {
        // date (default)
        arr.sort((a, b) => (b.last_date || '').localeCompare(a.last_date || ''));
    }
    return arr;
}

// ── Sound Notification ───────────────────────────────
function _getAudioCtx() {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return _audioCtx;
}

function playNewMessageSound() {
    try {
        const ctx = _getAudioCtx();
        // Two-tone chime: 880Hz → 1046Hz
        [[880, 0, 0.12], [1046, 0.13, 0.18]].forEach(([freq, start, end]) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0, ctx.currentTime + start);
            gain.gain.linearRampToValueAtTime(0.18, ctx.currentTime + start + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + end);
            osc.start(ctx.currentTime + start);
            osc.stop(ctx.currentTime + end);
        });
    } catch (e) { /* ignore if AudioContext not available */ }
}

// ── Buyer List (second column) ──────────────────────
function renderBuyerList(buyers) {
    const container = document.getElementById('buyerList');
    if (!container) return;

    if (!buyers.length) {
        container.innerHTML = '<div class="thread-empty" style="padding:20px;"><span style="font-size:12px;">No buyers</span></div>';
        return;
    }

    const sorted = _sortBuyers(buyers);
    container.innerHTML = sorted.map((b, i) => {
        const isActive = b.buyer === currentBuyer;
        const isUnread = b.unread_count > 0;
        const dateStr = b.last_date ? formatRelativeDate(b.last_date) : '';

        const ja = getLang() === 'ja';
        // SVG icon paths (16x16 viewBox)
        const _ico = {
            check: '<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" transform="scale(0.67) translate(0,-1)"/>',
            star2: '<path stroke-linecap="round" stroke-linejoin="round" d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" transform="scale(0.67) translate(0,-1)"/>',
            truck: '<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 18.75a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 0 1-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 0 0-3.213-9.193 2.056 2.056 0 0 0-1.58-.86H14.25" transform="scale(0.67) translate(0,-1)"/>',
            home:  '<path stroke-linecap="round" stroke-linejoin="round" d="m2.25 12 8.954-8.955a1.126 1.126 0 0 1 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75" transform="scale(0.67) translate(0,-1)"/>',
            tag:   '<path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" transform="scale(0.67) translate(0,-1)"/>',
            msg:   '<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" transform="scale(0.67) translate(0,-1)"/>',
            warn:  '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" transform="scale(0.67) translate(0,-1)"/>',
            undo:  '<path stroke-linecap="round" stroke-linejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" transform="scale(0.67) translate(0,-1)"/>',
            x:     '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" transform="scale(0.67) translate(0,-1)"/>',
        };
        const _svg = (path, fill=false) => `<svg width="11" height="11" viewBox="0 0 16 16" fill="${fill ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">${path}</svg>`;
        const statusChips = {
            purchased: { cls: 'chip-purchased',  icon: _svg(_ico.check),   label: ja ? '購入済' : 'Bought' },
            repeat:    { cls: 'chip-repeat',     icon: _svg(_ico.star2),   label: ja ? 'リピーター' : 'Repeat' },
            shipped:   { cls: 'chip-shipped',    icon: _svg(_ico.truck),   label: ja ? '発送済' : 'Shipped' },
            delivered: { cls: 'chip-delivered',  icon: _svg(_ico.home),    label: ja ? '配達済' : 'Delivered' },
            offer:     { cls: 'chip-offer',      icon: _svg(_ico.tag),     label: ja ? 'オファー' : 'Offer' },
            feedback:  { cls: 'chip-feedback',   icon: _svg(_ico.star2),   label: ja ? 'FB済' : 'FB' },
            message:   { cls: 'chip-message',    icon: _svg(_ico.msg),     label: ja ? '問い合わせ' : 'Inquiry' },
            'return':  { cls: 'chip-return',     icon: _svg(_ico.undo),    label: ja ? '返品' : 'Return' },
            cancel:    { cls: 'chip-cancel',     icon: _svg(_ico.x),       label: ja ? 'キャンセル' : 'Cancel' },
            refund:    { cls: 'chip-refund',     icon: _svg(_ico.warn),    label: ja ? '返金' : 'Refund' },
            dispute:   { cls: 'chip-dispute',    icon: _svg(_ico.warn),    label: ja ? 'ディスプート' : 'Dispute' },
        };
        const chips = (b.status || []).map(s => {
            const c = statusChips[s];
            if (!c) return '';
            return `<span class="buyer-chip ${c.cls}">${c.icon}${c.label}</span>`;
        }).join('');

        return `<div class="buyer-item ${isActive ? 'active' : ''} ${isUnread ? 'unread' : ''}" onclick="openThread('${escapeHtml(b.buyer)}', '${escapeHtml(b.item_id || currentItemId)}')" style="animation-delay:${i*30}ms">
            <div class="buyer-top-row">
                <span class="buyer-name">${escapeHtml(b.buyer)}</span>
                ${isUnread ? '<span class="unread-dot"></span>' : ''}
            </div>
            ${chips ? `<div class="buyer-chips">${chips}</div>` : ''}
            <div class="buyer-status-row">
                <span></span>
                <span class="conv-date">${dateStr}</span>
            </div>
        </div>`;
    }).join('');
}

function renderConversations() {
    const container = document.getElementById('convItems');
    if (!conversations.length) {
        container.innerHTML = `
            <div class="thread-empty">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" style="width:48px;height:48px;opacity:0.3;">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
                </svg>
                <span>${getLang() === 'ja' ? 'メッセージがありません' : 'No messages'}</span>
            </div>`;
        return;
    }

    container.innerHTML = conversations.map((conv, i) => {
        const isActive = conv.buyer === currentBuyer && conv.item_id === currentItemId;
        const isUnread = conv.unread_count > 0;
        const dateStr = conv.last_date ? formatRelativeDate(conv.last_date) : '';
        const preview = getLang() === 'ja' && conv.last_message_ja ? conv.last_message_ja : conv.last_message;
        const title = conv.item_title || conv.subject || '';

        const thumbHtml = conv.thumbnail
            ? `<img class="conv-thumb" src="${escapeHtml(conv.thumbnail)}" alt="" loading="lazy">`
            : `<div class="conv-thumb-placeholder"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" width="20" height="20"><path stroke-linecap="round" stroke-linejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"/></svg></div>`;

        return `
            <div class="conv-item ${isActive ? 'active' : ''} ${isUnread ? 'unread' : ''}"
                 onclick="openThread('${escapeHtml(conv.buyer)}', '${escapeHtml(conv.item_id)}')"
                 style="animation-delay:${i * 30}ms">
                ${thumbHtml}
                <div class="conv-content">
                    <div class="conv-top-row">
                        <span class="conv-buyer-name">
                            ${isUnread ? '<span class="unread-dot"></span>' : ''}
                            ${escapeHtml(conv.buyer)}
                        </span>
                        <span class="conv-date">${dateStr}</span>
                    </div>
                    <div class="conv-item-title">${escapeHtml(title.substring(0, 45))}</div>
                    <div class="conv-preview">${escapeHtml((preview || '').substring(0, 55))}</div>
                </div>
            </div>`;
    }).join('');
}

// ── Thread ──────────────────────────────────────────
async function openThread(buyer, itemId) {
    currentBuyer = buyer;
    if (itemId) currentItemId = itemId;

    // Re-render to highlight active items
    renderProductList();
    const item = itemsList.find(i => i.item_id === currentItemId);
    if (item) renderBuyerList(item.buyers || []);

    try {
        const threadKey = `${buyer}|${itemId}`;
        const cached = cacheGet(_cache.threads, threadKey);
        const hadCache = !!cached;
        if (cached) {
            currentThread = cached;
            renderThread();
            showCompose();
        }

        // Fetch fresh data
        const params = new URLSearchParams({ item_id: itemId });
        const resp = await fetch(`/api/chat/conversations/${encodeURIComponent(buyer)}?${params}`);
        const data = await resp.json();
        const freshThread = data.messages || [];
        cacheSet(_cache.threads, threadKey, freshThread);

        // Only re-render if data changed or no cache was shown
        if (!hadCache || freshThread.length !== currentThread.length) {
            currentThread = freshThread;
            renderThread();
            showCompose();
        } else {
            currentThread = freshThread;
        }

        // Mark inbound messages as read
        const unreadIds = currentThread
            .filter(m => m.direction === 'inbound' && !m.is_read)
            .map(m => m.id);
        if (unreadIds.length) {
            // Fire & forget — don't block UI waiting for eBay API
            fetch('/api/chat/mark-read', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message_ids: unreadIds}),
            }).then(() => loadConversations()).catch(() => {});
        }

        // Update buyer info panel (calls loadBuyerScore, loadBuyerFullHistory etc internally)
        updateBuyerPanel(buyer, itemId);

        // Store last inbound message ID for AI draft
        const lastInbound = [...currentThread].reverse().find(m => m.direction === 'inbound');
        lastMessageId = lastInbound ? lastInbound.id : null;

        // Load smart replies for last inbound
        if (lastMessageId) loadSmartReplies(lastMessageId);

        // Mobile: show thread
        document.getElementById('convList')?.classList.add('hidden');
        document.getElementById('threadView')?.classList.add('active');

        // 翻訳バックグラウンド処理（既に表示済みのメッセージを差し込み更新）
        const untranslatedIds = currentThread
            .filter(m => !m.body_translated && m.body && m.direction !== 'system')
            .map(m => m.id);
        if (untranslatedIds.length) {
            fetch('/api/chat/translate-batch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message_ids: untranslatedIds}),
            }).then(r => r.json()).then(d => {
                if (d.translated > 0) {
                    // Re-fetchして翻訳テキストのみ差し込み（フル再レンダリングしない）
                    const p = new URLSearchParams({ item_id: currentItemId });
                    fetch(`/api/chat/conversations/${encodeURIComponent(currentBuyer)}?${p}`)
                        .then(r => r.json()).then(data => {
                            const msgs = data.messages || [];
                            msgs.forEach(msg => {
                                if (!msg.body_translated) return;
                                const bubble = document.querySelector(`.msg-bubble[data-msg-id="${msg.id}"]`);
                                if (!bubble) return;
                                const existing = bubble.querySelector('.msg-translation');
                                const html = escapeHtml(msg.body_translated).replace(/\n/g, '<br>');
                                if (existing) {
                                    existing.classList.remove('msg-translating');
                                    existing.innerHTML = html;
                                } else {
                                    const div = document.createElement('div');
                                    div.className = 'msg-translation';
                                    div.innerHTML = html;
                                    bubble.querySelector('.msg-content')?.insertAdjacentElement('afterend', div);
                                }
                            });
                            currentThread = msgs;
                            cacheSet(_cache.threads, `${currentBuyer}|${currentItemId}`, currentThread);
                        });
                }
            }).catch(() => {});
        }
    } catch (e) {
        console.error('Failed to load thread:', e);
    }
}

function renderThread() {
    const container = document.getElementById('threadMessages');
    const header = document.getElementById('threadHeader');

    if (!currentThread.length) {
        container.innerHTML = '<div class="thread-empty"><span>No messages</span></div>';
        header.style.display = 'none';
        return;
    }

    header.style.display = 'flex';
    document.getElementById('threadBuyer').textContent = currentBuyer;
    document.getElementById('threadSubject').textContent = currentThread[0]?.subject || '';

    container.innerHTML = currentThread.map(msg => {
        const dir = msg.direction; // inbound | outbound | system
        const isSystem = dir === 'system';
        const senderLabel = isSystem ? 'eBay' : (dir === 'inbound' ? msg.sender : (getLang() === 'ja' ? '自分' : 'You'));
        const timeStr = msg.received_at ? formatDateTime(msg.received_at) : '';

        // Sentiment + urgency badges
        let sentimentHtml = '';
        if (dir === 'inbound' && msg.sentiment) {
            const urgencyLabels = {medium:'!', high:'!!', critical:'!!!'};
            const urgencyLabel = urgencyLabels[msg.urgency] || '';
            sentimentHtml = `<span class="sentiment-badge ${msg.sentiment}">${msg.sentiment}${urgencyLabel ? ' ' + urgencyLabel : ''}</span>`;
        }

        // Response time badge
        let responseTimeHtml = '';
        if (dir === 'inbound' && msg.response_time_min != null) {
            const mins = msg.response_time_min;
            const timeLabel = mins < 60 ? `${mins}m` : mins < 1440 ? `${Math.round(mins/60)}h` : `${Math.round(mins/1440)}d`;
            const bgColor = mins <= 60 ? 'var(--success-50)' : mins <= 1440 ? 'var(--warning-50)' : 'var(--error-50)';
            const fgColor = mins <= 60 ? 'var(--success-700)' : mins <= 1440 ? 'var(--warning-700)' : 'var(--error-700)';
            responseTimeHtml = `<span class="response-time-badge" style="background:${bgColor};color:${fgColor};">replied ${timeLabel}</span>`;
        }

        let translationHtml = '';
        if (msg.body_translated && !isSystem) {
            translationHtml = `<div class="msg-translation">${escapeHtml(msg.body_translated).replace(/\n/g, '<br>')}</div>`;
        } else if (!isSystem && dir === 'inbound' && msg.body) {
            translationHtml = `<div class="msg-translation msg-translating">翻訳中...</div>`;
        }

        let attachmentHtml = '';
        if (msg.has_attachment && msg.attachment_urls?.length) {
            attachmentHtml = `<div class="msg-attachments">${
                msg.attachment_urls.map(url => `<img src="${escapeHtml(url)}" loading="lazy">`).join('')
            }</div>`;
        }

        // System messages (eBay notifications) — rich cards or compact style
        if (isSystem) {
            const sSubj = (msg.subject || '').toLowerCase();
            const sBody = (msg.body || '').toLowerCase();
            // Offer notification (sender=eBay, e.g. "📩 You have a new offer: $300.00 for ...")
            if (sSubj.includes('offer') || sBody.includes('you have a new offer') || sBody.includes('best offer')) {
                return `
                <div class="msg-bubble system" data-msg-id="${msg.id}">
                    ${_renderOfferCard(msg)}
                    <div class="msg-time">${timeStr}</div>
                </div>`;
            }
            // Sold notification
            if (sSubj.includes('sold') || sSubj.includes('order confirm') || sSubj.includes('congratulation')
                || sBody.includes('congratulations') || sBody.includes('you sold') || sBody.includes('item sold')) {
                return `
                <div class="msg-bubble system" data-msg-id="${msg.id}">
                    ${_renderSoldCard(msg)}
                    <div class="msg-time">${timeStr}</div>
                </div>`;
            }
            // Cancel request
            if (sSubj.includes('cancel') || sBody.includes('cancellation request') || sBody.includes('cancel request')) {
                return `
                <div class="msg-bubble system" data-msg-id="${msg.id}">
                    ${_renderCancelCard(msg)}
                    <div class="msg-time">${timeStr}</div>
                </div>`;
            }
            // Return request (sometimes sent as system)
            if (sSubj.includes('return') || sBody.includes('return request')) {
                return `
                <div class="msg-bubble system" data-msg-id="${msg.id}">
                    ${_renderReturnCard(msg)}
                    <div class="msg-time">${timeStr}</div>
                </div>`;
            }
            // Default compact system message
            return `
            <div class="msg-bubble system">
                <div class="msg-system-content">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" width="14" height="14"><path stroke-linecap="round" stroke-linejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"/></svg>
                    <span>${escapeHtml((msg.body || msg.subject || '').substring(0, 120))}</span>
                    <span class="msg-time" style="margin:0;padding:0;">${timeStr}</span>
                </div>
            </div>`;
        }

        // Offer / Return / Cancel inline action card (inbound messages)
        let actionCardHtml = '';
        if (dir === 'inbound') {
            const subj = (msg.subject || '').toLowerCase();
            const body = (msg.body || '').toLowerCase();
            if (subj.includes('offer') || body.includes('best offer') || body.includes('made an offer')) {
                actionCardHtml = _renderOfferCard(msg);
            } else if (subj.includes('return') || body.includes('return request') || body.includes('wants to return')) {
                actionCardHtml = _renderReturnCard(msg);
            } else if (subj.includes('cancel') || body.includes('cancellation')) {
                actionCardHtml = _renderCancelCard(msg);
            }
        }

        const avatarHtml = dir === 'inbound'
            ? _buyerAvatarHtml(msg.sender)
            : _sellerAvatarHtml();

        return `
            <div class="msg-bubble ${dir}" data-msg-id="${msg.id}">
                ${avatarHtml}
                <div class="msg-body">
                    <div class="msg-sender">
                        ${escapeHtml(senderLabel)}
                        ${sentimentHtml}
                    </div>
                    <div class="msg-content">${escapeHtml(msg.body).replace(/\n/g, '<br>')}</div>
                    ${translationHtml}
                    ${attachmentHtml}
                    ${actionCardHtml}
                    <div class="msg-time">${timeStr} ${responseTimeHtml}</div>
                </div>
            </div>`;
    }).join('');

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// ── Offer / Return / Sold / Cancel Action Cards ──────────────────────
// Parse offer details from eBay message body (no API call needed for display)
function _parseOfferFromBody(body) {
    if (!body) return {};
    // Also check subject line (passed as body sometimes) for "$300.00" pattern
    // eBay format: "Offer: $300.00" / "offer of $100" / "offered $100"
    const offerMatch = body.match(/offer[:\s]+\$?([\d,]+\.?\d*)/i)
        || body.match(/(?:offer(?:ed)?|bid)(?:\s+of)?\s+\$?([\d,]+\.?\d*)/i)
        || body.match(/\$([\d,]+\.\d{2})/);
    // Subject line: "You have a new offer: $300.00 for ..."
    const subjPriceMatch = body.match(/new offer[:\s]+\$?([\d,]+\.?\d*)/i);
    // List price: "similar items sell for $440" / "listed at $399"
    const listMatch = body.match(/(?:similar items?\s+sell\s+for|listed?\s+at|your\s+price)[:\s]+\$?([\d,]+\.?\d*)/i);
    // Quantity
    const qtyMatch = body.match(/(?:quantity|qty)[:\s]+(\d+)/i)
        || body.match(/for\s+(\d+)\s+item/i);
    const rawPrice = subjPriceMatch ? subjPriceMatch[1] : (offerMatch ? offerMatch[1] : null);
    return {
        offerPrice: rawPrice   ? parseFloat(rawPrice.replace(/,/g, ''))       : null,
        listPrice:  listMatch  ? parseFloat(listMatch[1].replace(/,/g, ''))   : null,
        quantity:   qtyMatch   ? parseInt(qtyMatch[1])                         : 1,
    };
}

function _renderOfferCard(msg) {
    const ja = getLang() === 'ja';
    const msgId = msg.id;
    const itemId = currentItemId;
    const item = itemsList.find(i => i.item_id === itemId);
    const thumb = item?.thumbnail || '';
    const thumbHtml = thumb
        ? `<img src="${escapeHtml(thumb)}" class="action-card-thumb" onerror="this.style.display='none'">`
        : '';

    // Parse price info from message body — show instantly, no API call needed
    const parsed = _parseOfferFromBody(msg.body || '');
    let priceHtml = '';
    if (parsed.offerPrice) {
        const listPart = parsed.listPrice
            ? ` <span class="action-price-list"> / ${ja ? '販売価格' : 'List'} $${parsed.listPrice.toFixed(2)}</span>`
            : '';
        priceHtml = `<div class="action-card-row">
            <span class="action-price-main">${ja ? 'オファー' : 'Offer'} $${parsed.offerPrice.toFixed(2)}</span>${listPart}
            <span class="action-price-qty">${ja ? '数量' : 'Qty'}: ${parsed.quantity}</span>
        </div>`;
    }

    // Silently load offer_id in background (needed for button actions only)
    setTimeout(() => _prefetchOfferId(itemId, msgId), 300);

    return `
    <div class="action-card action-card-offer" id="offerCard-${msgId}">
        <div class="action-card-title action-card-title-offer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z"/></svg>
            ${ja ? 'オファー' : 'Offer'}
        </div>
        <div class="action-card-inner">
            ${thumbHtml}
            <div class="action-card-content">
                <div class="action-card-subtitle">${ja ? 'オファーが届きました！' : 'You received an offer!'}</div>
                ${priceHtml}
                <div class="offer-action-selector" id="offerSelector-${msgId}">
                    <button class="offer-sel-btn" data-action="Counter"
                        onclick="selectOfferAction('${escapeHtml(itemId)}','${msgId}','Counter')">${ja ? 'カウンター' : 'Counteroffer'}</button>
                    <button class="offer-sel-btn" data-action="Accept"
                        onclick="selectOfferAction('${escapeHtml(itemId)}','${msgId}','Accept')">${ja ? '承認' : 'Accept'}</button>
                    <button class="offer-sel-btn" data-action="Decline"
                        onclick="selectOfferAction('${escapeHtml(itemId)}','${msgId}','Decline')">${ja ? '拒否' : 'Decline'}</button>
                </div>
                <div id="counterInput-${msgId}" style="display:none;margin-top:8px;">
                    <input type="number" step="0.01" min="0"
                        placeholder="${ja ? '金額 (USD)' : 'Price (USD)'}"
                        id="counterPrice-${msgId}"
                        style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:130px;">
                </div>
                <div id="offerConfirm-${msgId}" style="display:none;margin-top:8px;">
                    <button class="offer-confirm-btn" id="offerConfirmBtn-${msgId}"
                        onclick="submitOfferAction('${escapeHtml(itemId)}','${msgId}')">
                        ${ja ? '送信' : 'Send'}
                    </button>
                </div>
            </div>
        </div>
    </div>`;
}

function _renderReturnCard(msg) {
    const ja = getLang() === 'ja';
    const msgId = msg.id;
    const item = itemsList.find(i => i.item_id === currentItemId);
    const thumb = item?.thumbnail || '';
    const thumbHtml = thumb
        ? `<img src="${escapeHtml(thumb)}" class="action-card-thumb" onerror="this.style.display='none'">`
        : '';

    // Extract Return ID from message body (e.g. "Return ID: 5316310449" or "#5316310449")
    const bodyText = msg.body || msg.subject || '';
    const returnIdMatch = bodyText.match(/(?:return[^\d]*id[:\s#]*|#)(\d{7,})/i)
        || bodyText.match(/(\d{10,})/);
    const returnId = returnIdMatch ? returnIdMatch[1] : '';
    const returnIdHtml = returnId
        ? `<a href="https://www.ebay.com/returns/v2/cases/${returnId}" target="_blank" class="action-id-link">${returnId}</a>`
        : '';

    // Auto-load return details
    setTimeout(() => loadReturnsForCard(msgId), 200);

    return `
    <div class="action-card action-card-return" id="returnCard-${msgId}">
        <div class="action-card-title action-card-title-return">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3"/></svg>
            ${ja ? 'リターンリクエスト' : 'Return Request'}
        </div>
        <div class="action-card-inner">
            ${thumbHtml}
            <div class="action-card-content">
                ${returnId ? `<div class="action-card-info">Return ID: ${returnIdHtml}</div>` : ''}
                <div id="returnList-${msgId}" class="action-card-info">${ja ? '読み込み中...' : 'Loading...'}</div>
                <div class="action-card-btns">
                    <button onclick="respondReturnFromCard('${msgId}','accept')" class="action-btn action-btn-accept">${ja ? '承認' : 'Accept'}</button>
                    <button onclick="respondReturnFromCard('${msgId}','decline')" class="action-btn action-btn-decline">${ja ? '拒否' : 'Decline'}</button>
                </div>
            </div>
        </div>
    </div>`;
}

function _renderSoldCard(msg) {
    const ja = getLang() === 'ja';
    const body = msg.body || '';
    const item = itemsList.find(i => i.item_id === currentItemId);
    const thumb = item?.thumbnail || '';
    const thumbHtml = thumb
        ? `<img src="${escapeHtml(thumb)}" class="action-card-thumb" onerror="this.style.display='none'">`
        : '';

    // Try to extract order details from eBay message body
    const orderMatch  = body.match(/order\s*(?:no\.?|number|id|#)[:\s]*([0-9\-]{8,})/i);
    const priceMatch  = body.match(/(?:total|price|amount)[:\s]*([A-Z]{0,3}\$?\s*[\d,]+\.?\d*)/i)
        || body.match(/([\d,]+\.\d{2})\s*(CAD|USD|JPY|GBP|EUR|AUD)/i);
    const skuMatch    = body.match(/(?:sku|custom label)[:\s]*([A-Z0-9\-_]+)/i);
    const shipByMatch = body.match(/(?:ship\s*by|dispatch\s*by)[:\s]*([^\n<]+)/i);

    const orderId  = orderMatch  ? orderMatch[1].trim()  : '';
    const price    = priceMatch  ? priceMatch[0].trim()  : '';
    const sku      = skuMatch    ? skuMatch[1].trim()    : '';
    const shipBy   = shipByMatch ? shipByMatch[1].trim() : '';

    let detailHtml = `<div class="action-card-subtitle">${ja ? '商品が売れました！' : 'Item sold!'}</div>`;
    if (price)   detailHtml += `<div class="action-card-row"><span class="action-sold-price">${escapeHtml(price)}</span></div>`;
    if (orderId) detailHtml += `<div class="action-meta">Order no: ${escapeHtml(orderId)}</div>`;
    if (sku)     detailHtml += `<div class="action-meta">SKU: ${escapeHtml(sku)}</div>`;
    if (shipBy)  detailHtml += `<div class="action-meta">${ja ? '発送期限' : 'Ship by'}: ${escapeHtml(shipBy)}</div>`;

    return `
    <div class="action-card action-card-sold">
        <div class="action-card-title action-card-title-sold">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 0 0-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 0 0-16.536-1.84M7.5 14.25 5.106 5.272M6 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm12.75 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z"/></svg>
            ${ja ? 'Sold' : 'Sold'}
        </div>
        <div class="action-card-inner">
            ${thumbHtml}
            <div class="action-card-content">${detailHtml}</div>
        </div>
    </div>`;
}

function _renderCancelCard(msg) {
    const ja = getLang() === 'ja';
    const body = msg.body || '';
    const item = itemsList.find(i => i.item_id === currentItemId);
    const thumb = item?.thumbnail || '';
    const thumbHtml = thumb
        ? `<img src="${escapeHtml(thumb)}" class="action-card-thumb" onerror="this.style.display='none'">`
        : '';

    // Extract Cancel ID and reason
    const cancelIdMatch = body.match(/cancel(?:lation)?\s*(?:id|#)[:\s]*(\d{7,})/i)
        || body.match(/(\d{10,})/);
    const reasonMatch   = body.match(/reason[:\s]+([^\n<.]+)/i)
        || body.match(/because[:\s]+([^\n<.]+)/i);

    const cancelId = cancelIdMatch ? cancelIdMatch[1] : '';
    const reason   = reasonMatch   ? reasonMatch[1].trim() : '';

    const cancelIdHtml = cancelId
        ? `<a href="https://www.ebay.com/cancel/${cancelId}" target="_blank" class="action-id-link">${cancelId}</a>`
        : '';

    return `
    <div class="action-card action-card-cancel">
        <div class="action-card-title action-card-title-cancel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
            ${ja ? 'キャンセルリクエスト' : 'Cancellation Request'}
        </div>
        <div class="action-card-inner">
            ${thumbHtml}
            <div class="action-card-content">
                ${cancelId ? `<div class="action-card-info">Cancel ID: ${cancelIdHtml}</div>` : ''}
                ${reason   ? `<div class="action-card-info" style="color:var(--text-primary);">${escapeHtml(reason)}</div>` : ''}
                ${!cancelId && !reason ? `<div class="action-card-info">${escapeHtml((msg.body || '').substring(0, 100))}</div>` : ''}
            </div>
        </div>
    </div>`;
}

let _offerCardData = {}; // msgId → offers[]
let _returnCardData = {}; // msgId → returns[]

// Silently prefetch offer_id in background (for button actions) — no UI update
async function _prefetchOfferId(itemId, msgId) {
    if (_offerCardData[msgId]) return; // already cached
    try {
        const resp = await fetch(`/api/chat/offers/${encodeURIComponent(itemId)}`);
        const data = await resp.json();
        _offerCardData[msgId] = data.offers || [];
    } catch(e) { /* silent */ }
}

function _selectedOfferId(msgId) {
    return _offerCardData[msgId]?.[0]?.offer_id || '';
}

// Track selected action per offer card
const _offerSelectedAction = {}; // msgId → 'Counter'|'Accept'|'Decline'

function selectOfferAction(itemId, msgId, action) {
    _offerSelectedAction[msgId] = action;
    // Toggle button styles
    const selector = document.getElementById(`offerSelector-${msgId}`);
    selector?.querySelectorAll('.offer-sel-btn').forEach(btn => {
        const isActive = btn.dataset.action === action;
        btn.classList.toggle('offer-sel-btn--active', isActive);
        btn.classList.toggle('offer-sel-btn--counter', isActive && action === 'Counter');
        btn.classList.toggle('offer-sel-btn--accept',  isActive && action === 'Accept');
        btn.classList.toggle('offer-sel-btn--decline',  isActive && action === 'Decline');
    });
    // Show/hide price input
    document.getElementById(`counterInput-${msgId}`).style.display =
        action === 'Counter' ? 'block' : 'none';
    // Show confirm button with appropriate label
    const confirmWrap = document.getElementById(`offerConfirm-${msgId}`);
    const confirmBtn  = document.getElementById(`offerConfirmBtn-${msgId}`);
    const ja = getLang() === 'ja';
    confirmWrap.style.display = 'block';
    if (action === 'Counter') {
        confirmBtn.textContent = ja ? 'カウンター送信' : 'Send Counteroffer';
        confirmBtn.className = 'offer-confirm-btn offer-confirm-btn--counter';
    } else if (action === 'Accept') {
        confirmBtn.textContent = ja ? '承認する' : 'Accept Offer';
        confirmBtn.className = 'offer-confirm-btn offer-confirm-btn--accept';
    } else {
        confirmBtn.textContent = ja ? '拒否する' : 'Decline Offer';
        confirmBtn.className = 'offer-confirm-btn offer-confirm-btn--decline';
    }
}

async function submitOfferAction(itemId, msgId) {
    const action = _offerSelectedAction[msgId];
    if (!action) return;
    if (!_selectedOfferId(msgId)) await _prefetchOfferId(itemId, msgId);
    const offerId = _selectedOfferId(msgId);
    if (!offerId) { alert(getLang() === 'ja' ? 'アクティブなオファーが見つかりません' : 'No active offer found'); return; }

    const payload = { offer_id: offerId, action };
    if (action === 'Counter') {
        const price = parseFloat(document.getElementById(`counterPrice-${msgId}`)?.value || '0');
        if (!price || price <= 0) {
            alert(getLang() === 'ja' ? '金額を入力してください' : 'Enter a valid price');
            return;
        }
        payload.counter_price = price;
    }

    const btn = document.getElementById(`offerConfirmBtn-${msgId}`);
    if (btn) { btn.disabled = true; btn.textContent = '...'; }

    const resp = await fetch(`/api/chat/offers/${encodeURIComponent(itemId)}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    const data = await resp.json();
    const card = document.getElementById(`offerCard-${msgId}`);
    if (data.success) {
        const ja = getLang() === 'ja';
        const msgs = {
            Accept:  ja ? 'オファーを承認しました ✓' : 'Offer accepted ✓',
            Decline: ja ? 'オファーを拒否しました ✓' : 'Offer declined ✓',
            Counter: ja ? `カウンター $${payload.counter_price?.toFixed(2)} を送信しました ✓`
                        : `Counter $${payload.counter_price?.toFixed(2)} sent ✓`,
        };
        card.innerHTML = `<div class="action-card-done">${msgs[action]}</div>`;
    } else {
        alert('Error: ' + (data.error || 'Unknown'));
        if (btn) { btn.disabled = false; btn.textContent = action; }
    }
}

async function loadReturnsForCard(msgId) {
    const el = document.getElementById(`returnList-${msgId}`);
    if (!el) return;
    el.textContent = '読み込み中...';
    try {
        const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(currentBuyer)}/troubles`);
        const data = await resp.json();
        const returns = data.returns || [];
        _returnCardData[msgId] = returns;
        if (!returns.length) { el.textContent = getLang() === 'ja' ? 'アクティブなリターンなし' : 'No active returns'; return; }
        el.innerHTML = returns.map((r, i) =>
            `<label style="cursor:pointer;display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                <input type="radio" name="return-${msgId}" value="${escapeHtml(r.return_id||String(i))}" ${i===0?'checked':''}>
                <span>${r.icon} ${getLang()==='ja' ? r.status_ja : r.status}</span>
                ${r.is_urgent ? '<span style="color:var(--error-600);font-size:11px;font-weight:700;">要対応</span>' : ''}
            </label>`
        ).join('');
    } catch(e) { el.textContent = 'Error: ' + e.message; }
}

async function respondReturnFromCard(msgId, action) {
    const radio = document.querySelector(`input[name="return-${msgId}"]:checked`);
    const returnId = radio?.value || _returnCardData[msgId]?.[0]?.return_id || '';
    if (!returnId) { alert(getLang() === 'ja' ? 'リターン詳細をロードしてください' : 'Load return details first'); return; }
    if (!confirm(`${action === 'accept' ? 'Accept' : 'Decline'} return?`)) return;
    const resp = await fetch(`/api/chat/return/${encodeURIComponent(returnId)}/${action}`, {method: 'POST'});
    const data = await resp.json();
    const card = document.getElementById(`returnCard-${msgId}`);
    if (data.success) {
        card.innerHTML = `<div class="action-card-done">${getLang()==='ja' ? `リターン${action==='accept'?'承認':'拒否'}完了` : `Return ${action}ed`} ✓</div>`;
    } else {
        alert('Error: ' + (data.error || 'Unknown'));
    }
}

function showCompose() {
    document.getElementById('composeArea').style.display = 'block';
    document.getElementById('composeInput').value = '';
    document.getElementById('sendBtn').disabled = true;
    uploadedImageUrls = [];
    hideTranslationPreview();
}

// ── Send Message ────────────────────────────────────
async function sendMessage() {
    const input = document.getElementById('composeInput');
    const text = input.value.trim();
    if (!text || !currentBuyer || !currentItemId) return;

    const btn = document.getElementById('sendBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span>';

    try {
        const resp = await fetch('/api/chat/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                buyer: currentBuyer,
                item_id: currentItemId,
                body_en: text,
                image_urls: uploadedImageUrls,
            }),
        });
        const result = await resp.json();

        if (result.success) {
            input.value = '';
            uploadedImageUrls = [];
            hideTranslationPreview();
            // Invalidate caches after sending
            cacheInvalidate(_cache.threads, `${currentBuyer}|${currentItemId}`);
            cacheInvalidate(_cache.scores, currentBuyer);
            cacheInvalidate(_cache.histories, currentBuyer);
            await openThread(currentBuyer, currentItemId);
        } else {
            alert(`Send failed: ${result.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Send error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="20" height="20"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" /></svg>';
    }
}

function handleComposeKey(e) {
    const input = e.target;
    document.getElementById('sendBtn').disabled = !input.value.trim();

    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        if (input.value.trim()) sendMessage();
    }
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// ── AI Draft ────────────────────────────────────────
async function generateDraft() {
    if (!lastMessageId) return;

    const btn = event.target.closest('button');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span>';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/chat/draft', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message_id: lastMessageId}),
        });
        const data = await resp.json();

        if (data.draft_reply) {
            document.getElementById('composeInput').value = data.draft_reply;
            document.getElementById('sendBtn').disabled = false;
            autoResize(document.getElementById('composeInput'));
            // Show analysis + draft preview with JA translation + refine UI
            showDraftPreview(data.draft_reply, data.draft_reply_ja || '', data.analysis || '');
        } else if (data.error) {
            alert(`Draft error: ${data.error}`);
        }
    } catch (e) {
        alert(`Draft error: ${e.message}`);
    } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
    }
}

function showDraftPreview(draftEn, draftJa, analysis) {
    const preview = document.getElementById('translationPreview');
    if (!preview) return;
    const ja = getLang() === 'ja';

    // 分析テキストをHTMLに変換（## → 太字、- → リスト）
    let analysisHtml = '';
    if (analysis) {
        analysisHtml = escapeHtml(analysis)
            .replace(/## (.+)/g, '<strong style="display:block;margin-top:8px;color:var(--text-primary);">$1</strong>')
            .replace(/^- (.+)$/gm, '<div style="padding-left:12px;">- $1</div>')
            .replace(/\n/g, '<br>');
    }

    preview.innerHTML = `
        ${analysis ? `
        <div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid var(--border);">
            <div style="font-size:12px;line-height:1.6;color:var(--text-secondary);">${analysisHtml}</div>
        </div>` : ''}
        <div style="margin-bottom:8px;">
            <strong style="font-size:11px;color:var(--text-muted);">${ja ? '返信ドラフト（日本語訳）' : 'Draft (Japanese)'}</strong>
            <div style="margin-top:4px;font-size:12px;line-height:1.6;color:var(--text-primary);white-space:pre-wrap;">${escapeHtml(draftJa || (ja ? '翻訳中...' : 'Translating...'))}</div>
        </div>
        <div style="display:flex;gap:6px;align-items:center;margin-top:8px;padding-top:8px;border-top:1px solid var(--border);">
            <input type="text" id="refineInput"
                   placeholder="${ja ? '修正指示（例: 1350がギリギリのライン、もっとカジュアルに）' : 'Refine (e.g. counter at £1350, more casual)'}"
                   style="flex:1;padding:7px 10px;border:1px solid var(--border);border-radius:20px;font-size:12px;font-family:inherit;"
                   onkeydown="if(event.key==='Enter'&&!event.isComposing){event.preventDefault();refineDraft();}">
            <button onclick="refineDraft()" style="padding:6px 14px;background:var(--blue);color:#fff;border:none;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap;">${ja ? '修正' : 'Refine'}</button>
        </div>`;
    preview.classList.add('visible');
    // スクロールして表示
    preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function refineDraft() {
    const input = document.getElementById('refineInput');
    const instruction = input?.value?.trim();
    if (!instruction || !lastMessageId) return;

    const currentDraft = document.getElementById('composeInput')?.value || '';
    if (!currentDraft) return;

    input.disabled = true;

    try {
        const resp = await fetch('/api/chat/draft/refine', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message_id: lastMessageId,
                current_draft: currentDraft,
                instruction: instruction,
            }),
        });
        const data = await resp.json();

        if (data.draft_reply) {
            document.getElementById('composeInput').value = data.draft_reply;
            autoResize(document.getElementById('composeInput'));
            // Keep existing analysis, update draft
            const existingAnalysis = document.querySelector('#translationPreview strong')?.closest('div')?.querySelector('div[style*="line-height: 1.6"]')?.innerHTML || '';
            showDraftPreview(data.draft_reply, data.draft_reply_ja || '', '');
            input.value = '';
        } else if (data.error) {
            alert(`Refine error: ${data.error}`);
        }
    } catch (e) {
        alert(`Refine error: ${e.message}`);
    } finally {
        input.disabled = false;
    }
}

// ── Translation ─────────────────────────────────────
async function translateCompose() {
    const input = document.getElementById('composeInput');
    const text = input.value.trim();
    if (!text) return;

    const preview = document.getElementById('translationPreview');
    preview.textContent = getLang() === 'ja' ? '翻訳中...' : 'Translating...';
    preview.classList.add('visible');

    // Detect buyer's language from the latest inbound message
    const lastInbound = [...currentThread].reverse().find(m => m.direction === 'inbound');
    const buyerMsg = lastInbound?.body || '';

    try {
        const resp = await fetch('/api/chat/draft/refine', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message_id: lastMessageId || 0,
                current_draft: '',
                instruction: `以下の日本語をバイヤーのメッセージと同じ言語に翻訳してください。バイヤーのメッセージ: "${buyerMsg.substring(0, 200)}"\n\n翻訳対象:\n${text}\n\n署名はRokiで。出力は翻訳結果のみ。`,
            }),
        });
        const data = await resp.json();

        if (data.draft_reply) {
            preview.innerHTML = `<strong style="font-size:11px;color:var(--text-muted);">${getLang() === 'ja' ? '元の日本語' : 'Original'}</strong><div style="margin:4px 0;font-size:12px;color:var(--text-secondary);">${escapeHtml(text)}</div>`;
            input.value = data.draft_reply;
            document.getElementById('sendBtn').disabled = false;
            autoResize(input);
        }
    } catch (e) {
        preview.textContent = `Error: ${e.message}`;
    }
}

function hideTranslationPreview() {
    const preview = document.getElementById('translationPreview');
    if (preview) {
        preview.classList.remove('visible');
        preview.textContent = '';
    }
}

// ── Image Upload ────────────────────────────────────
async function handleImageUpload(input) {
    const file = input.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/chat/upload-image', {
            method: 'POST',
            body: formData,
        });
        const data = await resp.json();

        if (data.success && data.url) {
            uploadedImageUrls.push(data.url);
            const preview = document.getElementById('translationPreview');
            preview.textContent = `📎 ${uploadedImageUrls.length} image(s) attached`;
            preview.classList.add('visible');
        } else {
            alert(`Upload failed: ${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Upload error: ${e.message}`);
    }

    input.value = '';
}

// ── Sync ────────────────────────────────────────────
async function syncMessages(silent = false) {
    const btn = document.getElementById('syncBtn');
    const status = document.getElementById('syncStatus');

    if (!silent) {
        btn.disabled = true;
        btn.innerHTML = '<span class="loading-spinner"></span>';
    }
    status.textContent = getLang() === 'ja' ? '同期中...' : 'Syncing...';

    try {
        const resp = await fetch('/api/chat/sync', {method: 'POST'});
        const data = await resp.json();
        const msg = getLang() === 'ja'
            ? `同期完了: 新規${data.new || 0}件`
            : `Synced: ${data.new || 0} new`;
        status.textContent = msg;
        // Clear all caches on sync
        cacheInvalidate(_cache.threads);
        cacheInvalidate(_cache.scores);
        cacheInvalidate(_cache.histories);
        await loadConversations();

        // Refresh current thread if open
        if (currentBuyer && currentItemId) {
            openThread(currentBuyer, currentItemId);
        }
    } catch (e) {
        status.textContent = `Error: ${e.message}`;
    } finally {
        if (!silent) {
            btn.disabled = false;
            btn.innerHTML = `<span data-en="Sync" data-ja="同期">${getLang() === 'ja' ? '同期' : 'Sync'}</span>`;
        }
        setTimeout(() => { status.textContent = ''; }, 5000);
    }
}

// ── Filters ─────────────────────────────────────────
function setFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    loadConversations();
}

function searchConversations() {
    loadConversations();
}

// ── Mark Read ───────────────────────────────────────
async function markAllRead() {
    try {
        await fetch('/api/chat/mark-all-read', {method: 'POST'});
        await loadConversations();
    } catch (e) {
        console.error('Mark all read failed:', e);
    }
}

async function toggleReadStatus() {
    if (!currentThread.length) return;
    const inboundIds = currentThread.filter(m => m.direction === 'inbound').map(m => m.id);
    if (!inboundIds.length) return;

    const allRead = currentThread.filter(m => m.direction === 'inbound').every(m => m.is_read);
    const endpoint = allRead ? '/api/chat/mark-unread' : '/api/chat/mark-read';

    try {
        await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message_ids: inboundIds}),
        });
        await loadConversations();
        await openThread(currentBuyer, currentItemId);
    } catch (e) {
        console.error('Toggle read failed:', e);
    }
}

// ── Templates ───────────────────────────────────────
async function openTemplateModal() {
    document.getElementById('templateModal').classList.add('open');
    await loadTemplates();
}

function closeTemplateModal() {
    document.getElementById('templateModal').classList.remove('open');
}

async function loadTemplates(search = '') {
    try {
        const params = new URLSearchParams({search});
        const resp = await fetch(`/api/chat/templates?${params}`);
        const data = await resp.json();
        renderTemplates(data.templates || []);
    } catch (e) {
        console.error('Failed to load templates:', e);
    }
}

function renderTemplates(templates) {
    const container = document.getElementById('templateList');
    if (!templates.length) {
        container.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:20px;">
            <span>${getLang() === 'ja' ? 'テンプレートがありません' : 'No templates found'}</span>
        </div>`;
        return;
    }

    container.innerHTML = templates.map(t => `
        <div class="template-item" onclick="selectTemplate(${t.id})">
            <div class="tmpl-title">${escapeHtml(t.title)}</div>
            <div class="tmpl-preview">${escapeHtml(t.body_en?.substring(0, 80) || '')}</div>
            <span class="tmpl-category">${t.category}</span>
        </div>
    `).join('');
}

async function selectTemplate(templateId) {
    try {
        const resp = await fetch(`/api/chat/templates/${templateId}/use`, {method: 'POST'});
        const data = await resp.json();
        if (data.body_en) {
            document.getElementById('composeInput').value = data.body_en;
            document.getElementById('sendBtn').disabled = false;
            autoResize(document.getElementById('composeInput'));
        }
        closeTemplateModal();
    } catch (e) {
        console.error('Failed to use template:', e);
    }
}

function searchTemplates() {
    const q = document.getElementById('templateSearchInput')?.value || '';
    loadTemplates(q);
}

// ── Buyer Panel ─────────────────────────────────────
function updateBuyerPanel(buyer, itemId) {
    const container = document.getElementById('buyerInfoContent');
    const ja = getLang() === 'ja';

    // Find item info from itemsList
    const item = itemsList.find(i => i.item_id === itemId);
    const itemTitle = item?.title || '';
    const itemThumb = item?.thumbnail || '';

    const ebayItemUrl = itemId ? `https://www.ebay.com/itm/${itemId}` : '';
    const ebayBuyerUrl = buyer ? `https://www.ebay.com/usr/${buyer}` : '';

    container.innerHTML = `
        <!-- Item Info -->
        ${itemId ? `
        <h4>${ja ? '商品情報' : 'Item Info'}</h4>
        <div class="buyer-info-card" id="itemInfoCard">
            ${itemThumb ? `<img src="${escapeHtml(itemThumb)}" style="width:100%;aspect-ratio:1;object-fit:contain;border-radius:8px;margin-bottom:10px;background:var(--gray-100);" loading="lazy">` : ''}
            <div class="info-value" style="font-size:13px;line-height:1.4;margin-bottom:6px;">${escapeHtml(itemTitle || '#' + itemId)}</div>
            <div id="itemDetailsGrid" style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px;margin-bottom:8px;color:var(--text-secondary);"></div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
                <a href="${ebayItemUrl}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;background:var(--brand-25);color:var(--blue);border-radius:6px;font-size:11px;font-weight:600;text-decoration:none;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>
                    eBay${ja ? 'で見る' : ' Listing'}
                </a>
            </div>
        </div>` : ''}

        <!-- Buyer Info -->
        <h4>${ja ? 'バイヤー情報' : 'Buyer Info'}</h4>
        <div class="buyer-info-card">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div class="info-value" style="font-size:14px;font-weight:700;">${escapeHtml(buyer)}</div>
                <a href="${ebayBuyerUrl}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:3px;padding:4px 8px;background:var(--brand-25);color:var(--blue);border-radius:6px;font-size:11px;font-weight:600;text-decoration:none;">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>
                    eBay
                </a>
            </div>
            <div id="buyerDetailsSection" style="margin-top:8px;font-size:12px;color:var(--text-secondary);"></div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:6px;">${ja ? 'スレッド' : 'Thread'}: ${currentThread.length} ${ja ? '件' : 'messages'}</div>
        </div>

        <div id="buyerScoreSection"></div>
        <div id="buyerHistorySection"></div>
        <div id="buyerTroubleSection"></div>
        <div id="productEditSection"></div>
        <div id="responseStatsSection"></div>`;

    loadBuyerDetails(buyer, itemId);
    loadBuyerScore(buyer);
    loadBuyerFullHistory(buyer);
    loadBuyerTroubles(buyer);
    loadResponseStats();
    if (itemId) {
        loadProductEdit(itemId);
        loadItemDetails(itemId);
    }
}

// ── Item Details (right panel) ──────────────────────
async function loadItemDetails(itemId) {
    const grid = document.getElementById('itemDetailsGrid');
    if (!grid || !itemId) return;

    try {
        let data = cacheGet(_cache.items, itemId, _cache.TTL_ITEM);
        if (!data) {
            const resp = await fetch(`/api/chat/item/${itemId}`);
            if (!resp.ok) return;
            data = await resp.json();
            if (!data || data.error) return;
            cacheSet(_cache.items, itemId, data);
        }

        const ja = getLang() === 'ja';
        grid.innerHTML = `
            <div><span style="color:var(--text-muted);">SKU</span><br><strong style="font-family:monospace;font-size:10px;">${escapeHtml(data.sku || '-')}</strong></div>
            <div><span style="color:var(--text-muted);">${ja ? '価格' : 'Price'}</span><br><strong>$${(data.price_usd || 0).toFixed(2)}</strong></div>
            <div><span style="color:var(--text-muted);">${ja ? '数量' : 'Qty'}</span><br><strong>${data.quantity ?? '-'}</strong></div>
            <div><span style="color:var(--text-muted);">Item ID</span><br><strong style="font-family:monospace;font-size:10px;">${itemId}</strong></div>
        `;
    } catch (e) {
        // Listing not found in local DB - OK
    }
}

// ── Smart Replies (ワンタップ返信候補) ──────────────
async function loadSmartReplies(messageId) {
    const container = document.getElementById('smartRepliesContainer');
    if (!container) return;
    container.innerHTML = '<span class="loading-spinner"></span>';
    container.style.display = 'flex';

    try {
        const resp = await fetch(`/api/chat/smart-replies/${messageId}`);
        const data = await resp.json();
        if (data.replies?.length) {
            container.innerHTML = data.replies.map(r =>
                `<button class="smart-reply-btn" onclick="useSmartReply(this)" title="${escapeHtml(r)}">${escapeHtml(r.length > 50 ? r.substring(0, 47) + '...' : r)}</button>`
            ).join('');
        } else {
            container.style.display = 'none';
        }
    } catch {
        container.style.display = 'none';
    }
}

function useSmartReply(btn) {
    const text = btn.title || btn.textContent;
    document.getElementById('composeInput').value = text;
    document.getElementById('sendBtn').disabled = false;
    autoResize(document.getElementById('composeInput'));
}

// ── Buyer Details (name, address, phone) ────────────
async function loadBuyerDetails(buyer, itemId) {
    const section = document.getElementById('buyerDetailsSection');
    if (!section) return;

    try {
        const params = new URLSearchParams({ item_id: itemId || '' });
        const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/details?${params}`);
        const data = await resp.json();

        if (!data.full_name && !data.address) {
            section.innerHTML = '';
            return;
        }

        const ja = getLang() === 'ja';
        const rows = [];
        if (data.full_name) rows.push(`<div><span style="color:var(--text-muted);">${ja ? '氏名' : 'Name'}:</span> <strong>${escapeHtml(data.full_name)}</strong></div>`);
        if (data.country) rows.push(`<div><span style="color:var(--text-muted);">${ja ? '国' : 'Country'}:</span> ${escapeHtml(data.country)}</div>`);
        if (data.address) rows.push(`<div style="margin-top:2px;"><span style="color:var(--text-muted);">${ja ? '住所' : 'Address'}:</span> <span style="font-size:11px;">${escapeHtml(data.address)}</span></div>`);
        if (data.phone) rows.push(`<div><span style="color:var(--text-muted);">${ja ? '電話' : 'Phone'}:</span> ${escapeHtml(data.phone)}</div>`);

        section.innerHTML = rows.join('');
    } catch (e) {
        console.error('Failed to load buyer details:', e);
    }
}

// ── Buyer Score ─────────────────────────────────────
async function loadBuyerScore(buyer) {
    const section = document.getElementById('buyerScoreSection');
    if (!section) return;

    try {
        let data = cacheGet(_cache.scores, buyer);
        if (!data) {
            const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/score`);
            data = await resp.json();
            cacheSet(_cache.scores, buyer, data);
        }

        const tierConfig = {
            vip:     { label: 'VIP',    color: '#7C3AED', bg: '#7C3AED15', icon: '⭐' },
            good:    { label: 'Good',   color: '#12B76A', bg: '#12B76A15', icon: '👍' },
            normal:  { label: 'Normal', color: '#667085', bg: '#66708515', icon: '👤' },
            caution: { label: 'Caution',color: '#F04438', bg: '#F0443815', icon: '⚠️' },
        };
        const tier = tierConfig[data.tier] || tierConfig.normal;

        section.innerHTML = `
            <h4 style="margin-top:16px;">${getLang() === 'ja' ? 'バイヤー評価' : 'Buyer Score'}</h4>
            <div class="buyer-info-card">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <span style="font-size:16px;">${tier.icon}</span>
                    <span style="padding:3px 10px;border-radius:6px;background:${tier.bg};color:${tier.color};font-weight:700;font-size:13px;">${tier.label}</span>
                </div>
                <div style="font-size:12px;color:var(--text-secondary);margin-bottom:6px;">${escapeHtml(data.details || '')}</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '注文回数' : 'Orders'}</span><br><strong>${data.total_orders || 0}</strong></div>
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '合計消費' : 'Total Spent'}</span><br><strong>$${(data.total_spent_usd || 0).toFixed(0)}</strong></div>
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? 'トラブル' : 'Troubles'}</span><br><strong style="color:${data.trouble_count > 0 ? '#F04438' : 'inherit'};">${data.trouble_count || 0}</strong></div>
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '平均返信' : 'Avg Reply'}</span><br><strong>${data.avg_response_time_min != null ? formatMinutes(data.avg_response_time_min) : '-'}</strong></div>
                </div>
            </div>`;
    } catch (e) {
        console.error('Failed to load buyer score:', e);
    }
}

// ── Buyer Full History ──────────────────────────────
async function loadBuyerFullHistory(buyer) {
    const section = document.getElementById('buyerHistorySection');
    if (!section) return;

    try {
        let data = cacheGet(_cache.histories, buyer);
        if (!data) {
            const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/history`);
            data = await resp.json();
            cacheSet(_cache.histories, buyer, data);
        }

        if (!data.orders?.length) {
            section.innerHTML = '';
            return;
        }

        const ja = getLang() === 'ja';
        const stats = data.stats || {};

        const ordersHtml = data.orders.slice(0, 8).map(o => {
            const profitColor = (o.net_profit_usd || 0) >= 0 ? 'var(--success-600)' : 'var(--error-500)';
            const troubleHtml = o.trouble_icon ? `<span title="${o.trouble_type}" style="font-size:12px;">${o.trouble_icon}</span>` : '';

            // Tracking link
            let trackHtml = '';
            if (o.tracking_number) {
                trackHtml = o.tracking_url
                    ? `<a href="${o.tracking_url}" target="_blank" rel="noopener" style="font-size:10px;color:var(--brand-500);text-decoration:none;display:inline-flex;align-items:center;gap:2px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 18.75a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 0 1-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 0 0-3.213-9.193 2.056 2.056 0 0 0-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 0 0-10.026 0 1.106 1.106 0 0 0-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12"/></svg>
                        ${o.carrier || ''} ${o.tracking_number.substring(0, 14)}${o.tracking_number.length > 14 ? '...' : ''}
                       </a>`
                    : `<span style="font-size:10px;color:var(--text-muted);">${o.tracking_number}</span>`;
            }

            const dateStr = o.sold_at ? new Date(o.sold_at).toLocaleDateString('ja-JP', {month:'short', day:'numeric'}) : '';

            // Use thumbnail from server (buyer_history API includes it from Listing DB)
            const histItem = itemsList.find(it => it.item_id === o.item_id);
            const histThumb = o.thumbnail || histItem?.thumbnail || '';
            const histThumbHtml = histThumb
                ? `<img src="${escapeHtml(histThumb)}" style="width:36px;height:36px;border-radius:6px;object-fit:cover;flex-shrink:0;background:var(--gray-100);" loading="lazy">`
                : `<div style="width:36px;height:36px;border-radius:6px;background:var(--gray-100);flex-shrink:0;"></div>`;

            return `
                <div style="padding:10px 0;border-bottom:1px solid var(--gray-100);">
                    <div style="display:flex;gap:8px;align-items:start;">
                        ${histThumbHtml}
                        <div style="flex:1;min-width:0;">
                            <div style="font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${troubleHtml} ${escapeHtml((o.title || '').substring(0, 30))}</div>
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;">
                                <span style="font-size:10px;color:var(--text-muted);">${dateStr}</span>
                                <span style="font-size:11px;font-weight:600;">$${(o.sale_price_usd || 0).toFixed(0)} <span style="color:${profitColor};font-size:10px;">($${(o.net_profit_usd || 0).toFixed(0)})</span></span>
                            </div>
                            ${trackHtml ? `<div style="margin-top:3px;">${trackHtml}</div>` : ''}
                        </div>
                    </div>
                </div>`;
        }).join('');

        section.innerHTML = `
            <h4 style="margin-top:16px;">${ja ? '購入履歴' : 'Purchase History'}</h4>
            <div class="buyer-info-card">
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;font-size:11px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid var(--gray-100);">
                    <div><span style="color:var(--text-muted);">${ja ? '注文' : 'Orders'}</span><br><strong>${stats.total_orders || 0}</strong></div>
                    <div><span style="color:var(--text-muted);">${ja ? '売上' : 'Revenue'}</span><br><strong>$${(stats.total_revenue_usd || 0).toFixed(0)}</strong></div>
                    <div><span style="color:var(--text-muted);">${ja ? '利益' : 'Profit'}</span><br><strong style="color:${(stats.total_profit_usd || 0) >= 0 ? 'var(--success-600)' : 'var(--error-500)'};">$${(stats.total_profit_usd || 0).toFixed(0)}</strong></div>
                </div>
                ${ordersHtml}
                ${data.orders.length > 8 ? `<div style="text-align:center;padding:8px;font-size:11px;color:var(--text-muted);">+${data.orders.length - 8} more</div>` : ''}
            </div>`;
    } catch (e) {
        console.error('Failed to load buyer history:', e);
    }
}

// ── Buyer Troubles ──────────────────────────────────
async function loadBuyerTroubles(buyer) {
    const section = document.getElementById('buyerTroubleSection');
    if (!section) return;

    try {
        const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/troubles`);
        const data = await resp.json();

        if (!data.total_troubles) {
            section.innerHTML = '';
            return;
        }

        const ja = getLang() === 'ja';
        let troublesHtml = '';

        // Returns
        for (const r of (data.returns || [])) {
            const urgentStyle = r.is_urgent ? 'border-left:3px solid var(--error-500);' : '';
            troublesHtml += `
                <div style="padding:8px 10px;border:1px solid var(--gray-100);border-radius:8px;margin-bottom:6px;font-size:11px;${urgentStyle}">
                    <div style="display:flex;justify-content:space-between;">
                        <span>${r.icon} ${ja ? r.status_ja : r.status}</span>
                        ${r.deadline ? `<span style="color:var(--error-500);font-weight:600;">${ja ? '期限' : 'Due'}: ${new Date(r.deadline).toLocaleDateString()}</span>` : ''}
                    </div>
                    <div style="color:var(--text-muted);margin-top:2px;">${escapeHtml(r.reason || '')}</div>
                </div>`;
        }

        // Cancellations
        for (const c of (data.cancellations || [])) {
            const urgentStyle = c.is_urgent ? 'border-left:3px solid var(--warning-500);' : '';
            troublesHtml += `
                <div style="padding:8px 10px;border:1px solid var(--gray-100);border-radius:8px;margin-bottom:6px;font-size:11px;${urgentStyle}">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span>${c.icon} ${ja ? c.status_ja : c.status}</span>
                        ${c.is_urgent ? `
                        <div style="display:flex;gap:4px;">
                            <button onclick="handleCancel('${c.order_id}', true)" style="padding:3px 8px;border:1px solid var(--success-500);border-radius:4px;background:var(--success-50);color:var(--success-700);font-size:10px;font-weight:600;">Accept</button>
                            <button onclick="handleCancel('${c.order_id}', false)" style="padding:3px 8px;border:1px solid var(--error-500);border-radius:4px;background:var(--error-50);color:var(--error-700);font-size:10px;font-weight:600;">Decline</button>
                        </div>` : ''}
                    </div>
                    <div style="color:var(--text-muted);margin-top:2px;">${escapeHtml(c.reason || '')}</div>
                </div>`;
        }

        section.innerHTML = `
            <h4 style="margin-top:16px;color:var(--error-600);">${ja ? 'トラブル' : 'Troubles'} (${data.total_troubles})</h4>
            <div class="buyer-info-card" style="border-color:var(--error-100);">
                ${troublesHtml}
            </div>`;
    } catch (e) {
        console.error('Failed to load troubles:', e);
    }
}

async function handleCancel(orderId, accept) {
    const action = accept ? 'accept' : 'decline';
    if (!confirm(`${accept ? 'Accept' : 'Decline'} this cancellation?`)) return;
    try {
        const resp = await fetch(`/api/chat/order/${orderId}/cancel/${action}`, { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            loadBuyerTroubles(currentBuyer);
        } else {
            alert(`Error: ${data.error || 'Unknown'}`);
        }
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

// ── Product Edit (in-chat) ──────────────────────────
async function loadProductEdit(itemId) {
    const section = document.getElementById('productEditSection');
    if (!section || !itemId) return;

    const ja = getLang() === 'ja';
    section.innerHTML = `
        <h4 style="margin-top:16px;">${ja ? '商品編集' : 'Quick Edit'}</h4>
        <div class="buyer-info-card">
            <div style="display:flex;gap:8px;margin-bottom:8px;">
                <div style="flex:1;">
                    <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px;">${ja ? '価格 (USD)' : 'Price (USD)'}</label>
                    <input type="number" id="editPrice" step="0.01" min="0" style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;font-family:inherit;">
                </div>
                <div style="flex:1;">
                    <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px;">${ja ? '数量' : 'Quantity'}</label>
                    <input type="number" id="editQuantity" step="1" min="0" style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;font-family:inherit;">
                </div>
            </div>
            <button onclick="saveProductEdit('${escapeHtml(itemId)}')" style="width:100%;padding:7px;background:var(--brand-500);color:white;border:none;border-radius:6px;font-size:12px;font-weight:600;transition:all 150ms;">
                ${ja ? '更新' : 'Update'}
            </button>
        </div>`;
}

async function saveProductEdit(itemId) {
    const price = document.getElementById('editPrice')?.value;
    const quantity = document.getElementById('editQuantity')?.value;

    const updates = {};
    if (price) updates.price_usd = parseFloat(price);
    if (quantity) updates.quantity = parseInt(quantity);

    if (!Object.keys(updates).length) return;

    try {
        const resp = await fetch(`/api/chat/listing/${itemId}/edit`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates),
        });
        const data = await resp.json();
        if (data.success) {
            alert(getLang() === 'ja' ? '更新完了' : 'Updated successfully');
        } else {
            alert(`Error: ${data.error || 'Unknown'}`);
        }
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

// ── Buyer Sales Info (legacy — replaced by full history) ─
async function loadBuyerSales(buyer, itemId) {
    const section = document.getElementById('buyerSalesSection');
    if (!section) return;

    try {
        const params = new URLSearchParams({item_id: itemId || ''});
        const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/sales?${params}`);
        const data = await resp.json();

        if (!data.orders?.length) {
            section.innerHTML = '';
            return;
        }

        const ordersHtml = data.orders.slice(0, 5).map(o => {
            const profitColor = o.net_profit_usd >= 0 ? '#12B76A' : '#F04438';
            const progressBadge = o.progress ? `<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:var(--gray-100);color:var(--text-secondary);">${escapeHtml(o.progress)}</span>` : '';
            // Tracking link
            let trackHtml = '';
            if (o.tracking_number) {
                const trackUrl = getTrackingUrl(o.tracking_number, o.shipping_method);
                trackHtml = trackUrl
                    ? `<a href="${trackUrl}" target="_blank" style="font-size:10px;color:var(--brand-500);text-decoration:none;">📦 ${o.tracking_number}</a>`
                    : `<span style="font-size:10px;color:var(--text-muted);">📦 ${o.tracking_number}</span>`;
            }
            return `
                <div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:11px;">
                    <div style="font-weight:500;margin-bottom:2px;">${escapeHtml((o.title || '').substring(0, 40))}</div>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <span>$${o.sale_price_usd?.toFixed(2) || '0'}</span>
                        <span style="color:${profitColor};font-weight:600;">→ $${o.net_profit_usd?.toFixed(2) || '0'} (${o.profit_margin_pct?.toFixed(0) || 0}%)</span>
                        ${progressBadge}
                    </div>
                    ${trackHtml}
                </div>`;
        }).join('');

        section.innerHTML = `
            <h4 style="margin-top:16px;">${getLang() === 'ja' ? '売上・利益' : 'Sales & Profit'}</h4>
            <div class="buyer-info-card">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;margin-bottom:8px;">
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '売上合計' : 'Revenue'}</span><br><strong>$${data.total_revenue_usd?.toFixed(2)}</strong></div>
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '利益合計' : 'Profit'}</span><br><strong style="color:${data.total_profit_usd >= 0 ? '#12B76A' : '#F04438'};">$${data.total_profit_usd?.toFixed(2)}</strong></div>
                </div>
                ${ordersHtml}
            </div>`;
    } catch (e) {
        console.error('Failed to load buyer sales:', e);
    }
}

// ── Response Time Stats ─────────────────────────────
async function loadResponseStats() {
    const section = document.getElementById('responseStatsSection');
    if (!section) return;

    try {
        const resp = await fetch('/api/chat/response-stats');
        const data = await resp.json();

        if (!data.total_tracked) {
            section.innerHTML = '';
            return;
        }

        const avgColor = (data.avg_min || 0) <= 60 ? '#12B76A' : (data.avg_min || 0) <= 1440 ? '#F79009' : '#F04438';

        section.innerHTML = `
            <h4 style="margin-top:16px;">${getLang() === 'ja' ? '返信パフォーマンス' : 'Response Performance'}</h4>
            <div class="buyer-info-card">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '平均返信' : 'Avg Reply'}</span><br><strong style="color:${avgColor};">${formatMinutes(data.avg_min)}</strong></div>
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '中央値' : 'Median'}</span><br><strong>${formatMinutes(data.median_min)}</strong></div>
                    <div><span style="color:var(--text-muted);">24h ${getLang() === 'ja' ? '以内率' : 'rate'}</span><br><strong>${data.within_24h_pct || 0}%</strong></div>
                    <div><span style="color:var(--text-muted);">${getLang() === 'ja' ? '計測数' : 'Tracked'}</span><br><strong>${data.total_tracked}</strong></div>
                </div>
            </div>`;
    } catch (e) {
        console.error('Failed to load response stats:', e);
    }
}

// ── Learned Draft (AI Style Learning) ───────────────
async function generateLearnedDraft() {
    if (!lastMessageId) return;

    const btn = event.target.closest('button');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<span class="loading-spinner"></span>';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/chat/draft/learned', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message_id: lastMessageId}),
        });
        const data = await resp.json();

        if (data.draft_reply) {
            document.getElementById('composeInput').value = data.draft_reply;
            document.getElementById('sendBtn').disabled = false;
            autoResize(document.getElementById('composeInput'));
        } else if (data.error) {
            alert(`Draft error: ${data.error}`);
        }
    } catch (e) {
        alert(`Draft error: ${e.message}`);
    } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
    }
}

// ── Tracking URL Helper ─────────────────────────────
function getTrackingUrl(trackingNumber, shippingMethod) {
    const method = (shippingMethod || '').toLowerCase();
    const num = trackingNumber || '';

    if (method.includes('dhl') || /^\d{10}$/.test(num))
        return `https://www.dhl.com/en/express/tracking.html?AWB=${num}`;
    if (method.includes('fedex') || /^\d{12,15}$/.test(num))
        return `https://www.fedex.com/fedextrack/?trknbr=${num}`;
    if (method.includes('speedpak') || method.includes('speed pak') || method.includes('orangeconnex'))
        return `https://www.orangeconnex.com/tracking?language=en&trackingnumber=${num}`;
    if (method.includes('ups') || /^1Z/.test(num))
        return `https://www.ups.com/track?tracknum=${num}`;
    if (method.includes('ems') || method.includes('japan post') || /^E[A-Z]\d{9}JP$/.test(num) || /^\d{13}$/.test(num))
        return `https://trackings.post.japanpost.jp/services/srv/search/?requestNo1=${num}&locale=en`;

    return null;
}

function formatMinutes(mins) {
    if (mins == null) return '-';
    if (mins < 60) return `${mins}m`;
    if (mins < 1440) return `${Math.round(mins / 60)}h`;
    return `${Math.round(mins / 1440)}d`;
}

// ── Scroll to Bottom ────────────────────────────────
function scrollToBottom() {
    const container = document.getElementById('threadMessages');
    if (container) container.scrollTop = container.scrollHeight;
}

function initScrollDetection() {
    const container = document.getElementById('threadMessages');
    const btn = document.getElementById('scrollBottomBtn');
    if (!container || !btn) return;
    container.addEventListener('scroll', () => {
        const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
        btn.style.display = isNearBottom ? 'none' : 'flex';
    });
}
document.addEventListener('DOMContentLoaded', initScrollDetection);

// ── Mobile ──────────────────────────────────────────
function backToList() {
    document.getElementById('convList')?.classList.remove('hidden');
    document.getElementById('threadView')?.classList.remove('active');
}

function showBuyerPanel() {
    // For mobile: could implement slide-in panel
    document.getElementById('buyerPanel')?.scrollIntoView({behavior: 'smooth'});
}

// ── Unread Badge ────────────────────────────────────
function updateUnreadBadge(count) {
    const badge = document.getElementById('navUnreadBadge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-flex' : 'none';
    }
}

// ── Utils ───────────────────────────────────────────
function getLang() {
    return localStorage.getItem('ebay-hub-lang') || 'en';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatRelativeDate(isoStr) {
    try {
        const date = new Date(isoStr);
        const now = new Date();
        const diff = now - date;
        const mins = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (mins < 1) return 'now';
        if (mins < 60) return `${mins}m`;
        if (hours < 24) return `${hours}h`;
        if (days < 7) return `${days}d`;
        return date.toLocaleDateString();
    } catch {
        return '';
    }
}

function formatDateTime(isoStr) {
    try {
        const date = new Date(isoStr);
        return date.toLocaleString('ja-JP', {
            month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    } catch {
        return '';
    }
}
