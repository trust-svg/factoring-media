/**
 * interceptor.js — ページのメインワールドで実行
 * fetch/XHRをフックしてAPIエンドポイントを自動検出する
 */
(function () {
  'use strict';

  const LOG_PREFIX = '[CPASS Fee Viewer]';

  // 検出済みAPI設定
  const discovered = {
    listApi: null,
    detailApi: null,
  };

  // --- fetch フック ---
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    try {
      const req = args[0];
      const url = typeof req === 'string' ? req : req?.url || '';
      const init = args[1] || {};

      // リスト・詳細APIの検出
      if (url && shouldIntercept(url)) {
        console.log(LOG_PREFIX, 'fetch検出:', init.method || 'GET', url.substring(0, 120));
        const clone = response.clone();
        clone.json().then(data => {
          console.log(LOG_PREFIX, 'fetchレスポンスキー:', Object.keys(data));
          analyzeResponse(url, init, data);
        }).catch(() => { /* non-JSON response, ignore */ });
      }
    } catch (e) {
      console.warn(LOG_PREFIX, 'fetch intercept error:', e);
    }

    return response;
  };

  // --- XMLHttpRequest フック ---
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this._cpass_method = method;
    this._cpass_url = url;
    return originalOpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function (body) {
    this._cpass_body = body;

    this.addEventListener('load', function () {
      try {
        const url = this._cpass_url || '';
        if (url && shouldIntercept(url)) {
          console.log(LOG_PREFIX, 'XHR検出:', this._cpass_method, url.substring(0, 120));
          const data = JSON.parse(this.responseText);
          console.log(LOG_PREFIX, 'XHRレスポンスキー:', Object.keys(data));
          analyzeResponse(url, {
            method: this._cpass_method,
            body: this._cpass_body,
          }, data);
        }
      } catch (e) {
        console.log(LOG_PREFIX, 'XHR解析エラー:', this._cpass_url?.substring(0, 80), e.message);
      }
    });

    return originalSend.apply(this, [body]);
  };

  // --- 検出ロジック ---
  function shouldIntercept(url) {
    // OrangeConnex APIドメインのリクエストのみ対象
    return url.includes('orangeconnex.com') || url.startsWith('/');
  }

  function isExcludedUrl(url) {
    // マスタ系・設定系APIを除外
    const excludePatterns = [
      'select-box', 'price-type', 'config/', 'enum/',
      'dictionary/', 'i18n/', 'language/', 'translate/',
      'auth/', 'login/', 'token/', 'batch',
    ];
    const lower = url.toLowerCase();
    return excludePatterns.some(p => lower.includes(p));
  }

  function analyzeResponse(url, init, data) {
    // result: null のレスポンス（batchなど）はスキップ
    if (data && data.result === null && !data.data) return;

    // 非対象APIをスキップ（select-box, price-type等のマスタ系API）
    if (isExcludedUrl(url)) {
      console.log(LOG_PREFIX, '除外URL:', url.substring(0, 80));
      return;
    }

    // デバッグ: detailsList の有無を確認
    const _r = data.data || data.result || data;
    if (_r && typeof _r === 'object' && !Array.isArray(_r)) {
      console.log(LOG_PREFIX, 'analyzeResponse keys:', Object.keys(_r), 'detailsList?', Array.isArray(_r.detailsList), 'url:', url.substring(0, 100));
    }

    // リストAPIの検出: ページネーション構造を持つレスポンス
    if (isListResponse(data)) {
      const config = {
        url: normalizeUrl(url),
        method: (init.method || 'GET').toUpperCase(),
        headers: extractHeaders(init.headers),
        body: tryParseBody(init.body),
        pagination: extractPagination(data),
      };
      discovered.listApi = config;
      console.log(LOG_PREFIX, 'リストAPI検出:', config.url);
      console.log(LOG_PREFIX, 'リストAPI pagination:', JSON.stringify(config.pagination));
      emitEvent('cpass-list-api-discovered', config);
    }

    // 詳細APIの検出: 料金詳細を含むレスポンス
    if (isDetailResponse(data)) {
      // URL保存: クエリパラメータ付きのGETリクエストの場合、sellerId/languageは保持しorderNoは差し替え対象
      const fullUrl = normalizeUrl(url);
      const config = {
        url: fullUrl,
        method: (init.method || 'GET').toUpperCase(),
        headers: extractHeaders(init.headers),
        body: tryParseBody(init.body),
        sampleResponse: data,
      };
      discovered.detailApi = config;
      console.log(LOG_PREFIX, '詳細API検出:', config.url);
      console.log(LOG_PREFIX, '詳細API method:', config.method);
      emitEvent('cpass-detail-api-discovered', config);
    }
  }

  function isListResponse(data) {
    // ページネーション情報 + アイテム配列を持つレスポンスをリストAPIと判定
    if (!data || typeof data !== 'object') return false;

    const d = data.data || data.result || data;

    // total + records/list/items/data パターン
    const hasTotal = typeof (d.total ?? d.totalCount ?? d.totalElements) === 'number';
    const hasItems = Array.isArray(d.records || d.list || d.items || d.data || d.content);

    if (hasTotal && hasItems) {
      const items = d.records || d.list || d.items || d.data || d.content;
      // 注文番号を持つアイテムがあるか
      if (items.length > 0 && items[0]) {
        const sample = items[0];
        const hasOrderFields = sample.orderNo || sample.orderId || sample.orderNumber ||
          sample.trackingNo || sample.trackingNumber;
        return !!hasOrderFields;
      }
    }
    return false;
  }

  function isDetailResponse(data) {
    // 料金詳細を含むレスポンスを詳細APIと判定
    if (!data || typeof data !== 'object') return false;

    const d = data.data || data.result || data;

    // 実際の構造: result.feeDetailsList が配列で、feeType を含む
    const feeArray = d.feeDetailsList || d.detailsList || d.feeDetails || d.fees ||
      d.chargeDetails || d.feeList || d.chargeList;
    if (Array.isArray(feeArray) && feeArray.length > 0) {
      const sample = feeArray[0];
      if (sample.feeType || sample.feeName || sample.tradeAmount !== undefined) {
        console.log(LOG_PREFIX, '詳細API検出: feeDetailsList構造を確認');
        return true;
      }
    }

    return false;
  }

  function extractPagination(data) {
    const d = data.data || data.result || data;
    return {
      total: d.total ?? d.totalCount ?? d.totalElements ?? null,
      page: d.page ?? d.current ?? d.pageNum ?? d.pageNo ?? null,
      pageSize: d.pageSize ?? d.size ?? d.limit ?? null,
      pages: d.pages ?? d.totalPages ?? null,
    };
  }

  function extractHeaders(headers) {
    if (!headers) return {};
    if (headers instanceof Headers) {
      const obj = {};
      headers.forEach((v, k) => { obj[k] = v; });
      return obj;
    }
    if (Array.isArray(headers)) {
      return Object.fromEntries(headers);
    }
    return { ...headers };
  }

  function normalizeUrl(url) {
    if (url.startsWith('http')) return url;
    return window.location.origin + (url.startsWith('/') ? '' : '/') + url;
  }

  function tryParseBody(body) {
    if (!body) return null;
    if (typeof body === 'string') {
      try { return JSON.parse(body); } catch { return body; }
    }
    return body;
  }

  function emitEvent(eventName, detail) {
    window.dispatchEvent(new CustomEvent(eventName, {
      detail: JSON.parse(JSON.stringify(detail)), // structured clone safe
    }));
  }

  // --- ページワールド Fetch ブリッジ ---
  // コンテンツスクリプトからのfetchリクエストを代理実行する
  // （ページのセッションCookie/CORS コンテキストで実行されるため認証が通る）
  window.addEventListener('cpass-fetch-request', async (e) => {
    const { requestId, url, method, headers, body } = e.detail;
    try {
      const opts = {
        method: method || 'GET',
        headers: headers || {},
        credentials: 'include',
      };
      if (body && method !== 'GET') {
        opts.body = typeof body === 'object' ? JSON.stringify(body) : body;
        if (!opts.headers['Content-Type'] && !opts.headers['content-type']) {
          opts.headers['Content-Type'] = 'application/json';
        }
      }
      const res = await originalFetch(url, opts);
      const status = res.status;
      if (!res.ok) {
        emitEvent('cpass-fetch-response', { requestId, error: `HTTP_${status}`, status });
        return;
      }
      const data = await res.json();
      emitEvent('cpass-fetch-response', { requestId, data, status });
    } catch (err) {
      emitEvent('cpass-fetch-response', { requestId, error: err.message, status: 0 });
    }
  });

  console.log(LOG_PREFIX, 'Interceptor loaded - API自動検出 + Fetchブリッジ有効');
})();
