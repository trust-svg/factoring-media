/**
 * service-worker.js — MV3 バックグラウンドサービスワーカー
 * メッセージハンドリング、ストレージ管理、ダッシュボード管理
 */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'SAVE_API_CONFIG':
      chrome.storage.local.set({ apiConfig: message.payload });
      break;

    case 'GET_API_CONFIG':
      chrome.storage.local.get(['apiConfig'], (data) => {
        sendResponse(data.apiConfig || { listApi: null, detailApi: null });
      });
      return true; // async response

    case 'SAVE_RESULTS':
      chrome.storage.local.set({
        collectedData: message.payload.data,
        collectionStatus: message.payload.status,
      });
      break;

    case 'GET_STATUS':
      chrome.storage.local.get(['collectionStatus'], (data) => {
        sendResponse(data.collectionStatus || {
          state: 'idle', current: 0, total: 0, errors: 0, lastRun: null,
        });
      });
      return true;

    case 'GET_RESULTS':
      chrome.storage.local.get(['collectedData', 'collectionStatus'], (data) => {
        sendResponse({
          data: data.collectedData || [],
          status: data.collectionStatus || { state: 'idle' },
        });
      });
      return true;

    case 'OPEN_DASHBOARD':
      chrome.tabs.create({
        url: chrome.runtime.getURL('dashboard/dashboard.html'),
      });
      break;

    case 'CLEAR_DATA':
      chrome.storage.local.remove(['apiConfig', 'collectedData', 'collectionStatus'], () => {
        sendResponse({ success: true });
      });
      return true;
  }
});
