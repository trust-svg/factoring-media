/**
 * storage.js — chrome.storage.local ラッパー
 */
const Storage = {
  async get(key) {
    return new Promise(resolve => {
      chrome.storage.local.get([key], data => resolve(data[key]));
    });
  },

  async set(key, value) {
    return new Promise(resolve => {
      chrome.storage.local.set({ [key]: value }, resolve);
    });
  },

  async remove(key) {
    return new Promise(resolve => {
      chrome.storage.local.remove([key], resolve);
    });
  },

  // API設定
  async getApiConfig() {
    return (await this.get('apiConfig')) || { listApi: null, detailApi: null };
  },

  async saveApiConfig(config) {
    return this.set('apiConfig', config);
  },

  // 収集済みデータ
  async getCollectedData() {
    return (await this.get('collectedData')) || [];
  },

  async saveCollectedData(data) {
    return this.set('collectedData', data);
  },

  // 収集ステータス
  async getStatus() {
    return (await this.get('collectionStatus')) || {
      state: 'idle', // idle | collecting | done | error
      current: 0,
      total: 0,
      errors: 0,
      lastRun: null,
    };
  },

  async saveStatus(status) {
    return this.set('collectionStatus', status);
  },

  // 全データクリア
  async clearAll() {
    return new Promise(resolve => {
      chrome.storage.local.remove(['apiConfig', 'collectedData', 'collectionStatus'], resolve);
    });
  },
};
