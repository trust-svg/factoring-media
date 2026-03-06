/* eBay SEO Optimizer — Frontend JavaScript */

// ============================================================
// Utility
// ============================================================

async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "API Error");
  }
  return resp.json();
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

function scoreClass(score) {
  if (score === null || score === undefined) return "score-none";
  if (score < 40) return "score-red";
  if (score < 70) return "score-yellow";
  return "score-green";
}

function scoreText(score) {
  if (score === null || score === undefined) return "-";
  return score;
}

// ============================================================
// Dashboard
// ============================================================

async function loadDashboard() {
  const container = document.getElementById("listings-table");
  if (!container) return;

  container.innerHTML = '<tr><td colspan="7" class="loading"><span class="spinner"></span> Loading...</td></tr>';

  try {
    const [listingsData, statsData] = await Promise.all([
      api("GET", "/api/listings"),
      api("GET", "/api/listings/stats"),
    ]);

    // Update summary cards
    const totalEl = document.getElementById("stat-total");
    const lowEl = document.getElementById("stat-low");
    const scoredEl = document.getElementById("stat-scored");
    if (totalEl) totalEl.textContent = statsData.total;
    if (lowEl) lowEl.textContent = statsData.low_score_count;
    if (scoredEl) scoredEl.textContent = statsData.scored;

    // Render table
    const listings = listingsData.listings;
    if (listings.length === 0) {
      container.innerHTML = '<tr><td colspan="7" class="loading">No listings found. Click "Fetch from eBay" to load.</td></tr>';
      return;
    }

    container.innerHTML = listings.map(l => {
      const img = l.image_urls.length > 0
        ? `<img src="${l.image_urls[0]}" class="thumb" alt="" loading="lazy">`
        : '<div class="thumb"></div>';
      const score = l.score ? l.score.overall : null;
      const cls = scoreClass(score);
      return `<tr>
        <td><input type="checkbox" class="listing-check" value="${l.sku}"></td>
        <td>${img}</td>
        <td><a href="/listing/${encodeURIComponent(l.sku)}">${escapeHtml(l.title)}</a></td>
        <td><span class="score-badge ${cls}">${scoreText(score)}</span></td>
        <td>$${l.price_usd.toFixed(2)}</td>
        <td>${escapeHtml(l.category_name || "-")}</td>
        <td><a href="/listing/${encodeURIComponent(l.sku)}" class="btn btn-secondary btn-sm">Detail</a></td>
      </tr>`;
    }).join("");
  } catch (e) {
    container.innerHTML = `<tr><td colspan="7" class="loading">Error: ${escapeHtml(e.message)}</td></tr>`;
  }
}

async function fetchFromEbay() {
  const btn = document.getElementById("btn-fetch");
  if (btn) btn.disabled = true;
  showToast("Fetching listings from eBay...", "info");

  try {
    const result = await api("POST", "/api/listings/fetch");
    showToast(`Fetched ${result.count} listings`, "success");
    loadDashboard();
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function analyzeAll() {
  showToast("Analyzing all listings...", "info");
  try {
    const result = await api("POST", "/api/analysis/batch");
    showToast(`Analyzed ${result.analyzed} listings`, "success");
    loadDashboard();
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  }
}

// ============================================================
// Listing Detail
// ============================================================

async function loadListingDetail(sku) {
  const container = document.getElementById("detail-content");
  if (!container) return;

  try {
    const listing = await api("GET", `/api/listings/${encodeURIComponent(sku)}`);
    renderDetailInfo(listing);
    renderScoreBreakdown(listing.score);
    renderIssues(listing.score);

    // Load optimization result if exists
    const optData = await api("GET", `/api/optimize/${encodeURIComponent(sku)}/result`);
    if (optData.optimization) {
      renderOptimization(optData.optimization, listing);
    }
  } catch (e) {
    container.innerHTML = `<div class="loading">Error: ${escapeHtml(e.message)}</div>`;
  }
}

function renderDetailInfo(listing) {
  const el = document.getElementById("detail-info");
  if (!el) return;

  const images = listing.image_urls.map(url =>
    `<img src="${url}" alt="" loading="lazy">`
  ).join("");

  const specifics = Object.entries(listing.item_specifics || {}).map(([k, v]) =>
    `<div><strong>${escapeHtml(k)}:</strong> ${escapeHtml(Array.isArray(v) ? v.join(", ") : String(v))}</div>`
  ).join("");

  el.innerHTML = `
    <div class="detail-header">
      <div class="detail-images">${images || '<div class="thumb"></div>'}</div>
      <div class="detail-info">
        <h2>${escapeHtml(listing.title)}</h2>
        <div class="meta">
          <div>SKU: ${escapeHtml(listing.sku)}</div>
          <div>Price: $${listing.price_usd.toFixed(2)}</div>
          <div>Category: ${escapeHtml(listing.category_name || "-")}</div>
          <div>Condition: ${escapeHtml(listing.condition || "-")}</div>
          <div>Photos: ${listing.image_urls.length}</div>
        </div>
      </div>
    </div>
    ${specifics ? `<div class="section"><h3>Item Specifics</h3>${specifics}</div>` : ""}
  `;
}

function renderScoreBreakdown(score) {
  const el = document.getElementById("score-breakdown");
  if (!el || !score) return;

  const items = [
    { label: "Overall", value: score.overall },
    { label: "Title", value: score.title },
    { label: "Description", value: score.description },
    { label: "Specifics", value: score.specifics },
    { label: "Photos", value: score.photos },
  ];

  el.innerHTML = items.map(item => `
    <div class="score-item">
      <div class="score-value ${scoreClass(item.value)}">${item.value}</div>
      <div class="score-label">${item.label}</div>
    </div>
  `).join("");
}

function renderIssues(score) {
  const el = document.getElementById("issues-list");
  if (!el || !score) return;

  const issues = (score.issues || []).map(i =>
    `<li class="issue">${escapeHtml(i)}</li>`
  ).join("");
  const suggestions = (score.suggestions || []).map(s =>
    `<li class="suggestion">${escapeHtml(s)}</li>`
  ).join("");

  el.innerHTML = issues + suggestions || '<li>No issues found</li>';
}

function renderOptimization(opt, listing) {
  const el = document.getElementById("optimization-result");
  if (!el) return;

  el.innerHTML = `
    <div class="comparison">
      <div class="comparison-box original">
        <div class="label">Current Title</div>
        ${escapeHtml(opt.original_title)}
        <div class="char-count">${opt.original_title.length}/80 chars</div>
      </div>
      <div class="comparison-box suggested">
        <div class="label">Suggested Title</div>
        ${escapeHtml(opt.suggested_title)}
        <div class="char-count">${opt.suggested_title.length}/80 chars</div>
      </div>
    </div>
    ${opt.suggested_description ? `
    <div class="comparison">
      <div class="comparison-box original">
        <div class="label">Current Description</div>
        <div style="max-height:200px;overflow:auto">${listing.description ? escapeHtml(listing.description).substring(0, 500) : "(empty)"}</div>
      </div>
      <div class="comparison-box suggested">
        <div class="label">Suggested Description</div>
        <div style="max-height:200px;overflow:auto">${opt.suggested_description.substring(0, 500)}</div>
      </div>
    </div>` : ""}
    ${opt.reasoning ? `<div style="margin-top:12px;font-size:14px;color:#666"><strong>Reasoning:</strong> ${escapeHtml(opt.reasoning)}</div>` : ""}
    <div style="margin-top:16px;display:flex;gap:8px">
      <button class="btn btn-success" onclick="applyChanges('${escapeHtml(listing.sku)}', true, ${!!opt.suggested_description}, false)">Apply Title</button>
      ${opt.suggested_description ? `<button class="btn btn-success" onclick="applyChanges('${escapeHtml(listing.sku)}', false, true, false)">Apply Description</button>` : ""}
      <button class="btn btn-success" onclick="applyChanges('${escapeHtml(listing.sku)}', true, ${!!opt.suggested_description}, true)">Apply All</button>
    </div>
    <div style="margin-top:8px;font-size:12px;color:#888">Status: ${opt.status}</div>
  `;
}

async function runOptimization(sku) {
  showToast("Running AI optimization...", "info");
  const btn = document.getElementById("btn-optimize");
  if (btn) btn.disabled = true;

  try {
    await api("POST", `/api/optimize/${encodeURIComponent(sku)}`);
    showToast("Optimization complete", "success");
    loadListingDetail(sku);
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runAnalysis(sku) {
  showToast("Running SEO analysis...", "info");
  try {
    await api("POST", `/api/analysis/${encodeURIComponent(sku)}`);
    showToast("Analysis complete", "success");
    loadListingDetail(sku);
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  }
}

async function runCompetitorAnalysis(sku) {
  showToast("Running competitor analysis...", "info");
  try {
    const result = await api("POST", `/api/competitor/${encodeURIComponent(sku)}`);
    renderCompetitorResults(result);
    showToast("Competitor analysis complete", "success");
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  }
}

function renderCompetitorResults(data) {
  const el = document.getElementById("competitor-results");
  if (!el) return;

  const analysis = data.keyword_analysis || {};
  const competitors = data.competitors || [];

  let html = "";

  if (analysis.top_keywords && analysis.top_keywords.length > 0) {
    const kwHtml = analysis.top_keywords.map(([kw, count]) =>
      `<span class="score-badge score-green" style="margin:2px">${escapeHtml(kw)} (${count})</span>`
    ).join("");
    html += `<div style="margin-bottom:12px"><strong>Top Keywords:</strong><br>${kwHtml}</div>`;
  }

  if (analysis.missing_keywords && analysis.missing_keywords.length > 0) {
    const missingHtml = analysis.missing_keywords.map(kw =>
      `<span class="score-badge score-red" style="margin:2px">${escapeHtml(kw)}</span>`
    ).join("");
    html += `<div style="margin-bottom:12px"><strong>Missing Keywords:</strong><br>${missingHtml}</div>`;
  }

  if (analysis.avg_price) {
    html += `<div style="margin-bottom:12px"><strong>Avg Competitor Price:</strong> $${analysis.avg_price}</div>`;
  }

  if (competitors.length > 0) {
    html += `<div style="margin-top:12px"><strong>Top Competitors (${competitors.length}):</strong></div>`;
    html += competitors.slice(0, 5).map(c =>
      `<div style="padding:8px 0;border-bottom:1px solid #f3f4f6;font-size:14px">
        ${escapeHtml(c.title)} — $${(c.price_usd || 0).toFixed(2)}
      </div>`
    ).join("");
  }

  el.innerHTML = html || "No competitor data available";
}

async function applyChanges(sku, applyTitle, applyDescription, applySpecifics) {
  if (!confirm("Apply changes to eBay? This will update your live listing.")) return;

  showToast("Applying changes to eBay...", "info");
  try {
    const result = await api("POST", `/api/apply/${encodeURIComponent(sku)}`, {
      apply_title: applyTitle,
      apply_description: applyDescription,
      apply_specifics: applySpecifics,
    });
    if (result.errors.length > 0) {
      showToast(`Applied with errors: ${result.errors.join(", ")}`, "error");
    } else {
      showToast(`Applied: ${result.applied.join(", ")}`, "success");
    }
    loadListingDetail(sku);
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  }
}

// ============================================================
// Batch
// ============================================================

async function loadBatchPage() {
  const container = document.getElementById("batch-table");
  if (!container) return;

  try {
    const data = await api("GET", "/api/listings");
    const listings = data.listings;

    container.innerHTML = listings.map(l => {
      const score = l.score ? l.score.overall : null;
      const cls = scoreClass(score);
      return `<tr>
        <td><input type="checkbox" class="batch-check" value="${l.sku}" ${score !== null && score < 50 ? "checked" : ""}></td>
        <td>${escapeHtml(l.title)}</td>
        <td><span class="score-badge ${cls}">${scoreText(score)}</span></td>
        <td>${escapeHtml(l.category_name || "-")}</td>
      </tr>`;
    }).join("");
  } catch (e) {
    container.innerHTML = `<tr><td colspan="4" class="loading">Error: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function selectAllBatch() {
  document.querySelectorAll(".batch-check").forEach(cb => cb.checked = true);
}

function deselectAllBatch() {
  document.querySelectorAll(".batch-check").forEach(cb => cb.checked = false);
}

async function batchOptimize() {
  const skus = Array.from(document.querySelectorAll(".batch-check:checked"))
    .map(cb => cb.value);

  if (skus.length === 0) {
    showToast("No listings selected", "error");
    return;
  }

  const progressEl = document.getElementById("batch-progress");
  const progressFill = document.getElementById("batch-progress-fill");
  const progressText = document.getElementById("batch-progress-text");
  if (progressEl) progressEl.style.display = "block";

  showToast(`Optimizing ${skus.length} listings...`, "info");

  try {
    const result = await api("POST", "/api/optimize/batch", { skus });
    if (progressFill) progressFill.style.width = "100%";
    if (progressText) progressText.textContent = `${result.optimized}/${skus.length} completed`;
    showToast(`Batch optimization complete: ${result.optimized} optimized`, "success");
    loadBatchPage();
  } catch (e) {
    showToast(`Error: ${e.message}`, "error");
  }
}

// ============================================================
// Helpers
// ============================================================

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Auto-init
document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("listings-table")) loadDashboard();
  if (document.getElementById("batch-table")) loadBatchPage();
});
