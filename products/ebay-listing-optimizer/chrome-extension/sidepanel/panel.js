/**
 * eBay SEO Optimizer — Side Panel JavaScript
 * タブ切替・バックエンドAPI通信・UI描画
 */

// ============================================================
// API通信ヘルパー
// ============================================================

function api(method, path, body) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      { type: "API_REQUEST", method, path, body },
      (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (response && response.error) {
          reject(new Error(response.error));
          return;
        }
        resolve(response);
      }
    );
  });
}

// ============================================================
// 状態管理
// ============================================================

let currentPageData = null;
let currentSku = null;
let backendConnected = false;

// ============================================================
// バックエンド接続チェック
// ============================================================

async function checkBackend() {
  const dot = document.querySelector("#status-dot .dot");
  const banner = document.getElementById("error-banner");
  const errorText = document.getElementById("error-text");

  try {
    const resp = await api("GET", "/health");
    if (resp && resp.status === "ok") {
      dot.className = "dot dot-ok";
      banner.style.display = "none";
      backendConnected = true;
      return true;
    }
  } catch (e) {
    // fall through
  }

  dot.className = "dot dot-error";
  banner.style.display = "block";
  errorText.textContent = "Backend not connected — start the server first";
  backendConnected = false;
  return false;
}

// ============================================================
// タブ切替
// ============================================================

function initTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");

      // タブ切替時にデータをロード
      if (btn.dataset.tab === "all") loadAllListings();
      if (btn.dataset.tab === "history") loadHistory();
    });
  });
}

// ============================================================
// Current Page タブ
// ============================================================

function showPageData(data) {
  if (!data || data.pageType === "unknown") {
    document.getElementById("no-page-data").style.display = "block";
    document.getElementById("page-data").style.display = "none";
    return;
  }

  document.getElementById("no-page-data").style.display = "none";
  document.getElementById("page-data").style.display = "block";

  // 画像
  const imagesEl = document.getElementById("listing-images");
  imagesEl.innerHTML = "";
  if (data.images && data.images.length > 0) {
    data.images.slice(0, 8).forEach((url) => {
      const img = document.createElement("img");
      img.src = url;
      img.alt = "";
      imagesEl.appendChild(img);
    });
  }

  // タイトル
  document.getElementById("listing-title").textContent = data.title || "";
  document.getElementById("listing-price").textContent = data.price || "";
  document.getElementById("listing-condition").textContent = data.condition || "";
  document.getElementById("listing-chars").textContent =
    (data.titleLength || 0) + "/80 chars";

  // クイックスコアを表示
  displayQuickScore(data);
}

function displayQuickScore(data) {
  const score = quickScore(data);
  const scoreCircle = document.getElementById("score-circle");
  const scoreNumber = document.getElementById("score-number");

  scoreNumber.textContent = score;
  scoreCircle.className = "score-circle " + scoreColorClass(score);

  // サブスコア
  const titleScore = calcTitleScore(data);
  const photoScore = calcPhotoScore(data);
  const specScore = calcSpecificsScore(data);
  const descScore = 50; // ページからは判定困難

  setScoreBar("title", titleScore);
  setScoreBar("photos", photoScore);
  setScoreBar("specifics", specScore);
  setScoreBar("desc", descScore);
}

function quickScore(data) {
  let score = 0;
  score += Math.max(0, calcTitleScore(data)) * 0.35;
  score += Math.min(100, calcPhotoScore(data)) * 0.15;
  score += calcSpecificsScore(data) * 0.25;
  score += 50 * 0.25; // description placeholder
  return Math.round(score);
}

function calcTitleScore(data) {
  const ratio = Math.min((data.titleLength || 0) / 80, 1);
  let s = ratio * 100;
  if (!data.titleLength) s = 0;
  if (/L@@K|WOW|!!!|LOOK/i.test(data.title || "")) s -= 15;
  return Math.max(0, Math.round(s));
}

function calcPhotoScore(data) {
  const count = data.imageCount || (data.images ? data.images.length : 0);
  if (count >= 5) return 100;
  return 25 + count * 15;
}

function calcSpecificsScore(data) {
  const count = data.specifics ? Object.keys(data.specifics).length : 0;
  if (count >= 5) return 100;
  if (count >= 3) return 70;
  if (count >= 1) return 40;
  return 0;
}

function setScoreBar(name, score) {
  const bar = document.getElementById("bar-" + name);
  const val = document.getElementById("val-" + name);
  if (bar) {
    bar.style.width = score + "%";
    bar.className = "score-bar-fill " + barColorClass(score);
  }
  if (val) val.textContent = score;
}

function scoreColorClass(score) {
  if (score < 40) return "score-red";
  if (score < 70) return "score-yellow";
  return "score-green";
}

function barColorClass(score) {
  if (score < 40) return "bar-red";
  if (score < 70) return "bar-yellow";
  return "bar-green";
}

// ============================================================
// バックエンドのスコアを使って更新
// ============================================================

async function loadBackendScore(sku) {
  if (!backendConnected || !sku) return;

  try {
    const data = await api("GET", "/api/listings/" + encodeURIComponent(sku));
    if (data && data.score) {
      displayBackendScore(data.score);
    }
  } catch (e) {
    // バックエンドスコアがなくてもクイックスコアを表示し続ける
  }
}

function displayBackendScore(score) {
  const scoreCircle = document.getElementById("score-circle");
  const scoreNumber = document.getElementById("score-number");

  scoreNumber.textContent = score.overall;
  scoreCircle.className = "score-circle " + scoreColorClass(score.overall);

  setScoreBar("title", score.title);
  setScoreBar("photos", score.photos);
  setScoreBar("specifics", score.specifics);
  setScoreBar("desc", score.description);

  // Issues
  if (score.issues || score.suggestions) {
    displayIssues(score.issues || [], score.suggestions || []);
  }
}

function displayIssues(issues, suggestions) {
  const section = document.getElementById("issues-section");
  const list = document.getElementById("issue-list");
  list.innerHTML = "";

  if (issues.length === 0 && suggestions.length === 0) {
    section.style.display = "none";
    return;
  }

  section.style.display = "block";

  issues.forEach((text) => {
    const li = document.createElement("li");
    li.className = "issue";
    li.textContent = text;
    list.appendChild(li);
  });

  suggestions.forEach((text) => {
    const li = document.createElement("li");
    li.className = "suggestion";
    li.textContent = text;
    list.appendChild(li);
  });
}

// ============================================================
// AI最適化
// ============================================================

async function runOptimization() {
  if (!currentSku) {
    showToast("No listing SKU found. Fetch from eBay first.");
    return;
  }

  const btn = document.getElementById("btn-optimize");
  const loading = document.getElementById("optimize-loading");
  const result = document.getElementById("optimize-result");

  btn.disabled = true;
  loading.style.display = "block";
  result.style.display = "none";

  try {
    const resp = await api("POST", "/api/optimize/" + encodeURIComponent(currentSku));
    displayOptimizationResult(resp);
  } catch (e) {
    result.style.display = "block";
    result.innerHTML = '<div class="error-banner">' + escapeHtml(e.message) + "</div>";
  } finally {
    btn.disabled = false;
    loading.style.display = "none";
  }
}

function displayOptimizationResult(data) {
  const container = document.getElementById("optimize-result");
  container.style.display = "block";

  let html = '<div class="comparison">';

  // タイトル
  if (data.suggested_title) {
    html += buildComparisonItem(
      "Title",
      data.original_title || "",
      data.suggested_title,
      "title"
    );
  }

  // 説明文
  if (data.suggested_description) {
    html += buildComparisonItem(
      "Description",
      truncate(data.original_description || "", 300),
      truncate(data.suggested_description, 300),
      "description"
    );
  }

  // Item Specifics
  if (data.suggested_specifics && Object.keys(data.suggested_specifics).length > 0) {
    const specHtml = Object.entries(data.suggested_specifics)
      .map(([k, v]) => "<b>" + escapeHtml(k) + "</b>: " + escapeHtml(v))
      .join("<br>");
    html +=
      '<div class="comp-item">' +
      '<div class="comp-label">Suggested Specifics</div>' +
      '<div class="comp-box suggested">' +
      specHtml +
      "</div>" +
      "</div>";
  }

  // Reasoning
  if (data.reasoning) {
    html +=
      '<div class="reasoning">' + escapeHtml(data.reasoning) + "</div>";
  }

  // Apply buttons
  html +=
    '<div class="comp-actions" style="margin-top:12px">' +
    '<button class="btn btn-success btn-sm" onclick="applyOptimization(true, true, true)">Apply All</button>' +
    '<button class="btn btn-secondary btn-sm" onclick="applyOptimization(true, false, false)">Apply Title Only</button>' +
    "</div>";

  html += "</div>";
  container.innerHTML = html;
}

function buildComparisonItem(label, original, suggested, field) {
  return (
    '<div class="comp-item">' +
    '<div class="comp-label">' +
    escapeHtml(label) +
    "</div>" +
    '<div class="comp-box original">' +
    escapeHtml(original) +
    "</div>" +
    '<div class="comp-label" style="margin-top:6px">Suggested</div>' +
    '<div class="comp-box suggested">' +
    escapeHtml(suggested) +
    "</div>" +
    "</div>"
  );
}

// ============================================================
// 変更適用
// ============================================================

async function applyOptimization(applyTitle, applyDescription, applySpecifics) {
  if (!currentSku) return;

  try {
    const resp = await api("POST", "/api/apply/" + encodeURIComponent(currentSku), {
      apply_title: applyTitle,
      apply_description: applyDescription,
      apply_specifics: applySpecifics,
    });

    if (resp.applied && resp.applied.length > 0) {
      showToast("Applied: " + resp.applied.join(", "));
    }
    if (resp.errors && resp.errors.length > 0) {
      showToast("Errors: " + resp.errors.join(", "), true);
    }
  } catch (e) {
    showToast("Apply failed: " + e.message, true);
  }
}

// ============================================================
// 競合分析
// ============================================================

async function runCompetitorAnalysis() {
  if (!currentSku) {
    showToast("No listing SKU found.");
    return;
  }

  const btn = document.getElementById("btn-competitor");
  const loading = document.getElementById("competitor-loading");
  const result = document.getElementById("competitor-result");

  btn.disabled = true;
  loading.style.display = "block";

  try {
    const resp = await api("POST", "/api/competitor/" + encodeURIComponent(currentSku));
    displayCompetitorResult(resp);
  } catch (e) {
    result.innerHTML = '<div class="error-banner">' + escapeHtml(e.message) + "</div>";
  } finally {
    btn.disabled = false;
    loading.style.display = "none";
  }
}

function displayCompetitorResult(data) {
  const container = document.getElementById("competitor-result");
  let html = "";

  // キーワード分析
  if (data.keyword_analysis) {
    const kw = data.keyword_analysis;

    if (kw.missing_keywords && kw.missing_keywords.length > 0) {
      html += '<div style="margin-bottom:8px"><b>Missing Keywords:</b></div>';
      kw.missing_keywords.forEach((w) => {
        html +=
          '<span class="keyword-tag missing">' + escapeHtml(w) + "</span>";
      });
    }

    if (kw.common_keywords && kw.common_keywords.length > 0) {
      html += '<div style="margin-top:8px;margin-bottom:8px"><b>Found in Competitors:</b></div>';
      kw.common_keywords.slice(0, 15).forEach((w) => {
        html +=
          '<span class="keyword-tag found">' + escapeHtml(w) + "</span>";
      });
    }

    if (kw.avg_price) {
      html +=
        '<div style="margin-top:8px;font-size:12px;color:#666">Avg competitor price: $' +
        kw.avg_price.toFixed(2) +
        "</div>";
    }
  }

  // 競合リスト
  if (data.competitors && data.competitors.length > 0) {
    html += '<div style="margin-top:12px"><b>Top Competitors (' + data.competitors.length + ")</b></div>";
    data.competitors.slice(0, 5).forEach((c) => {
      html +=
        '<div class="listing-row" style="margin-top:4px">' +
        '<div class="row-title">' +
        escapeHtml(c.title || "") +
        "</div>" +
        '<div style="font-size:11px;color:#888">$' +
        (c.price || 0).toFixed(2) +
        "</div>" +
        "</div>";
    });
  }

  container.innerHTML = html || '<div style="color:#888;font-size:12px">No competitor data</div>';
}

// ============================================================
// All Listings タブ
// ============================================================

async function loadAllListings() {
  const listEl = document.getElementById("all-listings-list");
  const statsEl = document.getElementById("all-listings-stats");

  if (!backendConnected) {
    listEl.innerHTML = '<div class="empty-state"><p>Backend not connected</p></div>';
    return;
  }

  listEl.innerHTML = '<div class="loading"><span class="spinner"></span> Loading...</div>';

  try {
    const data = await api("GET", "/api/listings");
    const stats = await api("GET", "/api/listings/stats");

    // 統計表示
    statsEl.innerHTML =
      '<div class="mini-stat"><div class="val">' + (stats.total || 0) + '</div><div class="lbl">Total</div></div>' +
      '<div class="mini-stat"><div class="val">' + (stats.low_score_count || 0) + '</div><div class="lbl">Low Score</div></div>' +
      '<div class="mini-stat"><div class="val">' + (stats.scored || 0) + '</div><div class="lbl">Analyzed</div></div>';

    // リスト表示
    if (!data.listings || data.listings.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><p>No listings. Click "Fetch from eBay".</p></div>';
      return;
    }

    listEl.innerHTML = "";
    data.listings.forEach((item) => {
      const scoreVal = item.score ? item.score.overall : "-";
      const scoreClass = item.score ? rowScoreClass(item.score.overall) : "s-none";
      const row = document.createElement("div");
      row.className = "listing-row";
      row.innerHTML =
        '<div class="row-title">' + escapeHtml(item.title) + "</div>" +
        '<div class="row-score ' + scoreClass + '">' + scoreVal + "</div>";
      row.addEventListener("click", () => selectListingFromAll(item.sku));
      listEl.appendChild(row);
    });
  } catch (e) {
    listEl.innerHTML = '<div class="empty-state"><p>' + escapeHtml(e.message) + "</p></div>";
  }
}

function rowScoreClass(score) {
  if (score < 40) return "s-red";
  if (score < 70) return "s-yellow";
  return "s-green";
}

async function selectListingFromAll(sku) {
  currentSku = sku;

  // Current Pageタブに切り替え
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
  document.querySelector('[data-tab="current"]').classList.add("active");
  document.getElementById("tab-current").classList.add("active");

  // バックエンドからデータをロード
  try {
    const data = await api("GET", "/api/listings/" + encodeURIComponent(sku));
    showPageData({
      title: data.title,
      price: "$" + (data.price_usd || 0).toFixed(2),
      condition: data.condition,
      images: data.image_urls || [],
      specifics: data.item_specifics || {},
      itemId: data.listing_id,
      imageCount: (data.image_urls || []).length,
      titleLength: (data.title || "").length,
      pageType: "item_page",
    });
    if (data.score) {
      displayBackendScore(data.score);
    }
  } catch (e) {
    showToast("Failed to load listing: " + e.message, true);
  }
}

async function fetchAllFromEbay() {
  const btn = document.getElementById("btn-fetch-all");
  btn.disabled = true;
  btn.textContent = "Fetching...";

  try {
    const resp = await api("POST", "/api/listings/fetch");
    showToast("Fetched " + (resp.count || 0) + " listings");
    loadAllListings();
  } catch (e) {
    showToast("Fetch failed: " + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Fetch from eBay";
  }
}

async function analyzeAllListings() {
  const btn = document.getElementById("btn-analyze-all");
  btn.disabled = true;
  btn.textContent = "Analyzing...";

  try {
    const resp = await api("POST", "/api/analysis/batch");
    showToast("Analyzed " + (resp.analyzed || 0) + " listings");
    loadAllListings();
  } catch (e) {
    showToast("Analysis failed: " + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze All";
  }
}

// ============================================================
// History タブ
// ============================================================

async function loadHistory() {
  const listEl = document.getElementById("history-list");

  if (!backendConnected) {
    listEl.innerHTML = '<div class="empty-state"><p>Backend not connected</p></div>';
    return;
  }

  listEl.innerHTML = '<div class="loading"><span class="spinner"></span> Loading...</div>';

  try {
    const data = await api("GET", "/api/apply/history");

    if (!data.history || data.history.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><p>No changes applied yet</p></div>';
      return;
    }

    listEl.innerHTML = "";
    data.history.forEach((h) => {
      const item = document.createElement("div");
      item.className = "history-item";
      const statusClass = h.success ? "success" : "fail";
      const statusText = h.success ? "Success" : "Failed";
      item.innerHTML =
        '<div><span class="field">' + escapeHtml(h.field_changed) + "</span> — " + escapeHtml(h.sku) + "</div>" +
        '<div class="time">' + formatDate(h.applied_at) + ' <span class="' + statusClass + '">' + statusText + "</span></div>" +
        (h.error_message ? '<div style="color:#dc2626;font-size:11px">' + escapeHtml(h.error_message) + "</div>" : "");
      listEl.appendChild(item);
    });
  } catch (e) {
    listEl.innerHTML = '<div class="empty-state"><p>' + escapeHtml(e.message) + "</p></div>";
  }
}

// ============================================================
// ユーティリティ
// ============================================================

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function truncate(text, maxLen) {
  if (!text) return "";
  return text.length > maxLen ? text.slice(0, maxLen) + "..." : text;
}

function formatDate(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function showToast(message, isError) {
  // 既存のトーストを削除
  const existing = document.querySelector(".panel-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = "panel-toast";
  toast.style.cssText =
    "position:fixed;bottom:16px;left:16px;right:16px;padding:10px 14px;border-radius:8px;font-size:12px;z-index:100;text-align:center;" +
    (isError
      ? "background:#fef2f2;color:#991b1b;border:1px solid #fecaca"
      : "background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0");
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ============================================================
// ストレージからページデータを取得
// ============================================================

function loadPageDataFromStorage() {
  chrome.storage.local.get("currentPageData", (result) => {
    if (result.currentPageData) {
      currentPageData = result.currentPageData;
      showPageData(currentPageData);

      // SKUはContent Scriptからは取れないのでitemIdを使う
      if (currentPageData.itemId) {
        currentSku = currentPageData.itemId;
      }
    }
  });
}

// ストレージの変更を監視（Content Scriptがデータを更新した時）
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.currentPageData) {
    currentPageData = changes.currentPageData.newValue;
    if (currentPageData) {
      showPageData(currentPageData);
      if (currentPageData.itemId) {
        currentSku = currentPageData.itemId;
      }
    }
  }
});

// ============================================================
// イベントリスナー
// ============================================================

function initEventListeners() {
  // AI Optimization
  document.getElementById("btn-optimize").addEventListener("click", runOptimization);

  // Competitor Analysis
  document.getElementById("btn-competitor").addEventListener("click", runCompetitorAnalysis);

  // All Listings タブ
  document.getElementById("btn-fetch-all").addEventListener("click", fetchAllFromEbay);
  document.getElementById("btn-analyze-all").addEventListener("click", analyzeAllListings);
}

// ============================================================
// 初期化
// ============================================================

async function init() {
  initTabs();
  initEventListeners();
  await checkBackend();
  loadPageDataFromStorage();

  // 30秒ごとにバックエンド接続をチェック
  setInterval(checkBackend, 30000);
}

// applyOptimizationをグローバルに公開（onclick属性から呼ばれるため）
window.applyOptimization = applyOptimization;

document.addEventListener("DOMContentLoaded", init);
