/**
 * eBay SEO Optimizer — Content Script
 * eBayページ上で動作し、出品情報を抽出してUIを注入する
 */

(function () {
  "use strict";

  // 二重注入防止
  if (window.__ebayOptimizer) return;
  window.__ebayOptimizer = true;

  // ============================================================
  // ページ種別判定
  // ============================================================

  function detectPageType() {
    const url = window.location.href;
    if (url.includes("/sh/lst") || url.includes("/myebay/selling")) return "listing_hub";
    if (url.includes("/itm/")) return "item_page";
    if (url.includes("/sl/list")) return "create_listing";
    return "unknown";
  }

  // ============================================================
  // 出品情報の抽出
  // ============================================================

  function extractItemPageData() {
    const title = document.querySelector("h1.x-item-title__mainTitle span")?.textContent?.trim()
      || document.querySelector("[data-testid='x-item-title'] span")?.textContent?.trim()
      || document.title.replace(" | eBay", "").trim();

    const price = document.querySelector(".x-price-primary span")?.textContent?.trim()
      || document.querySelector("[data-testid='x-price-primary']")?.textContent?.trim()
      || "";

    const condition = document.querySelector(".x-item-condition-text span")?.textContent?.trim()
      || document.querySelector("[data-testid='x-item-condition']")?.textContent?.trim()
      || "";

    // 画像を取得
    const images = [];
    document.querySelectorAll(".ux-image-carousel img, [data-testid='ux-image-carousel'] img").forEach(img => {
      const src = img.src || img.getAttribute("data-src") || "";
      if (src && !src.includes("s-l64") && !images.includes(src)) {
        images.push(src);
      }
    });

    // Item Specifics
    const specifics = {};
    document.querySelectorAll(".ux-layout-section-evo .ux-labels-values").forEach(row => {
      const label = row.querySelector(".ux-labels-values__labels span")?.textContent?.trim();
      const value = row.querySelector(".ux-labels-values__values span")?.textContent?.trim();
      if (label && value) specifics[label] = value;
    });

    // Item IDをURLから抽出
    const itemIdMatch = window.location.pathname.match(/\/itm\/(\d+)/);
    const itemId = itemIdMatch ? itemIdMatch[1] : "";

    return {
      title,
      price,
      condition,
      images,
      specifics,
      itemId,
      imageCount: images.length,
      titleLength: title.length,
      url: window.location.href,
    };
  }

  function extractListingHubData() {
    const listings = [];
    document.querySelectorAll(".listing-item, [data-testid='listing-row']").forEach(row => {
      const title = row.querySelector(".listing-title, .item-title")?.textContent?.trim() || "";
      const sku = row.querySelector("[data-testid='sku']")?.textContent?.trim() || "";
      listings.push({ title, sku });
    });
    return { listings, pageType: "listing_hub" };
  }

  // ============================================================
  // フローティングボタンの注入
  // ============================================================

  function injectFloatingButton() {
    const btn = document.createElement("div");
    btn.id = "ebay-seo-optimizer-btn";
    btn.innerHTML = `
      <button id="ebay-seo-btn-main" title="SEO Optimizer">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 20V10"/>
          <path d="M18 20V4"/>
          <path d="M6 20v-4"/>
        </svg>
      </button>
    `;
    document.body.appendChild(btn);

    document.getElementById("ebay-seo-btn-main").addEventListener("click", () => {
      // Side Panelを開くリクエスト
      chrome.runtime.sendMessage({ type: "OPEN_SIDEPANEL" });

      // ページデータを取得してバックグラウンドに送信
      const pageType = detectPageType();
      let data;
      if (pageType === "item_page") {
        data = extractItemPageData();
      } else if (pageType === "listing_hub") {
        data = extractListingHubData();
      } else {
        data = { pageType: "unknown" };
      }
      data.pageType = pageType;

      chrome.runtime.sendMessage({
        type: "PAGE_DATA",
        data,
      });
    });
  }

  // ============================================================
  // SEOスコアバッジの注入（出品一覧ページ用）
  // ============================================================

  function injectQuickScoreOnItemPage() {
    const pageType = detectPageType();
    if (pageType !== "item_page") return;

    const data = extractItemPageData();
    const score = quickScore(data);

    const titleEl = document.querySelector("h1.x-item-title__mainTitle, [data-testid='x-item-title']");
    if (!titleEl || titleEl.querySelector(".seo-quick-badge")) return;

    const badge = document.createElement("span");
    badge.className = "seo-quick-badge";
    badge.style.cssText = `
      display: inline-block;
      margin-left: 8px;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 12px;
      font-weight: 600;
      vertical-align: middle;
    `;

    if (score < 40) {
      badge.style.background = "#fef2f2";
      badge.style.color = "#dc2626";
    } else if (score < 70) {
      badge.style.background = "#fffbeb";
      badge.style.color = "#d97706";
    } else {
      badge.style.background = "#f0fdf4";
      badge.style.color = "#16a34a";
    }

    badge.textContent = `SEO: ${score}`;
    badge.title = `Title: ${data.titleLength}/80 chars | Photos: ${data.imageCount} | Specifics: ${Object.keys(data.specifics).length}`;
    titleEl.appendChild(badge);
  }

  // ============================================================
  // クイックスコア（Content Script内で即座に計算）
  // ============================================================

  function quickScore(data) {
    let score = 0;

    // タイトル（35点満点）
    const titleRatio = Math.min(data.titleLength / 80, 1);
    let titleScore = titleRatio * 100;
    if (data.titleLength === 0) titleScore = 0;
    if (/L@@K|WOW|!!!|LOOK/i.test(data.title)) titleScore -= 15;
    score += Math.max(0, titleScore) * 0.35;

    // 写真（15点満点）
    const photoScore = data.imageCount >= 5 ? 100 : (25 + data.imageCount * 15);
    score += Math.min(100, photoScore) * 0.15;

    // Item Specifics（25点満点）
    const specCount = Object.keys(data.specifics).length;
    let specScore = specCount >= 5 ? 100 : specCount >= 3 ? 70 : specCount >= 1 ? 40 : 0;
    score += specScore * 0.25;

    // 説明文（25点 - ページから判定困難なので中間値）
    score += 50 * 0.25;

    return Math.round(score);
  }

  // ============================================================
  // 初期化
  // ============================================================

  function init() {
    injectFloatingButton();
    // 少し待ってからスコアバッジを注入（DOMが完全に読み込まれるのを待つ）
    setTimeout(injectQuickScoreOnItemPage, 1500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
