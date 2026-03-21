/**
 * eBay Buyer Messaging — Frontend Logic
 */

// ── State ───────────────────────────────────────────
let currentFilter = 'all';
let currentBuyer = '';
let currentItemId = '';
let conversations = [];
let currentThread = [];
let uploadedImageUrls = [];
let lastMessageId = null;

// ── Init ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadConversations();
    // Auto-sync every 5 minutes
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
        conversations = data.conversations || [];
        renderConversations();
        updateUnreadBadge(data.unread_total || 0);
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
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

    container.innerHTML = conversations.map(conv => {
        const isActive = conv.buyer === currentBuyer && conv.item_id === currentItemId;
        const isUnread = conv.unread_count > 0;
        const dateStr = conv.last_date ? formatRelativeDate(conv.last_date) : '';
        const preview = getLang() === 'ja' && conv.last_message_ja ? conv.last_message_ja : conv.last_message;

        return `
            <div class="conv-item ${isActive ? 'active' : ''} ${isUnread ? 'unread' : ''}"
                 onclick="openThread('${escapeHtml(conv.buyer)}', '${escapeHtml(conv.item_id)}')">
                <div class="conv-buyer">
                    <span>${escapeHtml(conv.buyer)}</span>
                    ${isUnread ? '<span class="unread-dot"></span>' : ''}
                </div>
                <div class="conv-subject">${escapeHtml(conv.subject || '')}</div>
                <div class="conv-preview">${escapeHtml(preview || '')}</div>
                <div class="conv-meta">
                    <span class="conv-item-id">${conv.item_id ? '#' + conv.item_id : ''}</span>
                    <span class="conv-date">${dateStr}</span>
                </div>
            </div>`;
    }).join('');
}

// ── Thread ──────────────────────────────────────────
async function openThread(buyer, itemId) {
    currentBuyer = buyer;
    currentItemId = itemId;

    // Highlight active conversation
    renderConversations();

    try {
        const params = new URLSearchParams({ item_id: itemId });
        const resp = await fetch(`/api/chat/conversations/${encodeURIComponent(buyer)}?${params}`);
        const data = await resp.json();
        currentThread = data.messages || [];
        renderThread();
        showCompose();

        // Mark inbound messages as read
        const unreadIds = currentThread
            .filter(m => m.direction === 'inbound' && !m.is_read)
            .map(m => m.id);
        if (unreadIds.length) {
            await fetch('/api/chat/mark-read', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message_ids: unreadIds}),
            });
            loadConversations();
        }

        // Update buyer info panel with score + sales
        updateBuyerPanel(buyer, itemId);
        loadBuyerScore(buyer);
        loadBuyerSales(buyer, itemId);

        // Store last inbound message ID for AI draft
        const lastInbound = [...currentThread].reverse().find(m => m.direction === 'inbound');
        lastMessageId = lastInbound ? lastInbound.id : null;

        // Load smart replies for last inbound
        if (lastMessageId) loadSmartReplies(lastMessageId);

        // Mobile: show thread
        document.getElementById('convList')?.classList.add('hidden');
        document.getElementById('threadView')?.classList.add('active');
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
        const dir = msg.direction;
        const senderLabel = dir === 'inbound' ? msg.sender : (getLang() === 'ja' ? '自分' : 'You');
        const timeStr = msg.received_at ? formatDateTime(msg.received_at) : '';

        // Sentiment + urgency badges
        let sentimentHtml = '';
        if (dir === 'inbound' && msg.sentiment) {
            const sentimentColors = {positive:'#12B76A', neutral:'#667085', negative:'#F79009', angry:'#F04438'};
            const urgencyIcons = {low:'', medium:'⚡', high:'🔥', critical:'🚨'};
            const color = sentimentColors[msg.sentiment] || '#667085';
            const icon = urgencyIcons[msg.urgency] || '';
            sentimentHtml = `<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;padding:2px 6px;border-radius:4px;background:${color}15;color:${color};font-weight:600;">
                ${icon} ${msg.sentiment}${msg.urgency && msg.urgency !== 'low' ? ' · ' + msg.urgency : ''}
            </span>`;
            if (msg.sentiment_note) {
                sentimentHtml += ` <span style="font-size:10px;color:var(--text-muted);">${escapeHtml(msg.sentiment_note)}</span>`;
            }
        }

        // Response time badge
        let responseTimeHtml = '';
        if (dir === 'inbound' && msg.response_time_min != null) {
            const mins = msg.response_time_min;
            const timeLabel = mins < 60 ? `${mins}m` : mins < 1440 ? `${Math.round(mins/60)}h` : `${Math.round(mins/1440)}d`;
            const timeColor = mins <= 60 ? '#12B76A' : mins <= 1440 ? '#F79009' : '#F04438';
            responseTimeHtml = `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${timeColor}15;color:${timeColor};">↩ ${timeLabel}</span>`;
        }

        let translationHtml = '';
        if (msg.body_translated && dir === 'inbound') {
            translationHtml = `<div class="msg-translation">🇯🇵 ${escapeHtml(msg.body_translated)}</div>`;
        }

        let attachmentHtml = '';
        if (msg.has_attachment && msg.attachment_urls?.length) {
            attachmentHtml = `<div class="msg-attachments">${
                msg.attachment_urls.map(url => `<img src="${escapeHtml(url)}" loading="lazy">`).join('')
            }</div>`;
        }

        return `
            <div class="msg-bubble ${dir}">
                <div class="msg-sender">
                    ${escapeHtml(senderLabel)}
                    ${sentimentHtml}
                </div>
                <div class="msg-content">${escapeHtml(msg.body).replace(/\n/g, '<br>')}</div>
                ${translationHtml}
                ${attachmentHtml}
                <div class="msg-time">${timeStr} ${responseTimeHtml}</div>
            </div>`;
    }).join('');

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
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

    if (e.key === 'Enter' && !e.shiftKey) {
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

// ── Translation ─────────────────────────────────────
async function translateCompose() {
    const input = document.getElementById('composeInput');
    const text = input.value.trim();
    if (!text) return;

    const preview = document.getElementById('translationPreview');
    preview.textContent = getLang() === 'ja' ? '翻訳中...' : 'Translating...';
    preview.classList.add('visible');

    try {
        const resp = await fetch('/api/chat/translate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text, direction: 'ja_to_en'}),
        });
        const data = await resp.json();

        if (data.translated) {
            preview.textContent = `EN: ${data.translated}`;
            // Replace input with English translation
            input.value = data.translated;
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
    container.innerHTML = `
        <div class="buyer-info-card">
            <div class="info-label">Buyer</div>
            <div class="info-value">${escapeHtml(buyer)}</div>
        </div>
        ${itemId ? `
        <div class="buyer-info-card">
            <div class="info-label">Item ID</div>
            <div class="info-value" style="font-family:'SF Mono','Cascadia Code',monospace;font-size:12px;">${escapeHtml(itemId)}</div>
        </div>` : ''}
        <div id="buyerScoreSection"></div>
        <div id="buyerHistorySection"></div>
        <div id="buyerTroubleSection"></div>
        <div id="productEditSection"></div>
        <div id="responseStatsSection"></div>`;

    loadBuyerFullHistory(buyer);
    loadBuyerTroubles(buyer);
    loadResponseStats();
    if (itemId) loadProductEdit(itemId);
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

// ── Buyer Score ─────────────────────────────────────
async function loadBuyerScore(buyer) {
    const section = document.getElementById('buyerScoreSection');
    if (!section) return;

    try {
        const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/score`);
        const data = await resp.json();

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
        const resp = await fetch(`/api/chat/buyer/${encodeURIComponent(buyer)}/history`);
        const data = await resp.json();

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

            return `
                <div style="padding:10px 0;border-bottom:1px solid var(--gray-100);">
                    <div style="display:flex;justify-content:space-between;align-items:start;">
                        <div style="flex:1;min-width:0;">
                            <div style="font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${troubleHtml} ${escapeHtml((o.title || '').substring(0, 35))}</div>
                            <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${dateStr} · ${o.marketplace || 'US'}</div>
                        </div>
                        <div style="text-align:right;flex-shrink:0;margin-left:8px;">
                            <div style="font-size:12px;font-weight:600;">$${(o.sale_price_usd || 0).toFixed(0)}</div>
                            <div style="font-size:10px;color:${profitColor};font-weight:600;">$${(o.net_profit_usd || 0).toFixed(0)} (${(o.profit_margin_pct || 0).toFixed(0)}%)</div>
                        </div>
                    </div>
                    ${trackHtml ? `<div style="margin-top:4px;">${trackHtml}</div>` : ''}
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
