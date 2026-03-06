/**
 * data-processor.js — データ正規化・集計
 */
const DataProcessor = {
  /**
   * APIレスポンスからFeeRecordに正規化
   * サイトの実際のレスポンス構造に合わせて調整が必要
   */
  normalizeDetailResponse(raw, listItem) {
    const d = raw.data || raw.result || raw;

    // 料金配列を探す
    const feeArray = d.feeDetails || d.fees || d.chargeDetails ||
      d.billingDetails || d.costDetails || d.feeList || d.chargeList || [];

    const fees = {
      shipping: 0,
      fuelSurcharge: 0,
      customsDuty: 0,
      customsProcessing: 0,
      other: 0,
    };

    // 料金項目の分類
    for (const fee of feeArray) {
      const name = (fee.feeName || fee.chargeName || fee.name || fee.type || fee.feeType || '').toLowerCase();
      const amount = parseJPY(fee.amount || fee.feeAmount || fee.charge || fee.value || 0);

      if (matchKeyword(name, ['運送', 'shipping', 'freight', 'delivery', '運送料金'])) {
        fees.shipping += amount;
      } else if (matchKeyword(name, ['燃料', 'fuel', 'surcharge', '割増'])) {
        fees.fuelSurcharge += amount;
      } else if (matchKeyword(name, ['関税処理', 'customs processing', '手数料', 'processing fee'])) {
        fees.customsProcessing += amount;
      } else if (matchKeyword(name, ['関税', 'customs', 'duty', 'tax', '税金'])) {
        fees.customsDuty += amount;
      } else {
        fees.other += amount;
      }
    }

    const totalAmount = fees.shipping + fees.fuelSurcharge + fees.customsDuty +
      fees.customsProcessing + fees.other;

    // SKU情報
    const skuData = d.skuDetails || d.skus || d.items || [];
    const skus = Array.isArray(skuData) ? skuData.map(s => ({
      ebayTxId: s.ebayTxId || s.transactionId || s.ebayTransactionId || '',
      description: s.skuName || s.description || s.productName || s.name || '',
      hsCode: s.hsCode || s.hscode || '',
    })) : [];

    return {
      orderId: d.orderNo || d.orderId || d.orderNumber || listItem?.orderNo || '',
      date: d.createTime || d.createdAt || d.date || listItem?.createTime || '',
      carrier: d.carrier || d.carrierName || d.logisticsProvider || listItem?.carrier || '',
      trackingNumber: d.trackingNo || d.trackingNumber || d.waybillNo || '',
      destination: d.destination || d.country || d.destCountry || '',
      packageType: d.packageType || d.parcelType || '',
      totalAmount: totalAmount || parseJPY(d.totalAmount || d.total || 0),
      fees,
      skus,
    };
  },

  /**
   * DOMモーダルからFeeRecordに正規化
   */
  normalizeFromDOM(modalData) {
    return {
      orderId: modalData.orderId || '',
      date: modalData.date || '',
      carrier: modalData.carrier || '',
      trackingNumber: modalData.trackingNumber || '',
      destination: modalData.destination || '',
      packageType: modalData.packageType || '',
      totalAmount: modalData.totalAmount || 0,
      fees: modalData.fees || {
        shipping: 0,
        fuelSurcharge: 0,
        customsDuty: 0,
        customsProcessing: 0,
        other: 0,
      },
      skus: modalData.skus || [],
    };
  },

  /**
   * 月別集計
   */
  aggregateByMonth(records) {
    const monthly = {};
    for (const r of records) {
      const month = extractMonth(r.date);
      if (!monthly[month]) {
        monthly[month] = { month, count: 0, shipping: 0, fuelSurcharge: 0, customsDuty: 0, customsProcessing: 0, other: 0, total: 0 };
      }
      monthly[month].count++;
      monthly[month].shipping += r.fees.shipping;
      monthly[month].fuelSurcharge += r.fees.fuelSurcharge;
      monthly[month].customsDuty += r.fees.customsDuty;
      monthly[month].customsProcessing += r.fees.customsProcessing;
      monthly[month].other += r.fees.other;
      monthly[month].total += r.totalAmount;
    }
    return Object.values(monthly).sort((a, b) => a.month.localeCompare(b.month));
  },

  /**
   * 全体集計
   */
  aggregateTotals(records) {
    const totals = { count: records.length, shipping: 0, fuelSurcharge: 0, customsDuty: 0, customsProcessing: 0, other: 0, total: 0 };
    for (const r of records) {
      totals.shipping += r.fees.shipping;
      totals.fuelSurcharge += r.fees.fuelSurcharge;
      totals.customsDuty += r.fees.customsDuty;
      totals.customsProcessing += r.fees.customsProcessing;
      totals.other += r.fees.other;
      totals.total += r.totalAmount;
    }
    return totals;
  },

  /**
   * キャリア別集計
   */
  aggregateByCarrier(records) {
    const byCarrier = {};
    for (const r of records) {
      const carrier = r.carrier || '不明';
      if (!byCarrier[carrier]) {
        byCarrier[carrier] = { carrier, count: 0, total: 0 };
      }
      byCarrier[carrier].count++;
      byCarrier[carrier].total += r.totalAmount;
    }
    return Object.values(byCarrier).sort((a, b) => b.total - a.total);
  },

  /**
   * 送付先国別集計
   */
  aggregateByDestination(records) {
    const byDest = {};
    for (const r of records) {
      const dest = r.destination || '不明';
      if (!byDest[dest]) {
        byDest[dest] = { destination: dest, count: 0, total: 0 };
      }
      byDest[dest].count++;
      byDest[dest].total += r.totalAmount;
    }
    return Object.values(byDest).sort((a, b) => b.total - a.total);
  },
};

// --- ヘルパー ---
function parseJPY(text) {
  if (typeof text === 'number') return text;
  if (!text) return 0;
  const cleaned = String(text).replace(/[^0-9\-+.]/g, '');
  return parseInt(cleaned, 10) || 0;
}

function matchKeyword(text, keywords) {
  return keywords.some(kw => text.includes(kw));
}

function extractMonth(dateStr) {
  if (!dateStr) return '不明';
  // "2026-02-25 21:40:44" → "2026-02"
  const match = dateStr.match(/(\d{4})[/-](\d{2})/);
  return match ? `${match[1]}-${match[2]}` : '不明';
}
