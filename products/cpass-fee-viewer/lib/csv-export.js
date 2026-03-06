/**
 * csv-export.js — CSV出力ユーティリティ（UTF-8 BOM付き、Excel対応）
 */
const CsvExport = {
  /**
   * FeeRecordの配列からCSVを生成・ダウンロード
   */
  exportRecords(records, filename) {
    const headers = [
      '注文番号', '作成時間', 'キャリア', '追跡番号', '送付先',
      'パッケージタイプ', '運送料金', '燃料割増金', '関税処理手数料',
      '関税及び税金', 'その他', '合計', '商品名', 'HSコード',
    ];

    const rows = records.map(r => [
      r.orderId,
      r.date,
      r.carrier,
      r.trackingNumber,
      r.destination,
      r.packageType,
      r.fees.shipping,
      r.fees.fuelSurcharge,
      r.fees.customsProcessing,
      r.fees.customsDuty,
      r.fees.other,
      r.totalAmount,
      r.skus.map(s => s.description).join(' / '),
      r.skus.map(s => s.hsCode).join(' / '),
    ]);

    const csv = this._buildCsv(headers, rows);
    this._download(csv, filename || 'cpass-fee-details.csv');
  },

  /**
   * 月別集計からCSVを生成・ダウンロード
   */
  exportMonthly(monthlyData, filename) {
    const headers = [
      '月', '件数', '運送料金', '燃料割増金', '関税処理手数料',
      '関税及び税金', 'その他', '合計',
    ];

    const rows = monthlyData.map(m => [
      m.month, m.count, m.shipping, m.fuelSurcharge,
      m.customsProcessing, m.customsDuty, m.other, m.total,
    ]);

    const csv = this._buildCsv(headers, rows);
    this._download(csv, filename || 'cpass-fee-monthly.csv');
  },

  _buildCsv(headers, rows) {
    const BOM = '\uFEFF';
    const escape = (cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`;
    const lines = [
      headers.map(escape).join(','),
      ...rows.map(row => row.map(escape).join(',')),
    ];
    return BOM + lines.join('\r\n');
  },

  _download(content, filename) {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
};
