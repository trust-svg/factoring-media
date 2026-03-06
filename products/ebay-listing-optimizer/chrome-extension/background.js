/**
 * eBay SEO Optimizer — Background Service Worker
 * FastAPIバックエンドとの通信を仲介する
 */

const API_BASE = "http://127.0.0.1:8080";

// 拡張アイコンクリック時にSide Panelを開く
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

// eBayページに移動した時にSide Panelを有効化
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tab.url && tab.url.includes("ebay.com")) {
    chrome.sidePanel.setOptions({
      tabId,
      path: "sidepanel/panel.html",
      enabled: true,
    });
  }
});

// Content ScriptやSide Panelからのメッセージを処理
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "API_REQUEST") {
    handleApiRequest(message)
      .then(sendResponse)
      .catch((err) => sendResponse({ error: err.message }));
    return true; // 非同期レスポンスを有効化
  }

  if (message.type === "PAGE_DATA") {
    // Content Scriptから取得したページデータをストレージに保存
    chrome.storage.local.set({ currentPageData: message.data });
    return;
  }
});

async function handleApiRequest({ method, path, body }) {
  const opts = {
    method: method || "GET",
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);

  try {
    const resp = await fetch(`${API_BASE}${path}`, opts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      return { error: err.detail || `HTTP ${resp.status}` };
    }
    return await resp.json();
  } catch (e) {
    return {
      error: `Backend not running. Start the server:\ncd products/ebay-listing-optimizer && python main.py`,
    };
  }
}
