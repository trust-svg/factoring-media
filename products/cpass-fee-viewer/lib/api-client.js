/**
 * api-client.js — リトライ付きAPI呼び出し
 */
const ApiClient = {
  /**
   * リストAPIで全注文を取得
   */
  async fetchAllOrders(listApiConfig) {
    const allItems = [];
    const { pagination } = listApiConfig;
    const totalPages = pagination.pages ||
      Math.ceil((pagination.total || 0) / (pagination.pageSize || 10));

    for (let page = 1; page <= totalPages; page++) {
      const data = await this._fetchWithRetry(
        listApiConfig.url,
        listApiConfig.method,
        listApiConfig.headers,
        this._buildPageBody(listApiConfig.body, page, pagination.pageSize || 10)
      );
      const d = data.data || data.result || data;
      const items = d.records || d.list || d.items || d.data || d.content || [];
      allItems.push(...items);
    }

    return allItems;
  },

  /**
   * 詳細APIで1件の料金詳細を取得
   */
  async fetchDetail(detailApiConfig, orderId) {
    const url = this._buildDetailUrl(detailApiConfig.url, orderId);
    const body = this._buildDetailBody(detailApiConfig.body, orderId);

    return this._fetchWithRetry(
      url,
      detailApiConfig.method,
      detailApiConfig.headers,
      body
    );
  },

  /**
   * バッチで全詳細を取得
   * @param {Function} onProgress - (current, total) => void
   */
  async fetchAllDetails(detailApiConfig, orderIds, onProgress) {
    const results = [];
    const BATCH_SIZE = 5;
    let delay = 300;

    for (let i = 0; i < orderIds.length; i += BATCH_SIZE) {
      const batch = orderIds.slice(i, i + BATCH_SIZE);
      const promises = batch.map(id =>
        this.fetchDetail(detailApiConfig, id)
          .then(data => ({ success: true, orderId: id, data }))
          .catch(err => ({ success: false, orderId: id, error: err.message }))
      );

      const batchResults = await Promise.all(promises);
      results.push(...batchResults);

      if (onProgress) {
        onProgress(Math.min(i + BATCH_SIZE, orderIds.length), orderIds.length);
      }

      // レート制限対応
      if (batchResults.some(r => !r.success && r.error?.includes('429'))) {
        delay = Math.min(delay * 2, 5000);
      }

      if (i + BATCH_SIZE < orderIds.length) {
        await new Promise(r => setTimeout(r, delay));
      }
    }

    return results;
  },

  // --- 内部メソッド ---

  async _fetchWithRetry(url, method, headers, body, maxRetries = 3) {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const options = {
          method: method || 'GET',
          headers: { ...headers },
          credentials: 'include',
        };

        if (body && method !== 'GET') {
          if (typeof body === 'object') {
            options.body = JSON.stringify(body);
            if (!options.headers['Content-Type'] && !options.headers['content-type']) {
              options.headers['Content-Type'] = 'application/json';
            }
          } else {
            options.body = body;
          }
        }

        const response = await fetch(url, options);

        if (response.status === 401 || response.status === 403) {
          throw new Error('AUTH_EXPIRED');
        }
        if (response.status === 429) {
          throw new Error('429');
        }
        if (!response.ok) {
          throw new Error(`HTTP_${response.status}`);
        }

        return await response.json();
      } catch (error) {
        if (error.message === 'AUTH_EXPIRED') throw error;
        if (attempt === maxRetries - 1) throw error;
        await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
      }
    }
  },

  _buildPageBody(originalBody, page, pageSize) {
    if (!originalBody || typeof originalBody !== 'object') return originalBody;
    const body = { ...originalBody };
    // 一般的なページネーションパラメータ名に対応
    const pageKeys = ['page', 'current', 'pageNum', 'pageNo'];
    const sizeKeys = ['pageSize', 'size', 'limit'];
    for (const k of pageKeys) { if (k in body) { body[k] = page; break; } }
    for (const k of sizeKeys) { if (k in body) { body[k] = pageSize; break; } }
    return body;
  },

  _buildDetailUrl(urlTemplate, orderId) {
    // URL内のID部分を置換（パスパラメータの場合）
    if (urlTemplate.includes('{orderId}') || urlTemplate.includes('{id}')) {
      return urlTemplate.replace(/\{orderId\}|\{id\}/g, orderId);
    }
    // クエリパラメータの場合
    const url = new URL(urlTemplate);
    if (url.searchParams.has('orderId') || url.searchParams.has('orderNo')) {
      url.searchParams.set(url.searchParams.has('orderId') ? 'orderId' : 'orderNo', orderId);
      return url.toString();
    }
    return urlTemplate;
  },

  _buildDetailBody(originalBody, orderId) {
    if (!originalBody || typeof originalBody !== 'object') return originalBody;
    const body = { ...originalBody };
    const idKeys = ['orderId', 'orderNo', 'orderNumber', 'id'];
    for (const k of idKeys) {
      if (k in body) { body[k] = orderId; return body; }
    }
    // フォールバック: 最初のキーをIDとして使用
    body.orderId = orderId;
    return body;
  },
};
