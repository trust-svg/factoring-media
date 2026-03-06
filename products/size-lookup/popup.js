document.addEventListener("DOMContentLoaded", () => {
  const modelInput = document.getElementById("modelNumber");
  const searchBtn = document.getElementById("searchBtn");
  const loading = document.getElementById("loading");
  const results = document.getElementById("results");
  const errorBox = document.getElementById("error");
  const errorText = document.getElementById("errorText");
  const noApiKey = document.getElementById("noApiKey");
  const openOptions = document.getElementById("openOptions");
  const frequentSection = document.getElementById("frequentSection");
  const frequentList = document.getElementById("frequentList");
  const historySection = document.getElementById("historySection");
  const historyList = document.getElementById("historyList");
  const clearHistoryBtn = document.getElementById("clearHistory");

  // Check API key and restore last state on load
  chrome.storage.sync.get(["apiKey"], (data) => {
    if (!data.apiKey) {
      noApiKey.style.display = "block";
      searchBtn.disabled = true;
    }
  });

  restoreLastResult();
  renderFrequent();
  renderHistory();

  openOptions.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });

  searchBtn.addEventListener("click", () => search());
  modelInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") search();
  });

  clearHistoryBtn.addEventListener("click", async () => {
    await chrome.storage.local.set({ history: [], frequent: {} });
    renderHistory();
    renderFrequent();
  });

  async function search(query) {
    const modelNumber = query || modelInput.value.trim();
    if (!modelNumber) return;
    modelInput.value = modelNumber;

    const { apiKey, model } = await chrome.storage.sync.get(["apiKey", "model"]);
    if (!apiKey) {
      noApiKey.style.display = "block";
      return;
    }

    showLoading();

    try {
      const product = await fetchProductInfo(apiKey, model || "gemini-2.5-flash", modelNumber);
      // Verify HTS code against USITC official database
      const htsData = await lookupHTS(product);
      if (htsData) {
        product.hts_code = htsData.htsno;
        product.hs_code = htsData.htsno.replace(/\./g, "").substring(0, 6);
        product.hs_description = htsData.description;
        product.hts_source = "USITC";
      }
      const packaging = calculatePackaging(product);
      displayResults(product, packaging);
      await saveToHistory(modelNumber, product, packaging);
    } catch (err) {
      showError(err.message);
    }
  }

  async function fetchProductInfo(apiKey, model, modelNumber) {
    const prompt = `あなたは製品仕様のエキスパートです。製品の型番・商品名から、メーカー公式スペックに基づいた正確なサイズ・重量情報を提供してください。

型番/商品名: ${modelNumber}

以下のJSON形式で回答してください（JSONのみ、他のテキストは不要）：
{
  "product_name": "正式な製品名（日本語）",
  "brand": "メーカー名",
  "dimensions": {
    "length": 数値（cm、小数点1桁まで）,
    "width": 数値（cm、小数点1桁まで）,
    "height": 数値（cm、小数点1桁まで）
  },
  "weight_kg": 数値（kg、小数点2桁まで）,
  "fragility": 数値（1-5の整数）,
  "fragility_reason": "壊れやすさの理由（日本語、簡潔に）",
  "category": "製品カテゴリ（日本語）",
  "confidence": "high または medium または low",
  "hs_code": "HSコード（6桁、例: 851712）",
  "hts_code": "HTSコード（米国向け10桁、例: 8517.12.0050）",
  "hs_description": "HSコードの品目説明（日本語、簡潔に）",
  "notes": "梱包・発送時の注意点（日本語、なければ空文字）"
}

回答ルール：
- dimensionsは「製品本体のみ」のサイズ（外箱・パッケージは含めない）
- メーカー公式の仕様書に記載されている数値を優先すること
- 公式スペックが不明な場合は推定し、confidenceをmediumまたはlowに設定
- hs_codeは国際統一の6桁HSコード（Harmonized System）を記載
- hts_codeは米国向けHTS番号（Harmonized Tariff Schedule、8〜10桁）を記載
- 不明な場合は最も近い分類のコードを記載し、notesに「HS/HTSコードは税関で要確認」と追記

壊れやすさの基準：
1 = 非常に頑丈（金属工具、アウトドア用品）
2 = 普通（書籍、衣類、バッグ）
3 = やや壊れやすい（小型家電、フィギュア、キーボード）
4 = 壊れやすい（ガラス製品、精密機器、液晶画面付き、カメラ）
5 = 非常に壊れやすい（陶磁器、大型ディスプレイ、楽器）`;

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          responseMimeType: "application/json",
        },
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      if (response.status === 400) {
        throw new Error("APIキーが無効です。設定画面で正しいキーを入力してください。");
      }
      throw new Error(errData.error?.message || `API エラー (${response.status})`);
    }

    const data = await response.json();
    const text = data.candidates[0].content.parts[0].text.trim();

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      throw new Error("AIからの応答を解析できませんでした。もう一度お試しください。");
    }

    const product = JSON.parse(jsonMatch[0]);

    if (!product.dimensions || !product.dimensions.length) {
      throw new Error("商品サイズを取得できませんでした。別の型番で試してください。");
    }

    return product;
  }

  async function lookupHTS(product) {
    try {
      const aiHts = (product.hts_code || product.hs_code || "").replace(/\./g, "");
      const aiHeading = aiHts.substring(0, 4); // First 4 digits = heading

      if (!aiHeading || aiHeading.length < 4) return null;

      // Step 1: Search USITC by the AI-estimated heading number
      const res = await fetch(
        `https://hts.usitc.gov/reststop/search?keyword=${encodeURIComponent(aiHeading)}`
      );
      if (!res.ok) return null;

      const results = await res.json();
      if (!results || results.length === 0) return null;

      // Step 2: Only accept results whose HTS number starts with the same heading
      // This prevents unrelated codes from being returned
      const matching = results
        .filter((r) => {
          if (!r.htsno || !r.general) return false;
          const rClean = r.htsno.replace(/\./g, "");
          return rClean.startsWith(aiHeading);
        })
        .sort((a, b) => {
          // Prefer the result closest to the AI-estimated full code
          const aClean = a.htsno.replace(/\./g, "");
          const bClean = b.htsno.replace(/\./g, "");
          const aMatch = commonPrefixLen(aClean, aiHts);
          const bMatch = commonPrefixLen(bClean, aiHts);
          if (bMatch !== aMatch) return bMatch - aMatch;
          // If same prefix match, prefer more specific (longer) code
          return bClean.length - aClean.length;
        });

      if (matching.length > 0) return matching[0];

      return null;
    } catch {
      // USITC lookup is best-effort; don't block main flow
      return null;
    }
  }

  function commonPrefixLen(a, b) {
    let i = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) i++;
    return i;
  }

  function calculatePackaging(product) {
    const fragility = product.fragility || 3;
    const dims = product.dimensions;

    // Realistic padding per side (cm) based on fragility
    const paddingConfig = {
      1: { padding: 1, tips: ["薄手のエアキャップまたは新聞紙で包む", "隙間を軽く埋める"] },
      2: { padding: 2, tips: ["エアキャップ（プチプチ）で一重に包む", "隙間を新聞紙で埋める"] },
      3: { padding: 3, tips: ["エアキャップで二重に包む", "四隅に緩衝材を詰める", "「FRAGILE」ステッカーを貼る"] },
      4: { padding: 4, tips: ["エアキャップで二重以上に包む", "角をダンボール板で補強", "隙間を緩衝材で埋める", "「FRAGILE」と明記"] },
      5: { padding: 5, tips: ["二重箱で梱包（製品→内箱→緩衝材→外箱）", "エアキャップで三重に包む", "「FRAGILE / HANDLE WITH CARE」と明記", "輸送保険を推奨"] },
    };

    const config = paddingConfig[fragility] || paddingConfig[3];
    const padding = config.padding;

    const innerBox = {
      length: Math.ceil(dims.length + padding * 2),
      width: Math.ceil(dims.width + padding * 2),
      height: Math.ceil(dims.height + padding * 2),
    };

    // Double boxing only for level 5
    let outerBox = null;
    if (fragility >= 5) {
      outerBox = {
        length: innerBox.length + 6,
        width: innerBox.width + 6,
        height: innerBox.height + 6,
      };
    }

    const finalBox = outerBox || innerBox;

    // Volumetric weight (international standard divisor: 5000)
    const volumetricWeight = (finalBox.length * finalBox.width * finalBox.height) / 5000;

    // Estimated packaging material weight
    const packagingMaterialKg = fragility >= 4
      ? product.weight_kg * 0.15 + 0.3
      : product.weight_kg * 0.08 + 0.2;
    const actualWeight = product.weight_kg + packagingMaterialKg;

    const billableWeight = Math.max(volumetricWeight, actualWeight);

    return {
      padding,
      innerBox,
      outerBox,
      volumetricWeight: Math.round(volumetricWeight * 100) / 100,
      actualWeight: Math.round(actualWeight * 100) / 100,
      billableWeight: Math.round(billableWeight * 100) / 100,
      tips: config.tips,
    };
  }

  // --- Storage / History ---

  async function saveToHistory(query, product, packaging) {
    const data = await chrome.storage.local.get(["history", "frequent", "lastResult"]);
    const history = data.history || [];
    const frequent = data.frequent || {};

    const entry = {
      query,
      product_name: product.product_name,
      brand: product.brand,
      timestamp: Date.now(),
    };

    // Remove duplicate then prepend
    const filtered = history.filter((h) => h.query.toLowerCase() !== query.toLowerCase());
    filtered.unshift(entry);
    const trimmed = filtered.slice(0, 50);

    // Update frequency count
    const key = query.toLowerCase();
    frequent[key] = (frequent[key] || 0) + 1;

    await chrome.storage.local.set({
      history: trimmed,
      frequent,
      lastResult: { query, product, packaging },
    });

    renderHistory();
    renderFrequent();
  }

  async function restoreLastResult() {
    const data = await chrome.storage.local.get(["lastResult"]);
    if (data.lastResult) {
      const { query, product, packaging } = data.lastResult;
      modelInput.value = query;
      displayResults(product, packaging);
    }
  }

  async function renderFrequent() {
    const data = await chrome.storage.local.get(["frequent", "history"]);
    const frequent = data.frequent || {};
    const history = data.history || [];

    // Get top 5 most searched items (minimum 2 searches)
    const sorted = Object.entries(frequent)
      .filter(([, count]) => count >= 2)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);

    if (sorted.length === 0) {
      frequentSection.style.display = "none";
      return;
    }

    frequentSection.style.display = "block";
    frequentList.innerHTML = "";

    sorted.forEach(([key, count]) => {
      const original = history.find((h) => h.query.toLowerCase() === key);
      const displayName = original ? original.query : key;
      const tag = document.createElement("button");
      tag.className = "freq-tag";
      tag.textContent = displayName;
      tag.title = `${count}回検索`;
      tag.addEventListener("click", () => search(displayName));
      frequentList.appendChild(tag);
    });
  }

  async function renderHistory() {
    const data = await chrome.storage.local.get(["history"]);
    const history = data.history || [];

    if (history.length === 0) {
      historySection.style.display = "none";
      return;
    }

    historySection.style.display = "block";
    historyList.innerHTML = "";

    history.slice(0, 10).forEach((entry) => {
      const item = document.createElement("div");
      item.className = "history-item";
      item.innerHTML = `
        <span class="history-query">${escapeHtml(entry.query)}</span>
        <span class="history-name">${escapeHtml(entry.product_name || "")}</span>
      `;
      item.addEventListener("click", () => search(entry.query));
      historyList.appendChild(item);
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // --- Display ---

  function displayResults(product, packaging) {
    loading.style.display = "none";
    errorBox.style.display = "none";
    results.style.display = "block";

    document.getElementById("productName").textContent = product.product_name;
    document.getElementById("brand").textContent = product.brand;
    document.getElementById("category").textContent = product.category;
    document.getElementById("hsCode").textContent = product.hs_code || "-";
    document.getElementById("htsCode").textContent = product.hts_code || "-";
    const htsSrc = document.getElementById("htsSource");
    if (product.hts_source === "USITC") {
      htsSrc.textContent = "USITC公式";
      htsSrc.className = "source-badge official";
    } else {
      htsSrc.textContent = "AI推定";
      htsSrc.className = "source-badge ai";
    }
    // Strip HTML tags from USITC descriptions
    const rawDesc = product.hs_description || "";
    const cleanDesc = rawDesc.replace(/<[^>]*>/g, "").trim();
    document.getElementById("hsDesc").textContent = cleanDesc;
    document.getElementById("hsDescRow").style.display = cleanDesc ? "flex" : "none";

    const badge = document.getElementById("confidence");
    const confidenceLabels = { high: "高精度", medium: "推定", low: "低精度" };
    badge.textContent = confidenceLabels[product.confidence] || "推定";
    badge.className = `badge ${product.confidence || "medium"}`;

    document.getElementById("prodLength").textContent = product.dimensions.length;
    document.getElementById("prodWidth").textContent = product.dimensions.width;
    document.getElementById("prodHeight").textContent = product.dimensions.height;
    document.getElementById("weight").textContent = `${product.weight_kg} kg`;

    const levels = document.querySelectorAll(".fragility-level");
    levels.forEach((el) => {
      const level = parseInt(el.dataset.level);
      el.classList.toggle("active", level <= product.fragility);
    });
    document.getElementById("fragilityReason").textContent = product.fragility_reason;

    document.getElementById("boxLabel").textContent =
      packaging.outerBox ? "内箱サイズ" : "推奨ダンボールサイズ";
    document.getElementById("boxLength").textContent = packaging.innerBox.length;
    document.getElementById("boxWidth").textContent = packaging.innerBox.width;
    document.getElementById("boxHeight").textContent = packaging.innerBox.height;
    document.getElementById("paddingInfo").textContent =
      `各辺 ${packaging.padding}cm の緩衝材スペースを含む`;

    const outerSection = document.getElementById("outerBoxSection");
    if (packaging.outerBox) {
      outerSection.style.display = "block";
      document.getElementById("outerLength").textContent = packaging.outerBox.length;
      document.getElementById("outerWidth").textContent = packaging.outerBox.width;
      document.getElementById("outerHeight").textContent = packaging.outerBox.height;
    } else {
      outerSection.style.display = "none";
    }

    document.getElementById("volWeight").textContent = `${packaging.volumetricWeight} kg`;
    document.getElementById("actualWeight").textContent = `${packaging.actualWeight} kg`;
    document.getElementById("billableWeight").textContent = `${packaging.billableWeight} kg`;

    const tipsEl = document.getElementById("packingTips");
    tipsEl.innerHTML = `
      <h4>梱包のポイント</h4>
      <ul>${packaging.tips.map((t) => `<li>${t}</li>`).join("")}</ul>
    `;

    const notesSection = document.getElementById("notes");
    if (product.notes) {
      notesSection.style.display = "block";
      document.getElementById("notesText").textContent = product.notes;
    } else {
      notesSection.style.display = "none";
    }
  }

  function showLoading() {
    loading.style.display = "block";
    results.style.display = "none";
    errorBox.style.display = "none";
    noApiKey.style.display = "none";
    searchBtn.disabled = true;
    searchBtn.textContent = "検索中...";
    setTimeout(() => {
      searchBtn.disabled = false;
      searchBtn.textContent = "検索";
    }, 15000);
  }

  function showError(message) {
    loading.style.display = "none";
    results.style.display = "none";
    errorBox.style.display = "block";
    errorText.textContent = message;
    searchBtn.disabled = false;
    searchBtn.textContent = "検索";
  }
});
