/**
 * content.js — メインコンテンツスクリプト
 * API検出、データ収集、UI注入、DOMフォールバックを統括
 */
(function () {
  'use strict';

  const LOG = '[CPASS Fee Viewer]';
  const TARGET_PATH = '/transactionDetails';

  let apiConfig = { listApi: null, detailApi: null };
  let isCollecting = false;

  // --- 初期化 ---
  function init() {
    injectInterceptor();
    listenForApiDiscovery();
    observeNavigation();
    checkCurrentPage();
  }

  // --- Interceptor注入 ---
  function injectInterceptor() {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('content/interceptor.js');
    script.onload = () => script.remove();
    (document.head || document.documentElement).appendChild(script);
  }

  // --- API検出リスナー ---
  function listenForApiDiscovery() {
    window.addEventListener('cpass-list-api-discovered', (e) => {
      apiConfig.listApi = e.detail;
      console.log(LOG, 'リストAPI検出:', apiConfig.listApi.url);
      saveApiConfig();
      checkReady();
    });

    window.addEventListener('cpass-detail-api-discovered', (e) => {
      apiConfig.detailApi = e.detail;
      console.log(LOG, '詳細API検出:', apiConfig.detailApi.url);
      saveApiConfig();
      checkReady();
    });
  }

  function saveApiConfig() {
    chrome.runtime.sendMessage({
      type: 'SAVE_API_CONFIG',
      payload: apiConfig,
    });
  }

  function checkReady() {
    if (apiConfig.detailApi && typeof CpassUI !== 'undefined' && CpassUI.panel) {
      CpassUI.onApiReady();
    }
  }

  // --- SPA ナビゲーション監視 ---
  function observeNavigation() {
    let lastPath = location.pathname + location.hash;
    const check = () => {
      const currentPath = location.pathname + location.hash;
      if (currentPath !== lastPath) {
        lastPath = currentPath;
        checkCurrentPage();
      }
    };

    window.addEventListener('popstate', check);
    window.addEventListener('hashchange', check);

    // pushState/replaceStateフック
    const origPush = history.pushState;
    const origReplace = history.replaceState;
    history.pushState = function () { origPush.apply(this, arguments); check(); };
    history.replaceState = function () { origReplace.apply(this, arguments); check(); };

    // MutationObserverでURL変更も監視
    new MutationObserver(check).observe(document.body, { childList: true, subtree: true });
  }

  function checkCurrentPage() {
    const isTargetPage = location.pathname.includes(TARGET_PATH) ||
      location.hash.includes(TARGET_PATH);

    if (isTargetPage) {
      loadUIAndSetup();
    } else if (typeof CpassUI !== 'undefined') {
      CpassUI.remove();
    }
  }

  // --- UI読み込み・セットアップ ---
  function loadUIAndSetup() {
    // ui.jsをページに注入（content script内で実行）
    if (typeof CpassUI === 'undefined') {
      // ui.jsを動的に読み込み
      const script = document.createElement('script');
      script.src = chrome.runtime.getURL('content/ui.js');
      script.onload = () => {
        script.remove();
        setupUI();
      };
      (document.head || document.documentElement).appendChild(script);
    } else {
      setupUI();
    }
  }

  // ui.jsはcontent script worldでも参照可能にするため、inlineで定義
  // manifest.jsonのcontent_scriptsには含めない方式を取る場合の代替:
  // ここでは直接CpassUIをcontent world内に持つ
  // → 実際にはui.jsのコードをここに統合する方がMV3では安定

  // --- UI統合版 ---
  const CpassUI = {
    panel: null,
    state: 'idle',
    onStart: null,
    onDashboard: null,

    inject() {
      if (this.panel) return;

      this.panel = document.createElement('div');
      this.panel.className = 'cpass-fv-panel';
      this.panel.innerHTML = `
        <div class="cpass-fv-header">
          <span class="cpass-fv-title">CPASS Fee Viewer</span>
          <button class="cpass-fv-minimize" title="最小化">_</button>
        </div>
        <div class="cpass-fv-body">
          <div class="cpass-fv-status">
            <span class="cpass-fv-status-dot idle"></span>
            <span class="cpass-fv-status-text">API検出待ち...</span>
          </div>
          <div class="cpass-fv-hint">
            いずれかの行の「詳細」をクリックしてAPIを検出してください。
          </div>
          <div class="cpass-fv-progress" style="display:none">
            <div class="cpass-fv-progress-bar">
              <div class="cpass-fv-progress-fill"></div>
            </div>
            <div class="cpass-fv-progress-text">0 / 0</div>
          </div>
          <div class="cpass-fv-error" style="display:none"></div>
          <div class="cpass-fv-actions">
            <button class="cpass-fv-btn cpass-fv-btn-primary cpass-fv-start" disabled>一括取得</button>
            <button class="cpass-fv-btn cpass-fv-btn-secondary cpass-fv-dashboard" disabled>結果を表示</button>
          </div>
        </div>
      `;

      document.body.appendChild(this.panel);

      this.panel.querySelector('.cpass-fv-minimize').addEventListener('click', () => {
        this.panel.classList.toggle('minimized');
      });
      this.panel.querySelector('.cpass-fv-start').addEventListener('click', () => {
        if (this.onStart) this.onStart();
      });
      this.panel.querySelector('.cpass-fv-dashboard').addEventListener('click', () => {
        if (this.onDashboard) this.onDashboard();
      });
    },

    setStatus(state, text) {
      if (!this.panel) return;
      this.state = state;
      this.panel.querySelector('.cpass-fv-status-dot').className = `cpass-fv-status-dot ${state}`;
      this.panel.querySelector('.cpass-fv-status-text').textContent = text;
      const hint = this.panel.querySelector('.cpass-fv-hint');
      hint.style.display = state === 'idle' ? '' : 'none';
    },

    onApiReady() {
      this.setStatus('ready', 'API検出完了 - 取得可能');
      this.panel.querySelector('.cpass-fv-start').disabled = false;
    },

    startCollecting() {
      this.setStatus('collecting', '取得中...');
      this.panel.querySelector('.cpass-fv-start').disabled = true;
      this.panel.querySelector('.cpass-fv-progress').style.display = '';
      this.panel.querySelector('.cpass-fv-error').style.display = 'none';
    },

    updateProgress(current, total) {
      if (!this.panel) return;
      const pct = total > 0 ? (current / total * 100) : 0;
      this.panel.querySelector('.cpass-fv-progress-fill').style.width = `${pct}%`;
      this.panel.querySelector('.cpass-fv-progress-text').textContent = `${current} / ${total}`;
      this.panel.querySelector('.cpass-fv-status-text').textContent = `取得中... ${current}/${total}`;
    },

    onComplete(count, errors) {
      const text = errors > 0
        ? `完了 (${count}件取得, ${errors}件エラー)`
        : `完了 (${count}件取得)`;
      this.setStatus('done', text);
      this.panel.querySelector('.cpass-fv-start').disabled = false;
      this.panel.querySelector('.cpass-fv-start').textContent = '再取得';
      this.panel.querySelector('.cpass-fv-dashboard').disabled = false;
    },

    showError(message) {
      if (!this.panel) return;
      this.setStatus('error', 'エラー発生');
      const errorEl = this.panel.querySelector('.cpass-fv-error');
      errorEl.style.display = '';
      errorEl.textContent = message;
      this.panel.querySelector('.cpass-fv-start').disabled = false;
    },

    remove() {
      if (this.panel) { this.panel.remove(); this.panel = null; }
    },
  };

  function setupUI() {
    CpassUI.inject();

    // 保存済みAPI設定を復元
    chrome.runtime.sendMessage({ type: 'GET_API_CONFIG' }, (config) => {
      if (config && config.detailApi) {
        apiConfig = config;
        CpassUI.onApiReady();
      }
    });

    // 前回の結果があるか確認
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (status) => {
      if (status && status.state === 'done') {
        CpassUI.onComplete(status.current, status.errors);
      }
    });

    CpassUI.onStart = startCollection;
    CpassUI.onDashboard = openDashboard;
  }

  // --- データ収集 ---
  async function startCollection() {
    if (isCollecting) return;
    isCollecting = true;
    CpassUI.startCollecting();

    try {
      if (apiConfig.listApi && apiConfig.detailApi) {
        await collectViaApi();
      } else if (apiConfig.detailApi) {
        // リストAPIがない場合: DOMからオーダーIDを取得 + APIで詳細取得
        await collectHybrid();
      } else {
        // 両方ない場合: 完全DOMスクレイピング
        await collectViaDom();
      }
    } catch (err) {
      console.error(LOG, 'Collection error:', err);
      if (err.message === 'AUTH_EXPIRED') {
        CpassUI.showError('セッションが切れました。ページを再読み込みしてログインし直してください。');
      } else {
        CpassUI.showError(`エラー: ${err.message}`);
      }
    } finally {
      isCollecting = false;
    }
  }

  // --- 方式1: API一括取得 ---
  async function collectViaApi() {
    console.log(LOG, 'API方式で一括取得開始');

    // 1. リストAPIで全注文を取得
    CpassUI.setStatus('collecting', 'リスト取得中...');
    const allOrders = await fetchAllOrders();
    const total = allOrders.length;
    console.log(LOG, `全${total}件の注文を取得`);

    // デバッグ: 最初のアイテムの全フィールドを表示
    if (allOrders.length > 0) {
      console.log(LOG, '最初のリストアイテムのキー:', Object.keys(allOrders[0]));
      console.log(LOG, '最初のリストアイテム:', JSON.stringify(allOrders[0]).substring(0, 500));
    }

    // 2. 各注文の詳細を取得
    const results = [];
    let errors = 0;
    const BATCH = 5;
    let delay = 300;

    for (let i = 0; i < total; i += BATCH) {
      const batch = allOrders.slice(i, i + BATCH);
      const promises = batch.map(order => {
        // 様々なフィールド名に対応
        const orderId = order.orderNo || order.orderId || order.orderNumber ||
          order.billNo || order.waybillNo || order.trackingNo || order.id;
        if (i === 0) console.log(LOG, 'orderフィールド探索:', { orderNo: order.orderNo, orderId: order.orderId, orderNumber: order.orderNumber, billNo: order.billNo, id: order.id });
        return fetchDetail(orderId)
          .then(data => {
            if (i < BATCH) console.log(LOG, `詳細取得成功 [${orderId}]`);
            return { success: true, orderId, data, listItem: order };
          })
          .catch(err => {
            console.error(LOG, `詳細取得エラー [${orderId}]:`, err.message);
            return { success: false, orderId, error: err.message };
          });
      });

      const batchResults = await Promise.all(promises);

      for (const r of batchResults) {
        if (r.success) {
          console.log(LOG, `詳細レスポンス [${r.orderId}]:`, JSON.stringify(r.data).substring(0, 300));
          const normalized = normalizeDetail(r.data, r.listItem);
          console.log(LOG, `正規化結果 [${normalized.orderId}]: 合計=${normalized.totalAmount}, 送料系=${normalized.shippingTotal}, 関税系=${normalized.customsTotal}, 確定=${normalized.confirmed}`);
          results.push(normalized);
        } else {
          errors++;
          console.warn(LOG, `詳細取得失敗 [${r.orderId}]:`, r.error);
          if (r.error === 'AUTH_EXPIRED') throw new Error('AUTH_EXPIRED');
        }
      }

      CpassUI.updateProgress(Math.min(i + BATCH, total), total);

      // レート制限対応
      if (batchResults.some(r => !r.success && r.error === '429')) {
        delay = Math.min(delay * 2, 5000);
      }
      if (i + BATCH < total) {
        await sleep(delay);
      }
    }

    await saveResults(results, errors);
  }

  // --- 方式2: ハイブリッド（DOMリスト + API詳細） ---
  async function collectHybrid() {
    console.log(LOG, 'ハイブリッド方式で取得開始');
    const orderIds = scrapeOrderIdsFromDom();
    const total = orderIds.length;

    if (total === 0) {
      CpassUI.showError('一覧からデータを取得できませんでした。');
      return;
    }

    const results = [];
    let errors = 0;
    const BATCH = 5;

    for (let i = 0; i < total; i += BATCH) {
      const batch = orderIds.slice(i, i + BATCH);
      const promises = batch.map(id =>
        fetchDetail(id)
          .then(data => ({ success: true, data }))
          .catch(err => ({ success: false, error: err.message }))
      );

      const batchResults = await Promise.all(promises);
      for (const r of batchResults) {
        if (r.success) results.push(normalizeDetail(r.data, null));
        else errors++;
      }

      CpassUI.updateProgress(Math.min(i + BATCH, total), total);
      if (i + BATCH < total) await sleep(300);
    }

    await saveResults(results, errors);
  }

  // --- 方式3: 完全DOMスクレイピング ---
  async function collectViaDom() {
    console.log(LOG, 'DOMスクレイピング方式で取得開始');
    CpassUI.setStatus('collecting', 'DOMスクレイピング中...');

    const results = [];
    let errors = 0;
    let pageNum = 1;
    let totalProcessed = 0;

    // 総件数を推定（ページネーション表示から）
    const totalEstimate = estimateTotalFromDom();

    while (true) {
      // 現在のページの行を取得
      const rows = getTableRows();
      if (rows.length === 0) break;

      for (let i = 0; i < rows.length; i++) {
        try {
          const data = await scrapeDetailFromRow(rows[i]);
          if (data) results.push(data);
          else errors++;
        } catch (e) {
          console.warn(LOG, 'Row scrape error:', e);
          errors++;
        }
        totalProcessed++;
        CpassUI.updateProgress(totalProcessed, totalEstimate || totalProcessed);
        await sleep(500); // モーダルのアニメーション待ち
      }

      // 次のページへ
      const hasNext = goToNextPage();
      if (!hasNext) break;
      pageNum++;
      await sleep(1000); // ページ遷移待ち
    }

    await saveResults(results, errors);
  }

  // --- API呼び出しヘルパー ---
  async function fetchAllOrders() {
    const cfg = apiConfig.listApi;
    const allItems = [];
    const pageSize = cfg.pagination?.pageSize || 10;
    const totalPages = cfg.pagination?.pages ||
      Math.ceil((cfg.pagination?.total || 0) / pageSize);

    for (let page = 1; page <= Math.max(totalPages, 1); page++) {
      let url = cfg.url;
      let body = cfg.body;

      if (cfg.method === 'GET') {
        // GETの場合: URLのクエリパラメータでページネーション
        url = buildPageUrl(cfg.url, page, pageSize);
      } else {
        // POSTの場合: bodyでページネーション
        body = buildPageBody(cfg.body, page, pageSize);
      }

      const data = await fetchWithRetry(url, cfg.method, cfg.headers, body);
      const d = data.data || data.result || data;
      const items = d.records || d.list || d.items || d.data || d.content || [];
      allItems.push(...items);
      CpassUI.setStatus('collecting', `リスト取得中... ページ${page}/${totalPages}`);
    }

    return allItems;
  }

  async function fetchDetail(orderNo) {
    const cfg = apiConfig.detailApi;
    // 実際のAPI: details?sellerId=XXX&language=ja-jp&orderNo=YYY (GET, クエリパラメータ)
    const url = buildDetailUrl(cfg.url, orderNo);
    console.log(LOG, '詳細取得:', orderNo, url);
    return fetchWithRetry(url, cfg.method, cfg.headers, null);
  }

  // --- ページワールド Fetch ブリッジ ---
  // interceptor.js（ページのメインワールド）経由でfetchを実行
  // ページのセッションCookie/CORSコンテキストが使われるため認証が通る
  let _fetchReqId = 0;
  const _fetchCallbacks = new Map();

  // レスポンスリスナー（一度だけ登録）
  window.addEventListener('cpass-fetch-response', (e) => {
    const { requestId, data, error, status } = e.detail;
    const cb = _fetchCallbacks.get(requestId);
    if (cb) {
      _fetchCallbacks.delete(requestId);
      if (error) {
        cb.reject(new Error(error));
      } else {
        cb.resolve(data);
      }
    }
  });

  function pageWorldFetch(url, method, headers, body) {
    return new Promise((resolve, reject) => {
      const requestId = `req_${++_fetchReqId}_${Date.now()}`;
      _fetchCallbacks.set(requestId, { resolve, reject });

      // タイムアウト（30秒）
      setTimeout(() => {
        if (_fetchCallbacks.has(requestId)) {
          _fetchCallbacks.delete(requestId);
          reject(new Error('TIMEOUT'));
        }
      }, 30000);

      window.dispatchEvent(new CustomEvent('cpass-fetch-request', {
        detail: { requestId, url, method, headers, body },
      }));
    });
  }

  async function fetchWithRetry(url, method, headers, body, retries = 3) {
    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const data = await pageWorldFetch(url, method || 'GET', headers, body);
        return data;
      } catch (e) {
        console.warn(LOG, `fetch失敗 (attempt ${attempt + 1}/${retries}):`, url.substring(0, 80), e.message);
        if (e.message === 'HTTP_401' || e.message === 'HTTP_403') throw new Error('AUTH_EXPIRED');
        if (e.message === 'AUTH_EXPIRED') throw e;
        if (attempt === retries - 1) throw e;
        await sleep(1000 * Math.pow(2, attempt));
      }
    }
  }

  // --- DOMスクレイピングヘルパー ---
  function scrapeOrderIdsFromDom() {
    const rows = getTableRows();
    const ids = [];
    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      if (cells.length >= 2) {
        const orderId = cells[1]?.textContent?.trim();
        if (orderId) ids.push(orderId);
      }
    }
    return ids;
  }

  function getTableRows() {
    // Ant Design / Element UI テーブルの行を取得
    const selectors = [
      '.ant-table-tbody tr',
      '.el-table__body-wrapper tr',
      'table tbody tr',
      '[class*="table"] tbody tr',
    ];
    for (const sel of selectors) {
      const rows = document.querySelectorAll(sel);
      if (rows.length > 0) return Array.from(rows);
    }
    return [];
  }

  async function scrapeDetailFromRow(row) {
    // 「詳細」リンクを探してクリック
    const detailBtn = row.querySelector('a, button, [class*="detail"], [class*="link"]');
    if (!detailBtn) return null;

    detailBtn.click();

    // モーダルが表示されるまで待機
    const modal = await waitForElement(
      '.ant-modal, .el-dialog, [class*="modal"], [class*="dialog"]',
      5000
    );
    if (!modal) return null;

    await sleep(300); // レンダリング待ち

    try {
      return scrapeModal(modal);
    } finally {
      // モーダルを閉じる
      const closeBtn = modal.querySelector(
        '.ant-modal-close, .el-dialog__close, [class*="close"], button[aria-label="Close"]'
      );
      if (closeBtn) closeBtn.click();
      await sleep(300);
    }
  }

  function scrapeModal(modal) {
    const text = modal.textContent || '';
    const record = {
      orderId: '',
      date: '',
      carrier: '',
      trackingNumber: '',
      destination: '',
      packageType: '',
      totalAmount: 0,
      fees: { shipping: 0, fuelSurcharge: 0, customsDuty: 0, customsProcessing: 0, other: 0 },
      skus: [],
    };

    // モーダルのテーブル行から料金を抽出
    const rows = modal.querySelectorAll('tr, [class*="row"]');
    for (const row of rows) {
      const cells = row.querySelectorAll('td, [class*="cell"], span');
      if (cells.length < 2) continue;

      const label = (cells[0]?.textContent || '').trim();
      const value = (cells[1]?.textContent || '').trim();

      if (label.includes('運送料金') || label.includes('運送')) {
        record.fees.shipping = parseJPY(value);
      } else if (label.includes('燃料') || label.includes('割増')) {
        record.fees.fuelSurcharge = parseJPY(value);
      } else if (label.includes('関税処理') || label.includes('手数料')) {
        record.fees.customsProcessing = parseJPY(value);
      } else if (label.includes('関税') || label.includes('税金')) {
        record.fees.customsDuty = parseJPY(value);
      } else if (label.includes('合計')) {
        record.totalAmount = parseJPY(value);
      }
    }

    // 注文番号を抽出
    const orderMatch = text.match(/EM\d{10,}[A-Z0-9]*/);
    if (orderMatch) record.orderId = orderMatch[0];

    // キャリア情報
    if (text.includes('FedEx')) record.carrier = 'FedEx';
    else if (text.includes('DHL')) record.carrier = 'DHL';
    else if (text.includes('UPS')) record.carrier = 'UPS';

    // 送付先
    const destMatch = text.match(/(?:お届け先|送付先)[：:]\s*(\w+)/);
    if (destMatch) record.destination = destMatch[1];

    // 合計がなければ料金を合算
    if (!record.totalAmount) {
      record.totalAmount = record.fees.shipping + record.fees.fuelSurcharge +
        record.fees.customsDuty + record.fees.customsProcessing + record.fees.other;
    }

    return record;
  }

  function estimateTotalFromDom() {
    const paginationText = document.querySelector(
      '.ant-pagination-total-text, [class*="pagination"] [class*="total"], [class*="total"]'
    );
    if (paginationText) {
      const match = paginationText.textContent.match(/(\d+)/);
      if (match) return parseInt(match[1], 10);
    }
    return 0;
  }

  function goToNextPage() {
    const nextBtn = document.querySelector(
      '.ant-pagination-next:not(.ant-pagination-disabled), ' +
      '.el-pagination .btn-next:not(:disabled), ' +
      '[class*="pagination"] [class*="next"]:not([disabled])'
    );
    if (nextBtn) {
      nextBtn.click();
      return true;
    }
    return false;
  }

  // --- データ正規化 ---
  // 実際のAPIレスポンス構造:
  // {
  //   "responseVersion": "rv_v1.0",
  //   "requestId": null,
  //   "success": true,
  //   "result": {
  //     "detailsList": [
  //       {
  //         "feeType": "燃料割増金",
  //         "amount": "+1,901",
  //         "tradeAmount": 1901.00,
  //         "modifyTime": "2026-02-26 16:42:03",
  //         "orderNo": "EM1013087787702FE...",
  //         "tradeTotalCs": 1770981XXXXX,
  //         "bizType": 1,
  //         ...
  //       },
  //       ...
  //     ],
  //     "forceTotalAmount": "14,428",
  //     ...
  //   }
  // }
  function normalizeDetail(raw, listItem) {
    // result直下にfeeDetailsListがある
    const resultObj = raw.result || raw.data || raw;
    // SKUデバッグ: 最初の1件だけ詳細ログ
    const _skuArr = resultObj.skuDetailsList;
    if (Array.isArray(_skuArr) && _skuArr.length > 0) {
      const _keys = Object.keys(_skuArr[0]);
      console.log(LOG, '=== SKUデバッグ ===');
      console.log(LOG, 'SKUキー一覧:', _keys.join(', '));
      console.log(LOG, 'SKU全データ:', JSON.stringify(_skuArr[0]).substring(0, 600));
      // 各フィールドの値を個別に出力
      for (const k of _keys) {
        console.log(LOG, `  SKU[${k}] =`, _skuArr[0][k]);
      }
    } else {
      console.log(LOG, 'SKUなし: skuDetailsList=', _skuArr);
    }
    const feeArray = resultObj.feeDetailsList || resultObj.detailsList || resultObj.feeDetails || resultObj.fees || [];

    // 全料金項目を動的に収集
    const feeItems = [];
    let orderNo = '';
    let modifyTime = '';
    let hasUnconfirmed = false;

    for (const fee of feeArray) {
      const feeType = (fee.feeType || fee.feeName || fee.name || '');
      const amount = typeof fee.tradeAmount === 'number'
        ? Math.round(fee.tradeAmount)
        : parseJPY(fee.amount || 0);

      if (!orderNo && fee.orderNo) orderNo = fee.orderNo;
      if (!modifyTime && fee.modifyTime) modifyTime = fee.modifyTime;

      // 「推定」を含む → 未確定、含まない → 確定
      const confirmed = !feeType.includes('推定');
      if (!confirmed) hasUnconfirmed = true;

      // カテゴリ: 送料系 or 関税系
      const category = categorizeFee(feeType);

      feeItems.push({ feeType, amount, confirmed, category });
    }

    const shippingTotal = feeItems.filter(f => f.category === 'shipping').reduce((s, f) => s + f.amount, 0);
    const customsTotal = feeItems.filter(f => f.category === 'customs').reduce((s, f) => s + f.amount, 0);
    const totalAmount = feeItems.reduce((s, f) => s + f.amount, 0);

    const forcedTotal = parseJPY(resultObj.forceTotalAmount || resultObj.totalFeeAmount || 0);

    // SKU情報を取得（フィールド名が不明なため広範囲に探索）
    const skuArray = resultObj.skuDetailsList || [];
    const skus = skuArray.map(s => {
      // 商品名: 多数の候補フィールドを試行
      const descCandidates = [
        'description', 'productName', 'skuName', 'skuDesc', 'skuDescription',
        'goodsName', 'goodsDesc', 'commodityName', 'itemTitle', 'itemName',
        'productDesc', 'productTitle', 'title', 'name', 'goodsTitle',
        'skuTitle', 'commodityDesc', 'declareName', 'declareNameCn',
        'declareNameEn', 'enName', 'cnName', 'jaName',
      ];
      let desc = '';
      for (const key of descCandidates) {
        if (s[key] && typeof s[key] === 'string' && s[key].trim()) {
          desc = s[key].trim();
          break;
        }
      }
      // フォールバック: 既知のキー以外で最初の非空文字列フィールドを使用
      if (!desc) {
        const skipKeys = new Set(['orderNo', 'carrierName', 'carrierTrackingNo', 'destination',
          'carrierPackageType', 'id', 'sellerId', 'modifyTime', 'createTime', 'status',
          'bizType', 'language', 'currency']);
        for (const [k, v] of Object.entries(s)) {
          if (!skipKeys.has(k) && typeof v === 'string' && v.trim() && v.length > 2) {
            desc = v.trim();
            console.log(LOG, `SKU商品名をフォールバックで検出: フィールド="${k}", 値="${desc}"`);
            break;
          }
        }
      }
      return {
        ebayTxId: s.ebayTxId || s.txId || s.transactionId || s.ebayTransactionId || '',
        description: desc,
        hsCode: s.hsCode || s.hscode || s.hsCode || '',
      };
    });

    return {
      orderId: orderNo || resultObj.orderNo || listItem?.orderNo || '',
      date: modifyTime || listItem?.createTimeJp || listItem?.createTime || resultObj.createTime || '',
      carrier: resultObj.carrierName || listItem?.serviceFullName || listItem?.carrier || listItem?.carrierName || '',
      trackingNumber: resultObj.carrierTrackingNo || listItem?.trackingNo || listItem?.waybillNo || '',
      destination: resultObj.destination || listItem?.destinationCountry || listItem?.destination || listItem?.country || '',
      packageType: resultObj.carrierPackageType || listItem?.packageTypeStr || listItem?.packageType || '',
      totalAmount: totalAmount || forcedTotal,
      shippingTotal,
      customsTotal,
      confirmed: !hasUnconfirmed,
      feeItems,
      skus,
    };
  }

  // --- 結果保存 ---
  async function saveResults(results, errors) {
    // 重複除去
    const unique = new Map();
    for (const r of results) {
      if (r.orderId) unique.set(r.orderId, r);
    }
    const deduped = Array.from(unique.values());

    chrome.runtime.sendMessage({
      type: 'SAVE_RESULTS',
      payload: {
        data: deduped,
        status: {
          state: 'done',
          current: deduped.length,
          total: deduped.length + errors,
          errors,
          lastRun: new Date().toISOString(),
        },
      },
    });

    CpassUI.onComplete(deduped.length, errors);
    console.log(LOG, `完了: ${deduped.length}件取得, ${errors}件エラー`);
  }

  // --- ダッシュボード ---
  function openDashboard() {
    chrome.runtime.sendMessage({ type: 'OPEN_DASHBOARD' });
  }

  // --- ユーティリティ ---
  function buildPageBody(original, page, pageSize) {
    if (!original || typeof original !== 'object') return original;
    const body = { ...original };
    for (const k of ['page', 'current', 'pageNum', 'pageNo']) { if (k in body) { body[k] = page; break; } }
    for (const k of ['pageSize', 'size', 'limit']) { if (k in body) { body[k] = pageSize; break; } }
    return body;
  }

  function buildDetailUrl(urlTemplate, orderNo) {
    // 実際のAPI形式: https://...details/v1?sellerId=XXX&language=ja-jp&orderNo=YYY
    try {
      const url = new URL(urlTemplate);
      // orderNoパラメータを差し替え（既存なら上書き、なければ追加）
      url.searchParams.set('orderNo', orderNo);
      return url.toString();
    } catch {
      // URLパース失敗時はクエリパラメータを手動で差し替え
      if (urlTemplate.includes('orderNo=')) {
        return urlTemplate.replace(/orderNo=[^&]*/, `orderNo=${encodeURIComponent(orderNo)}`);
      }
      const sep = urlTemplate.includes('?') ? '&' : '?';
      return `${urlTemplate}${sep}orderNo=${encodeURIComponent(orderNo)}`;
    }
  }

  function buildPageUrl(urlTemplate, page, pageSize) {
    // GETリクエストのURL内のページパラメータを差し替え
    try {
      const url = new URL(urlTemplate);
      url.searchParams.set('page', page);
      if (pageSize) url.searchParams.set('limit', pageSize);
      return url.toString();
    } catch {
      let u = urlTemplate;
      u = u.replace(/page=\d+/, `page=${page}`);
      if (pageSize) u = u.replace(/limit=\d+/, `limit=${pageSize}`);
      return u;
    }
  }

  function parseJPY(text) {
    if (typeof text === 'number') return text;
    if (!text) return 0;
    return parseInt(String(text).replace(/[^0-9\-+.]/g, ''), 10) || 0;
  }

  function categorizeFee(feeType) {
    // 明示的に送料系に分類する項目（「手数料」を含むが送料系）
    const shippingExact = [
      '遠隔地集荷手数料による差異調整',
      '遠隔地配達手数料',
      '規制手数料による調整',
    ];
    if (shippingExact.some(kw => feeType.includes(kw))) return 'shipping';

    const lower = feeType.toLowerCase();
    const customsKw = ['関税', '税金', '手数料', 'customs', 'duty', 'tax'];
    if (customsKw.some(kw => lower.includes(kw))) return 'customs';
    return 'shipping';
  }

  function matchKw(text, keywords) {
    return keywords.some(kw => text.includes(kw));
  }

  function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  function waitForElement(selector, timeout = 5000) {
    return new Promise(resolve => {
      const existing = document.querySelector(selector);
      if (existing) { resolve(existing); return; }

      const timer = setTimeout(() => { observer.disconnect(); resolve(null); }, timeout);
      const observer = new MutationObserver(() => {
        const el = document.querySelector(selector);
        if (el) { clearTimeout(timer); observer.disconnect(); resolve(el); }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }

  // --- 起動 ---
  init();
})();
