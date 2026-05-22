/* listing-assistant.js — 出品アシスタント 5-step wizard */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  currentStep: 1,
  product: {},    // from fetch-url response
  demand: {},     // from demand response
  calc: {},       // from calculate response
  listing: {},    // from generate response
  priceUsd: 0,
};

// ── Constants ──────────────────────────────────────────────────────────────

const PLATFORM_COLORS = {
  'ヤフオク':     '#FF6B00',
  'メルカリ':     '#FF0000',
  'Yahooフリマ':  '#FF0033',
  'ハードオフ':   '#003087',
  '駿河屋':       '#00693E',
  'ラクマ':       '#FF4785',
  'PayPayフリマ': '#FF0033',
  'Amazon':       '#FF9900',
  'ジモティー':   '#00A0E9',
};

const PLATFORM_PATTERNS = [
  { name: 'ヤフオク',     re: /auctions\.yahoo\.co\.jp|page\.auctions\.yahoo/i },
  { name: 'メルカリ',     re: /jp\.mercari\.com/i },
  { name: 'Yahooフリマ',  re: /paypayfleamarket\.yahoo\.co\.jp/i },
  { name: 'ハードオフ',   re: /hardoff\.co\.jp/i },
  { name: '駿河屋',       re: /suruga-ya\.jp/i },
  { name: 'ラクマ',       re: /fril\.jp|rakuma\./i },
  { name: 'PayPayフリマ', re: /paypayfleamarket/i },
  { name: 'Amazon',       re: /amazon\.co\.jp/i },
];

const CONDITION_LABELS = {
  USED_EXCELLENT:          'Used – Excellent',
  USED_VERY_GOOD:          'Used – Very Good',
  USED_GOOD:               'Used – Good',
  FOR_PARTS_OR_NOT_WORKING:'For Parts or Not Working',
  NEW:                     'New',
};

// ── Debounce ───────────────────────────────────────────────────────────────

let _calcTimer = null;
function debouncedCalc() {
  clearTimeout(_calcTimer);
  _calcTimer = setTimeout(calculate, 500);
}

// ── Step navigation ────────────────────────────────────────────────────────

function goToStep(n) {
  // Validate forward navigation
  if (n > 1 && !state.product.title && n > 2) {
    showNotice('step1Notice', 'error', '先に商品URLを取得してください。');
    return;
  }

  state.currentStep = n;
  updateStepBar(n);

  // Show/hide panels
  for (let i = 1; i <= 5; i++) {
    const panel = document.getElementById('panelStep' + i);
    if (panel) panel.style.display = (i === n) ? '' : 'none';
  }

  // On entering step 3: pre-fill cost fields & auto-calculate
  if (n === 3) {
    prefillCostFields();
    calculate();
  }

  // On entering step 5: fill summary
  if (n === 5) {
    fillSummary();
  }

  // Smooth scroll to top of content
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateStepBar(active) {
  const labels = ['URL入力', '商品確認', '価格設定', '出品情報', '確認・出品'];

  for (let i = 1; i <= 5; i++) {
    const circle = document.getElementById('sc' + i);
    const label  = document.getElementById('sl' + i);
    if (!circle || !label) continue;

    circle.className = 'la-step-circle';
    label.className  = 'la-step-label';

    if (i < active) {
      circle.classList.add('done');
      circle.textContent = '✓';
      label.classList.add('done');
    } else if (i === active) {
      circle.classList.add('active');
      circle.textContent = String(i);
      label.classList.add('active');
    } else {
      circle.textContent = String(i);
    }

    label.textContent = labels[i - 1];
  }

  // Connectors
  for (let i = 1; i <= 4; i++) {
    const conn = document.getElementById('conn' + i);
    if (!conn) continue;
    conn.className = 'la-step-connector' + (i < active ? ' done' : '');
  }
}

// ── Step 1: Platform detection ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
  const urlInput = document.getElementById('productUrl');
  if (urlInput) {
    urlInput.addEventListener('input', onUrlInput);
    urlInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') fetchProductUrl();
    });
  }
  // Init step bar
  updateStepBar(1);
});

// ── Keyword suggestion ─────────────────────────────────────────────────────

async function suggestKeywords(product) {
  const input = document.getElementById('ebaySearchQuery');
  if (!input) return;

  input.placeholder = 'キーワードを生成中...';
  input.disabled    = true;

  try {
    const res = await apiPost('/api/listing-assistant/suggest-keywords', {
      title:       product.title       || '',
      description: product.description || '',
      platform:    product.platform    || '',
    });

    if (res.ok) {
      const data = await res.json();
      if (data.keywords) {
        input.value       = data.keywords;
        input.placeholder = '英語キーワードを入力（例: Sony PS5 console）';
      } else {
        input.placeholder = '英語キーワードを入力（例: Sony PS5 console）';
      }
    } else {
      input.placeholder = '英語キーワードを入力（例: Sony PS5 console）';
    }
  } catch (e) {
    input.placeholder = '英語キーワードを入力（例: Sony PS5 console）';
  } finally {
    input.disabled = false;
    input.focus();
  }
}

function onUrlInput() {
  const url = document.getElementById('productUrl').value.trim();
  const detectedDiv = document.getElementById('platformDetect');
  const badge = document.getElementById('platformBadge');

  if (!url) {
    detectedDiv.style.display = 'none';
    return;
  }

  const platform = detectPlatform(url);
  if (platform) {
    badge.textContent = platform;
    badge.style.background = PLATFORM_COLORS[platform] || '#64748B';
    detectedDiv.style.display = 'flex';
    detectedDiv.style.alignItems = 'center';
  } else {
    detectedDiv.style.display = 'none';
  }
}

function detectPlatform(url) {
  for (const p of PLATFORM_PATTERNS) {
    if (p.re.test(url)) return p.name;
  }
  return null;
}

// ── Step 1 → 2: Fetch product URL ─────────────────────────────────────────

async function fetchProductUrl() {
  const url = document.getElementById('productUrl').value.trim();
  if (!url) {
    showNotice('step1Notice', 'error', 'URLを入力してください。');
    return;
  }

  setFetchLoading(true);
  clearNotice('step1Notice');

  try {
    const res = await apiPost('/api/listing-assistant/fetch-url', { url });

    if (!res.ok) {
      const err = await safeJson(res);
      showNotice('step1Notice', 'error', '取得失敗: ' + (err.detail || res.statusText));
      return;
    }

    const data = await res.json();
    state.product = data;

    // Fill step 2 product card
    fillProductCard(data);

    // Step 2 へ移動
    goToStep(2);

    // 英語キーワードを自動生成（バックグラウンドで実行、完了したら入力欄に反映）
    suggestKeywords(data);

  } catch (e) {
    showNotice('step1Notice', 'error', 'ネットワークエラー: ' + e.message);
  } finally {
    setFetchLoading(false);
  }
}

function setFetchLoading(loading) {
  const btn     = document.getElementById('fetchBtn');
  const btnText = document.getElementById('fetchBtnText');
  const spinner = document.getElementById('fetchSpinner');
  btn.disabled          = loading;
  btnText.style.display = loading ? 'none' : '';
  spinner.style.display = loading ? '' : 'none';
}

// ── Step 2: Fill product card ──────────────────────────────────────────────

function fillProductCard(data) {
  // Title
  const titleInput = document.getElementById('productTitle');
  if (titleInput) titleInput.value = data.title || '';

  // Price
  const priceEl = document.getElementById('productPrice');
  if (priceEl) {
    priceEl.textContent = data.price_jpy != null
      ? '¥' + Number(data.price_jpy).toLocaleString()
      : '—';
  }

  // Condition
  const condEl = document.getElementById('productCondition');
  if (condEl) condEl.textContent = data.condition || '—';

  // Seller
  const sellerEl = document.getElementById('productSeller');
  if (sellerEl) sellerEl.textContent = data.seller_id || '—';

  // Platform badge
  const badge2 = document.getElementById('platformBadge2');
  const platform = data.platform || detectPlatform(document.getElementById('productUrl').value);
  if (badge2 && platform) {
    badge2.textContent = platform;
    badge2.style.background = PLATFORM_COLORS[platform] || '#64748B';
    badge2.style.display = 'inline-flex';
  }

  // Image
  const imgWrap = document.getElementById('productImgWrap');
  if (imgWrap) {
    if (data.image_url) {
      imgWrap.innerHTML = `<img class="la-product-img" src="${escHtml(data.image_url)}" alt="商品画像" />`;
    } else {
      imgWrap.innerHTML = '<div class="la-product-img-placeholder">画像なし</div>';
    }
  }

  // Source link
  const srcLink = document.getElementById('productSourceLink');
  if (srcLink) {
    const url = document.getElementById('productUrl').value.trim();
    if (url) {
      srcLink.href = url;
      srcLink.style.display = 'inline';
    }
  }
}

// ── Step 2: eBay Demand check ──────────────────────────────────────────────

async function checkDemand() {
  const ebayQuery = (document.getElementById('ebaySearchQuery')?.value || '').trim();
  if (!ebayQuery) {
    document.getElementById('ebaySearchQuery')?.focus();
    return;
  }

  setDemandLoading(true);

  try {
    const res = await apiPost('/api/listing-assistant/demand', {
      ebay_query: ebayQuery,
      price_jpy: state.product.price_jpy || 0,
    });

    if (!res.ok) {
      const err = await safeJson(res);
      setDemandLoading(false);
      showDemandNone();
      console.warn('Demand API error:', err.detail || res.statusText);
      return;
    }

    const data = await res.json();
    state.demand = data;
    showDemandContent(data);

  } catch (e) {
    console.error('Demand check error:', e);
    setDemandLoading(false);
    showDemandNone();
  }
}

function setDemandLoading(loading) {
  const loadEl    = document.getElementById('demandLoading');
  const contentEl = document.getElementById('demandContent');
  const noneEl    = document.getElementById('demandNone');
  const btn       = document.getElementById('recheckDemandBtn');
  if (loadEl)    loadEl.style.display    = loading ? '' : 'none';
  if (contentEl) contentEl.style.display = loading ? 'none' : '';
  if (noneEl)    noneEl.style.display    = 'none';
  if (btn)       btn.disabled            = loading;
}

function showDemandNone() {
  const loadEl    = document.getElementById('demandLoading');
  const contentEl = document.getElementById('demandContent');
  const noneEl    = document.getElementById('demandNone');
  if (loadEl)    loadEl.style.display    = 'none';
  if (contentEl) contentEl.style.display = 'none';
  if (noneEl)    noneEl.style.display    = '';
}

function showDemandContent(data) {
  setDemandLoading(false);

  const score = data.demand_score != null ? data.demand_score : null;

  // Score badge
  const scoreEl = document.getElementById('demandScore');
  if (scoreEl) {
    if (score === null) {
      scoreEl.textContent = '—';
      scoreEl.className   = 'la-demand-score';
    } else {
      scoreEl.textContent = String(score);
      const cls = score >= 70 ? 'green' : score >= 40 ? 'orange' : 'red';
      scoreEl.className = 'la-demand-score ' + cls;
    }
  }

  // Title label
  const titleEl = document.getElementById('demandTitle');
  if (titleEl) {
    if (score === null)     titleEl.textContent = '需要データなし';
    else if (score >= 70)  titleEl.textContent = '需要あり — 売れやすい';
    else if (score >= 40)  titleEl.textContent = '需要あり — 普通';
    else                   titleEl.textContent = '需要低め — 慎重に判断';
  }

  // Recommendation
  const recEl = document.getElementById('demandRec');
  if (recEl) recEl.textContent = data.recommendation || '';

  // データソースバッジ
  const badge = document.getElementById('demandDataSourceBadge');
  if (badge) {
    if (data.data_source === 'sold') {
      badge.textContent = '落札実績データ';
      badge.style.background = 'var(--green-light, #d1fae5)';
      badge.style.color = 'var(--green, #059669)';
    } else {
      badge.textContent = '出品中データ ※落札実績なし';
      badge.style.background = 'var(--gray-100, #f1f5f9)';
      badge.style.color = 'var(--text-muted, #94a3b8)';
    }
    badge.style.display = '';
  }

  // Price stats — サーバーは price_analysis ネストで返す
  const pa = data.price_analysis || {};
  setTextContent('demandMedian', pa.median_usd != null ? '$' + Number(pa.median_usd).toFixed(2) : '—');
  setTextContent('demandMin',    pa.min_usd    != null ? '$' + Number(pa.min_usd).toFixed(2)    : '—');
  setTextContent('demandMax',    pa.max_usd    != null ? '$' + Number(pa.max_usd).toFixed(2)    : '—');

  // Similar items — サーバーは promising_items で返す
  const list = document.getElementById('similarList');
  if (list) {
    const items = Array.isArray(data.promising_items) ? data.promising_items.slice(0, 3) : [];
    if (items.length === 0) {
      list.innerHTML = '<li style="font-size:12px;color:var(--text-muted);padding:8px 0">類似商品が見つかりませんでした</li>';
      const lbl = document.getElementById('similarLabel');
      if (lbl) lbl.textContent = '類似商品';
    } else {
      const lbl = document.getElementById('similarLabel');
      if (lbl) lbl.textContent = '類似商品 TOP ' + items.length;
      list.innerHTML = items.map(item => `
        <li class="la-similar-item">
          <span class="la-similar-title" title="${escHtml(item.title || '')}">${escHtml(item.title || '—')}</span>
          <span class="la-similar-price">${item.price_usd != null ? '$' + Number(item.price_usd).toFixed(2) : '—'}</span>
        </li>
      `).join('');
    }
  }

  // items_found があればコンテンツを表示し続ける（promising_items空でも価格データは有効）
  if (!data.items_found && (!data.promising_items || data.promising_items.length === 0)) {
    showDemandNone();
  }
}

// ── Step 3: Cost pre-fill ──────────────────────────────────────────────────

function prefillCostFields() {
  const priceJpy = state.product.price_jpy;
  if (priceJpy != null) {
    const priceInput = document.getElementById('costPrice');
    if (priceInput) priceInput.value = priceJpy;

    const taxInput = document.getElementById('costTax');
    if (taxInput && !taxInput._touched) {
      taxInput.value = Math.round(priceJpy * 0.10);
    }
  }
}

function onMarginSlide(val) {
  const label = document.getElementById('targetMarginLabel');
  if (label) label.textContent = val + '%';
  debouncedCalc();
}

// ── Step 3: Price calculation ──────────────────────────────────────────────

async function calculate() {
  const priceJpy   = Number(document.getElementById('costPrice')?.value) || 0;
  const taxJpy     = Number(document.getElementById('costTax')?.value) || 0;
  const domShipJpy = Number(document.getElementById('costDomShipping')?.value) || 0;
  const intlShipUsd= Number(document.getElementById('costIntlShipping')?.value) || 20;
  const targetPct  = Number(document.getElementById('targetMarginSlider')?.value) || 25;

  const updEl = document.getElementById('calcUpdating');
  if (updEl) updEl.style.display = '';

  try {
    const res = await apiPost('/api/listing-assistant/calculate', {
      price_jpy:           priceJpy,
      tax_jpy:             taxJpy,
      domestic_shipping_jpy: domShipJpy,
      international_shipping_usd: intlShipUsd,
      target_margin_pct:   targetPct,
    });

    if (!res.ok) {
      const err = await safeJson(res);
      showNotice('calcNotice', 'error', '計算エラー: ' + (err.detail || res.statusText));
      return;
    }

    const data = await res.json();
    state.calc = data;
    state.priceUsd = data.recommended_price_usd || 0;
    fillCalcResults(data);

  } catch (e) {
    // Fallback: client-side calculation if API unavailable
    const fallback = clientSideCalc(priceJpy, taxJpy, domShipJpy, intlShipUsd, targetPct);
    state.calc = fallback;
    state.priceUsd = fallback.recommended_price_usd;
    fillCalcResults(fallback);
  } finally {
    if (updEl) updEl.style.display = 'none';
  }
}

function clientSideCalc(priceJpy, taxJpy, domShipJpy, intlShipUsd, targetPct) {
  // Use a reasonable fallback FX rate
  const fxRate = window._fxRate || 155;

  const costJpy = priceJpy + taxJpy + domShipJpy;
  const costUsd = costJpy / fxRate;

  // Solve for sell price P:
  // P - (costUsd + intlShipUsd + 0.129*P + 0.02*P) = targetPct/100 * P
  // P * (1 - 0.129 - 0.02 - targetPct/100) = costUsd + intlShipUsd
  const margin = targetPct / 100;
  const denom  = 1 - 0.129 - 0.02 - margin;
  const priceUsd = denom > 0.01 ? (costUsd + intlShipUsd) / denom : 0;

  const ebayFeeUsd    = priceUsd * 0.129;
  const payoneerFeeUsd= priceUsd * 0.02;
  const profitUsd     = priceUsd - costUsd - intlShipUsd - ebayFeeUsd - payoneerFeeUsd;
  const profitJpy     = Math.round(profitUsd * fxRate);
  const actualMargin  = priceUsd > 0 ? (profitUsd / priceUsd * 100) : 0;

  return {
    cost_jpy:                  priceJpy,
    tax_jpy:                   taxJpy,
    domestic_shipping_jpy:     domShipJpy,
    total_cost_jpy:            costJpy,
    domestic_cost_usd:         costUsd,
    total_cost_usd:            costUsd + intlShipUsd,
    international_shipping_usd: intlShipUsd,
    ebay_fee_usd:              ebayFeeUsd,
    payoneer_fee_usd:          payoneerFeeUsd,
    recommended_price_usd:     Math.ceil(priceUsd * 100) / 100,
    profit_usd:                profitUsd,
    profit_jpy:                profitJpy,
    actual_margin_pct:         actualMargin,
  };
}

function fillCalcResults(data) {
  setTextContent('cr-cost',          fmtJpy(data.cost_jpy));
  setTextContent('cr-tax',           fmtJpy(data.tax_jpy));
  setTextContent('cr-dom-ship',      fmtJpy(data.domestic_shipping_jpy));
  setTextContent('cr-subtotal-jpy',  fmtJpy(data.total_cost_jpy));
  setTextContent('cr-subtotal-usd',  fmtUsd(data.domestic_cost_usd));  // 国内コストのみ（intl送料除く）
  setTextContent('cr-intl-ship',     fmtUsd(data.international_shipping_usd));
  setTextContent('cr-ebay-fee',      fmtUsd(data.ebay_fee_usd));
  setTextContent('cr-payoneer',      fmtUsd(data.payoneer_fee_usd));
  setTextContent('cr-recommend',     fmtUsd(data.recommended_price_usd));

  const priceBig = document.getElementById('calcPriceBig');
  if (priceBig) priceBig.textContent = fmtUsd(data.recommended_price_usd);

  const profitEl = document.getElementById('calcProfit');
  if (profitEl) {
    profitEl.textContent = '純利益 ' + fmtUsd(data.profit_usd) + ' (' + fmtJpy(data.profit_jpy) + ')';
    profitEl.style.color = (data.profit_usd >= 0) ? 'var(--green)' : 'var(--red)';
  }

  const marginPct = data.actual_margin_pct || 0;
  setTextContent('calcMarginPct', marginPct.toFixed(1) + '%');

  const bar = document.getElementById('calcMarginBar');
  if (bar) {
    const pct = Math.min(100, Math.max(0, marginPct));
    bar.style.width = pct + '%';
    bar.style.background = pct >= 20 ? 'var(--green)' : pct >= 10 ? 'var(--orange)' : 'var(--red)';
  }

  // Warning notice
  clearNotice('calcNotice');
  if (marginPct < 10) {
    showNotice('calcNotice', 'warning', '⚠️ 利益率が低すぎます。仕入価格や送料の見直しを推奨します。');
  } else if (marginPct >= 25) {
    showNotice('calcNotice', 'success', '✓ 良好な利益率です。');
  }
}

// ── Step 4: AI listing generation ─────────────────────────────────────────

async function generateListing() {
  const btn      = document.getElementById('generateBtn');
  const btnText  = document.getElementById('generateBtnText');
  const spinner  = document.getElementById('generateSpinner');

  btn.disabled          = true;
  btnText.style.display = 'none';
  spinner.style.display = '';
  clearNotice('generateNotice');

  try {
    const title = document.getElementById('productTitle')?.value?.trim() || '';
    const cond  = document.getElementById('listingCondition')?.value || 'USED_EXCELLENT';

    const res = await apiPost('/api/listing-assistant/generate', {
      product_title:   title,
      price_usd:       state.priceUsd,
      condition:       cond,
      platform:        state.product.platform || '',
      original_price_jpy: state.product.price_jpy || 0,
      demand:          state.demand,
    });

    if (!res.ok) {
      const err = await safeJson(res);
      showNotice('generateNotice', 'error', '生成失敗: ' + (err.detail || res.statusText));
      return;
    }

    const data = await res.json();
    state.listing = data;
    fillListingFields(data);
    showNotice('generateNotice', 'success', '✓ AI生成が完了しました。内容を確認・編集してください。');

  } catch (e) {
    showNotice('generateNotice', 'error', 'エラー: ' + e.message);
  } finally {
    btn.disabled          = false;
    btnText.style.display = '';
    spinner.style.display = 'none';
  }
}

function fillListingFields(data) {
  const titleInput = document.getElementById('listingTitle');
  if (titleInput && data.title) {
    titleInput.value = data.title;
    updateCharCounter('listingTitle', 'titleCounter', 80);
  }

  const catInput = document.getElementById('listingCategoryId');
  if (catInput && data.category_id) catInput.value = data.category_id;

  const condSelect = document.getElementById('listingCondition');
  if (condSelect && data.condition) condSelect.value = data.condition;

  const descInput = document.getElementById('listingDescription');
  if (descInput && data.description) descInput.value = data.description;

  // Item Specifics
  const specifics = data.item_specifics;
  if (specifics && typeof specifics === 'object') {
    clearSpecifics();
    Object.entries(specifics).forEach(([k, v]) => addSpecificsRow(k, v));
  }
}

// ── Item Specifics table ───────────────────────────────────────────────────

function clearSpecifics() {
  const tbody = document.getElementById('specificsTableBody');
  if (tbody) tbody.innerHTML = '';
}

function addSpecificsRow(key = '', val = '') {
  const tbody = document.getElementById('specificsTableBody');
  if (!tbody) return;

  const id  = 'spec-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
  const tr  = document.createElement('tr');
  tr.id     = id;
  tr.innerHTML = `
    <td>
      <input type="text" class="la-spec-input" placeholder="例: Brand"
             value="${escHtml(key)}" data-role="spec-key" />
    </td>
    <td>
      <input type="text" class="la-spec-input" placeholder="例: Sony"
             value="${escHtml(val)}" data-role="spec-val" />
    </td>
    <td>
      <button class="la-spec-remove" onclick="removeSpecificsRow('${id}')" title="削除">×</button>
    </td>
  `;
  tbody.appendChild(tr);
}

function removeSpecificsRow(id) {
  const row = document.getElementById(id);
  if (row) row.remove();
}

function collectSpecifics() {
  const rows = document.querySelectorAll('#specificsTableBody tr');
  const result = {};
  rows.forEach(row => {
    const key = row.querySelector('[data-role="spec-key"]')?.value?.trim();
    const val = row.querySelector('[data-role="spec-val"]')?.value?.trim();
    if (key) result[key] = val || '';
  });
  return result;
}

// ── Step 5: Summary fill ───────────────────────────────────────────────────

function fillSummary() {
  const title = document.getElementById('listingTitle')?.value ||
                document.getElementById('productTitle')?.value || '—';

  setTextContent('sum-title',     title);
  setTextContent('sum-price',     fmtUsd(state.priceUsd || state.calc.recommended_price_usd));
  setTextContent('sum-cost',      fmtJpy(state.calc.total_cost_jpy));
  setTextContent('sum-profit',    fmtUsd(state.calc.profit_usd));
  setTextContent('sum-margin',    (state.calc.actual_margin_pct || 0).toFixed(1) + '%');

  const cond = document.getElementById('listingCondition')?.value || 'USED_EXCELLENT';
  setTextContent('sum-condition', CONDITION_LABELS[cond] || cond);
}

// ── Step 5: Submit ─────────────────────────────────────────────────────────

async function submitListing() {
  const btn      = document.getElementById('submitBtn');
  const btnText  = document.getElementById('submitBtnText');
  const spinner  = document.getElementById('submitSpinner');
  const backBtn  = document.getElementById('backBtn4');

  btn.disabled          = true;
  btnText.style.display = 'none';
  spinner.style.display = '';
  if (backBtn) backBtn.disabled = true;
  clearNotice('submitNotice');

  const payload = buildSubmitPayload();

  let allSuccess = true;
  let stockNumber = '';

  // 1. 仕入れ台帳登録
  setProgressState('ledger', 'loading', '登録中...');
  try {
    const r1 = await apiPost('/api/listing-assistant/submit/ledger', payload);
    if (r1.ok) {
      const d1 = await r1.json();
      stockNumber = d1.stock_number || '';
      setProgressState('ledger', 'success', '登録完了', '/sourcing');
    } else {
      const e1 = await safeJson(r1);
      setProgressState('ledger', 'error', '登録失敗: ' + (e1.detail || r1.statusText));
      allSuccess = false;
    }
  } catch (e) {
    setProgressState('ledger', 'error', 'エラー: ' + e.message);
    allSuccess = false;
  }

  // 2. eShip登録（台帳のstock_numberを引き継ぐ）
  setProgressState('eship', 'loading', '登録中...');
  try {
    const r2 = await apiPost('/api/listing-assistant/submit/eship', { ...payload, stock_number: stockNumber });
    if (r2.ok) {
      setProgressState('eship', 'success', '登録完了', 'https://eship-tool.com/orders');
    } else {
      const e2 = await safeJson(r2);
      setProgressState('eship', 'error', '登録失敗: ' + (e2.detail || r2.statusText));
      allSuccess = false;
    }
  } catch (e) {
    setProgressState('eship', 'error', 'エラー: ' + e.message);
    allSuccess = false;
  }

  // 3. eBayドラフト作成
  setProgressState('ebay', 'loading', 'ドラフト作成中...');
  try {
    const r3 = await apiPost('/api/listing-assistant/submit/ebay-draft', payload);
    if (r3.ok) {
      const d3 = await r3.json();
      const ebayUrl = d3.ebay_listing_url || 'https://www.ebay.com/sh/lst/active';
      setProgressState('ebay', 'success', 'ドラフト作成完了', ebayUrl);
    } else {
      const e3 = await safeJson(r3);
      setProgressState('ebay', 'error', '作成失敗: ' + (e3.detail || r3.statusText));
      allSuccess = false;
    }
  } catch (e) {
    setProgressState('ebay', 'error', 'エラー: ' + e.message);
    allSuccess = false;
  }

  btn.disabled          = false;
  btnText.style.display = '';
  spinner.style.display = 'none';
  if (backBtn) backBtn.disabled = false;

  if (allSuccess) {
    btn.disabled = true;
    document.getElementById('successSection').style.display = '';
    showNotice('submitNotice', 'success', '✓ すべての処理が完了しました。');
  } else {
    showNotice('submitNotice', 'warning', '⚠️ 一部の処理が失敗しました。上の詳細を確認してください。');
  }
}

function buildSubmitPayload() {
  return {
    // Product info
    product:        state.product,
    source_url:     document.getElementById('productUrl')?.value || '',

    // Listing info
    ebay_title:     document.getElementById('listingTitle')?.value || '',
    description:    document.getElementById('listingDescription')?.value || '',
    category_id:    document.getElementById('listingCategoryId')?.value || '',
    condition:      document.getElementById('listingCondition')?.value || 'USED_EXCELLENT',
    item_specifics: collectSpecifics(),

    // Pricing
    price_usd:      state.priceUsd,
    calc:           state.calc,

    // Demand
    demand:         state.demand,
  };
}

function setProgressState(key, state_, subText, linkUrl) {
  const item    = document.getElementById('prog-' + key);
  const iconEl  = document.getElementById('prog-' + key + '-icon');
  const subEl   = document.getElementById('prog-' + key + '-sub');
  const linkEl  = document.getElementById('prog-' + key + '-link');

  if (!item) return;

  // Reset classes
  item.classList.remove('success', 'error');

  if (state_ === 'loading') {
    iconEl.innerHTML = '<span class="la-spinner la-spinner-dark" style="width:18px;height:18px;border-width:2px"></span>';
    if (subEl) subEl.textContent = subText || '';
    if (linkEl) linkEl.style.display = 'none';
  } else if (state_ === 'success') {
    item.classList.add('success');
    iconEl.textContent = '✅';
    if (subEl) subEl.textContent = subText || '完了';
    if (linkEl && linkUrl) {
      linkEl.href = linkUrl;
      linkEl.style.display = '';
    }
  } else if (state_ === 'error') {
    item.classList.add('error');
    iconEl.textContent = '❌';
    if (subEl) subEl.textContent = subText || 'エラー';
    if (linkEl) linkEl.style.display = 'none';
  }
}

// ── Reset ──────────────────────────────────────────────────────────────────

function resetWizard() {
  state.currentStep = 1;
  state.product  = {};
  state.demand   = {};
  state.calc     = {};
  state.listing  = {};
  state.priceUsd = 0;

  // Clear inputs
  const urlInput = document.getElementById('productUrl');
  if (urlInput) urlInput.value = '';
  const detectedDiv = document.getElementById('platformDetect');
  if (detectedDiv) detectedDiv.style.display = 'none';

  // Reset progress
  ['ledger', 'eship', 'ebay'].forEach(key => {
    const item = document.getElementById('prog-' + key);
    if (item) item.classList.remove('success', 'error');
    const icon = document.getElementById('prog-' + key + '-icon');
    if (icon) icon.textContent = '⏳';
    const sub = document.getElementById('prog-' + key + '-sub');
    const defaults = {
      ledger: '出品後に仕入れ台帳へ記録されます',
      eship:  'eShipへ発送情報を事前登録します',
      ebay:   'eBay Seller Hubにドラフト出品を作成します',
    };
    if (sub) sub.textContent = defaults[key] || '';
    const link = document.getElementById('prog-' + key + '-link');
    if (link) link.style.display = 'none';
  });

  document.getElementById('successSection').style.display = 'none';

  goToStep(1);
}

// ── Char counter ───────────────────────────────────────────────────────────

function updateCharCounter(inputId, counterId, max) {
  const input   = document.getElementById(inputId);
  const counter = document.getElementById(counterId);
  if (!input || !counter) return;

  const len = input.value.length;
  counter.textContent = len + ' / ' + max;
  counter.className   = 'la-char-counter';

  if (len >= max)       counter.classList.add('over');
  else if (len >= max * 0.85) counter.classList.add('warn');
}

// ── Notice helpers ─────────────────────────────────────────────────────────

function showNotice(containerId, type, message) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="la-notice ${escHtml(type)}">${escHtml(message)}</div>`;
}

function clearNotice(containerId) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = '';
}

// ── DOM helpers ────────────────────────────────────────────────────────────

function setTextContent(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Format helpers ─────────────────────────────────────────────────────────

function fmtJpy(val) {
  if (val == null || isNaN(val)) return '¥—';
  return '¥' + Math.round(val).toLocaleString('ja-JP');
}

function fmtUsd(val) {
  if (val == null || isNaN(val)) return '$—';
  return '$' + Number(val).toFixed(2);
}

// ── Fetch helpers ──────────────────────────────────────────────────────────

function apiPost(path, body) {
  return fetch(path, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
}

async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    return { detail: res.statusText };
  }
}

// ── FX rate integration (reads from global set by overview.js if present) ──

window.addEventListener('load', function () {
  // Try to read FX rate set by the main app script
  if (typeof window._fxRate !== 'undefined') return;
  // Fallback: attempt to parse from the fx chip in header if present
  const fxEl = document.getElementById('fxRate');
  if (fxEl) {
    const parsed = parseFloat(fxEl.textContent);
    if (!isNaN(parsed)) window._fxRate = parsed;
  }
});

// ── 再仕入れ候補タブ ────────────────────────────────────

function switchMode(mode) {
  document.querySelectorAll('.la-mode-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.la-mode-tab[data-mode="${mode}"]`).classList.add('active');
  const wizardPanel = document.getElementById('la-wizard-panel');
  const reorderPanel = document.getElementById('la-reorder-panel');
  if (mode === 'wizard') {
    wizardPanel.style.display = '';
    reorderPanel.style.display = 'none';
  } else {
    wizardPanel.style.display = 'none';
    reorderPanel.style.display = '';
    loadSoldItems();
  }
}

let _soldItemsLoaded = false;
const _reorderItemsCache = new Map();
const _researchResults = new Map();

function _estimateMarginFast(item) {
  const rate = window._fxRate || 155;
  const revenueUsd = parseFloat(item.ebay_price_usd) || 0;
  if (!revenueUsd) return -999;
  const sourceCostUsd = (item.purchase_price_jpy || 0) / rate;
  const fees = revenueUsd * (0.129 + (1 - 0.129) * 0.02);
  const net = revenueUsd - fees - 20 - sourceCostUsd;
  return net / revenueUsd * 100;
}

async function loadSoldItems(force = false) {
  if (_soldItemsLoaded && !force) return;
  const container = document.getElementById('reorderList');
  const url = force ? '/api/listing-assistant/sold-no-stock?refresh=1' : '/api/listing-assistant/sold-no-stock';
  container.innerHTML = '<div class="la-reorder-empty">eShipから取得中...<br><small style="color:var(--text-secondary)">初回は15〜30秒かかります</small></div>';
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    const items = Array.isArray(data) ? data : [];
    _soldItemsLoaded = true;
    if (!items.length) {
      container.innerHTML = '<div class="la-reorder-empty">再仕入れ候補がありません。</div>';
      return;
    }
    const byMargin = (a, b) => _estimateMarginFast(b) - _estimateMarginFast(a);
    const soldOut = items.filter(i => i.category === 'sold_out').sort(byMargin);
    const unlisted = items.filter(i => i.category === 'unlisted').sort(byMargin);
    let html = '';
    if (soldOut.length) {
      html += `<div class="la-reorder-section-header">売れて在庫切れ（${soldOut.length}件）</div>`;
      html += soldOut.map(item => renderReorderItem(item)).join('');
    }
    if (unlisted.length) {
      html += `<div class="la-reorder-section-header">未出品在庫切れ（${unlisted.length}件）</div>`;
      html += unlisted.map(item => renderReorderItem(item)).join('');
    }
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<div class="la-reorder-empty">読み込みエラー: ${escHtml(e.message ?? '')}</div>`;
  }
}

function _extractKeyword(title) {
  const tokens = title.split(/[\s/,()[\]]+/).filter(t => t.length > 0);
  const cleaned = tokens.map(t => t.replace(/^[-.]|[-.]$/g, ''));
  const candidates = cleaned.filter(t => t.length >= 3 && /[A-Za-z]/.test(t) && /\d/.test(t));
  if (!candidates.length) return title.split(' ').slice(0, 3).join(' ');
  const letterFirst = candidates.filter(c => /^[A-Za-z]/.test(c));
  const pool = letterFirst.length ? letterFirst : candidates;
  const modelNum = pool.reduce((a, b) => a.length >= b.length ? a : b);
  // モデル番号の前にあるブランド名（英字のみ・先頭大文字）を付加
  const modelIdx = cleaned.indexOf(modelNum);
  if (modelIdx > 0) {
    const brand = tokens.slice(0, modelIdx).find(t => /^[A-Z][a-zA-Z]+$/.test(t));
    if (brand) return `${brand} ${modelNum}`;
  }
  return modelNum;
}

function renderReorderItem(item) {
  _reorderItemsCache.set(item.id, item);
  const imgHtml = item.image_url
    ? `<img src="${escHtml(item.image_url ?? '')}" class="la-reorder-img" onerror="this.style.display='none'">`
    : '';
  const soldBadge = item.sold_count > 0
    ? `<span class="category-badge sold-badge">Sold ${item.sold_count}</span>`
    : '';
  const platformBadge = item.platform
    ? `<span class="platform-badge">${escHtml(item.platform ?? '')}</span>`
    : '';
  const kw = _extractKeyword(item.title || '');
  const enc = encodeURIComponent(kw);
  const id = Number(item.id);
  return `
    <div class="la-reorder-item" id="reorder-${id}">
      <div class="la-reorder-info">
        ${imgHtml}
        <div class="la-reorder-details">
          <div class="la-reorder-title">${escHtml(item.title ?? '')}</div>
          <div class="la-reorder-meta">
            <span>仕入: ¥${(item.purchase_price_jpy || 0).toLocaleString()}</span>
            <span>eBay: $${escHtml(String(item.ebay_price_usd || '—') ?? '')}</span>
            ${soldBadge}${platformBadge}
          </div>
          <div class="la-research-result" id="research-result-${id}"></div>
          <div class="la-search-links" style="margin-top:6px">
            <a href="https://auctions.yahoo.co.jp/search/search/${enc}/0/?n=50" target="_blank" rel="noopener" class="la-search-link">ヤフオク</a>
            <a href="https://jp.mercari.com/search?keyword=${enc}&status=on_sale" target="_blank" rel="noopener" class="la-search-link">メルカリ</a>
            <a href="https://paypayfleamarket.yahoo.co.jp/search/${enc}" target="_blank" rel="noopener" class="la-search-link">Yahoo!フリマ</a>
          </div>
        </div>
      </div>
      <div class="la-reorder-reflect">
        <input type="url" id="eship-url-${id}" placeholder="仕入れ元URLを貼り付け"
          class="form-control" style="font-size:13px"
          oninput="_onEshipUrlInput(${id}, this.value)">
        <select id="eship-platform-${id}" class="form-control" style="width:120px;font-size:13px;flex-shrink:0">
          <option value="">自動判定</option>
          <option value="ヤフオク">ヤフオク</option>
          <option value="メルカリ">メルカリ</option>
          <option value="Yahoo!フリマ">Yahoo!フリマ</option>
          <option value="ラクマ">ラクマ</option>
          <option value="ハードオフ">ハードオフ</option>
          <option value="駿河屋">駿河屋</option>
        </select>
        <button class="btn btn-primary btn-sm" id="eship-submit-${id}"
          onclick="reflectToEship(${id})" disabled style="white-space:nowrap;flex-shrink:0">
          eShipに反映
        </button>
        <div id="eship-result-${id}" style="font-size:12px;min-width:80px"></div>
      </div>
    </div>
  `;
}

function _detectPlatform(url) {
  if (url.includes('auctions.yahoo.co.jp')) return 'ヤフオク';
  if (url.includes('mercari.com')) return 'メルカリ';
  if (url.includes('paypayfleamarket')) return 'Yahoo!フリマ';
  if (url.includes('fril.jp')) return 'ラクマ';
  if (url.includes('hardoff')) return 'ハードオフ';
  if (url.includes('suruga-ya')) return '駿河屋';
  return '';
}

function _onEshipUrlInput(itemId, url) {
  const platform = _detectPlatform(url);
  const sel = document.getElementById(`eship-platform-${itemId}`);
  if (sel && platform) sel.value = platform;
  const btn = document.getElementById(`eship-submit-${itemId}`);
  if (btn) btn.disabled = !url.startsWith('http');
}

function _calcMarginFromDemand(purchasePriceJpy, demandResult) {
  const rate = demandResult.exchange_rate || window._fxRate || 155;
  const medianUsd = demandResult.price_analysis?.median_usd;
  if (!medianUsd) return null;
  const sourceCostUsd = (purchasePriceJpy || 0) / rate;
  const totalCostUsd = sourceCostUsd + 20;  // 国際送料$20固定
  const ebayFee = medianUsd * 0.129;
  const payoneerFee = (medianUsd - ebayFee) * 0.02;
  const netProfit = medianUsd - ebayFee - payoneerFee - totalCostUsd;
  const marginPct = medianUsd > 0 ? (netProfit / medianUsd * 100) : 0;
  return { netProfit, marginPct, medianUsd };
}

function updateCardWithResearch(itemId, data) {
  const resultEl = document.getElementById(`research-result-${itemId}`);
  if (!resultEl) return;
  if (!data || data.status !== 'ok') {
    const msg = data?.status === 'no_results' ? '需要なし' : '価格データなし';
    resultEl.innerHTML = `<span class="la-profit-badge neg">${msg}</span>`;
    return;
  }
  const { margin_pct: m, net_profit_usd: p, median_usd: med, items_found: n } = data;
  const cls = m >= 20 ? 'high' : m >= 10 ? 'mid' : m >= 0 ? 'low' : 'neg';
  resultEl.innerHTML = `
    <span class="la-profit-badge ${cls}">利益率 ${m.toFixed(1)}% ／ $${p.toFixed(2)}</span>
    <span class="la-profit-detail">eBay現在相場 $${med.toFixed(2)} ・${n}件</span>
  `;
  const cardEl = document.getElementById(`reorder-${itemId}`);
  if (cardEl) cardEl.style.opacity = m < 0 ? '0.4' : '1';
}

async function _researchOne(item) {
  const resultEl = document.getElementById(`research-result-${item.id}`);
  if (resultEl) resultEl.innerHTML = '<span style="font-size:12px;color:var(--text-secondary)">検索中...</span>';
  try {
    const kw = _extractKeyword(item.title || '');
    const resp = await fetch('/api/listing-assistant/quick-price', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ebay_query: kw,
        purchase_price_jpy: item.purchase_price_jpy || 0,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    _researchResults.set(item.id, data);
    updateCardWithResearch(item.id, data);
  } catch (e) {
    console.warn(`[research] id=${item.id} error:`, e?.message);
    const el = document.getElementById(`research-result-${item.id}`);
    if (el) el.innerHTML = '<span style="font-size:12px;color:var(--text-secondary)">エラー</span>';
  }
}

async function startBatchResearch() {
  const btn = document.getElementById('batch-research-btn');
  if (!btn) return;
  btn.disabled = true;

  const allItems = Array.from(_reorderItemsCache.values())
    .sort((a, b) => _estimateMarginFast(b) - _estimateMarginFast(a))
    .slice(0, 20);

  if (!allItems.length) { btn.textContent = '候補なし'; btn.disabled = false; return; }

  // 4件並列で処理（Browse API はレートリミット緩い）
  const CONCURRENCY = 4;
  let done = 0;
  for (let i = 0; i < allItems.length; i += CONCURRENCY) {
    const batch = allItems.slice(i, i + CONCURRENCY);
    btn.textContent = `リサーチ中 ${Math.min(i + CONCURRENCY, allItems.length)}/${allItems.length}`;
    await Promise.all(batch.map(item => _researchOne(item)));
    done += batch.length;
  }

  btn.textContent = '再リサーチ';
  btn.disabled = false;
}

async function reflectToEship(itemId) {
  const item = _reorderItemsCache.get(itemId);
  if (!item) return;
  const urlInput = document.getElementById(`eship-url-${itemId}`);
  const platformSel = document.getElementById(`eship-platform-${itemId}`);
  const btn = document.getElementById(`eship-submit-${itemId}`);
  const resultEl = document.getElementById(`eship-result-${itemId}`);

  const sourceUrl = urlInput?.value?.trim() || '';
  const platform = platformSel?.value || '';
  if (!sourceUrl) return;

  btn.disabled = true;
  btn.textContent = '反映中...';
  resultEl.innerHTML = '<span style="color:var(--text-secondary)">eShipを更新中... (20〜40秒)</span>';

  try {
    const resp = await fetch('/api/listing-assistant/update-eship-source', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        eship_id: Number(item.eship_id ?? item.id),
        source_url: sourceUrl,
        item_title: item.title || '',
        platform,
      }),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      resultEl.innerHTML = `<span style="color:var(--green,#1a7f37)">✓ ${escHtml(data.message ?? '更新完了')}</span>`;
      btn.textContent = '反映済み';
    } else {
      resultEl.innerHTML = `<span style="color:var(--red)">✗ ${escHtml(data.message ?? 'エラー')}</span>`;
      btn.disabled = false;
      btn.textContent = 'eShipに反映';
    }
  } catch (e) {
    resultEl.innerHTML = `<span style="color:var(--red)">エラー: ${escHtml(e.message ?? '')}</span>`;
    btn.disabled = false;
    btn.textContent = 'eShipに反映';
  }
}

function renderPlatformResults(platform, items) {
  if (!items || !items.length) {
    return `
      <div class="la-platform-section">
        <div class="la-platform-name">${escHtml(platform ?? '')}</div>
        <div style="font-size:12px;color:var(--text-muted);padding:4px 0">候補なし</div>
      </div>`;
  }
  const itemsHtml = items.map(i => {
    const safeSrc = i.image_url && /^https?:\/\//.test(i.image_url) ? escHtml(i.image_url ?? '') : '';
    const safeHref = i.url && /^https?:\/\//.test(i.url) ? escHtml(i.url ?? '') : '#';
    return `
      <a href="${safeHref}" target="_blank" rel="noopener" class="la-source-item">
        ${safeSrc ? `<img src="${safeSrc}" class="la-source-img" onerror="this.style.display='none'">` : ''}
        <div class="la-source-info">
          <div class="la-source-title">${escHtml(i.title ?? '')}</div>
          <div class="la-source-price">¥${(i.price_jpy ?? 0).toLocaleString()}</div>
          <div class="la-source-condition">${escHtml(i.condition ?? '')}</div>
        </div>
      </a>
    `;
  }).join('');
  return `
    <div class="la-platform-section">
      <div class="la-platform-name">${escHtml(platform ?? '')} (${items.length}件)</div>
      <div class="la-platform-items">${itemsHtml}</div>
    </div>`;
}
