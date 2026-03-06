/**
 * dashboard.js — 結果ダッシュボード
 * 動的料金項目、送料系/関税系小計、確定/未確定判定、フィルタ、ソート、CSV出力
 * 表示列の選択機能（非表示列も集計には含む）
 */
(function () {
  'use strict';

  const PER_PAGE = 50;
  let allRecords = [];
  let filteredRecords = [];
  let currentPage = 1;
  let sortKey = 'date';
  let sortDir = 'desc';

  // 全レコードから検出された料金タイプ一覧（表示順）
  let allFeeTypes = [];

  // 表示列の設定（キー → 表示するか）
  // 固定列 + 動的料金列の全てを管理
  const FIXED_COLUMNS = [
    { key: 'orderId',       label: '注文番号',   default: true },
    { key: 'date',          label: '日付',       default: true },
    { key: 'carrier',       label: 'キャリア',   default: true },
    { key: 'trackingNumber',label: '追跡番号',   default: false },
    { key: 'destination',   label: '送付先',     default: true },
    { key: 'packageType',   label: 'パッケージ', default: false },
  ];
  const FIXED_AFTER = [
    { key: 'shippingTotal', label: '送料系',     default: true },
    { key: 'customsTotal',  label: '関税系',     default: true },
    { key: 'totalAmount',   label: '合計',       default: true },
    { key: 'confirmed',     label: '状態',       default: true },
    { key: 'skus',          label: '商品名',     default: false },
  ];

  let visibleColumns = {}; // key → boolean
  let columnOrder = [];     // 列の表示順（キーの配列）

  // --- 初期化 ---
  document.addEventListener('DOMContentLoaded', () => {
    loadData();
    setupEventListeners();
  });

  function loadData() {
    chrome.runtime.sendMessage({ type: 'GET_RESULTS' }, (result) => {
      if (!result || !result.data || result.data.length === 0) {
        showEmptyState();
        return;
      }
      allRecords = result.data;
      filteredRecords = [...allRecords];
      allFeeTypes = collectFeeTypes(allRecords);
      initColumnVisibility();
      populateFilterOptions();
      renderColumnToggles();
      render();
    });
  }

  function showEmptyState() {
    document.querySelector('.main').innerHTML = `
      <div class="empty-state">
        <h3>データがありません</h3>
        <p>SpeedPAKの取引明細ページで「一括取得」を実行してください。</p>
      </div>
    `;
  }

  // --- 料金タイプ収集 ---
  function collectFeeTypes(records) {
    const typeSet = new Map();
    for (const r of records) {
      if (!r.feeItems) continue;
      for (const f of r.feeItems) {
        if (!typeSet.has(f.feeType)) {
          typeSet.set(f.feeType, f.category);
        }
      }
    }
    const types = Array.from(typeSet.entries());
    types.sort((a, b) => {
      if (a[1] !== b[1]) return a[1] === 'shipping' ? -1 : 1;
      return a[0].localeCompare(b[0]);
    });
    return types.map(([feeType, category]) => ({ feeType, category }));
  }

  // --- 表示列管理 ---
  function initColumnVisibility() {
    // ストレージから復元を試みる
    try {
      const saved = localStorage.getItem('cpass-visible-columns');
      if (saved) {
        visibleColumns = JSON.parse(saved);
        // 新しい料金タイプが増えた場合にデフォルト表示
        for (const ft of allFeeTypes) {
          if (!(ft.feeType in visibleColumns)) {
            visibleColumns[ft.feeType] = true;
          }
        }
      } else {
        // デフォルト設定
        visibleColumns = {};
        for (const c of FIXED_COLUMNS) visibleColumns[c.key] = c.default;
        for (const ft of allFeeTypes) visibleColumns[ft.feeType] = true;
        for (const c of FIXED_AFTER) visibleColumns[c.key] = c.default;
      }
    } catch {
      visibleColumns = {};
      for (const c of FIXED_COLUMNS) visibleColumns[c.key] = c.default;
      for (const ft of allFeeTypes) visibleColumns[ft.feeType] = true;
      for (const c of FIXED_AFTER) visibleColumns[c.key] = c.default;
    }
    initColumnOrder();
  }

  function initColumnOrder() {
    // デフォルト順序を構築
    const defaultOrder = [
      ...FIXED_COLUMNS.map(c => c.key),
      ...allFeeTypes.map(ft => ft.feeType),
      ...FIXED_AFTER.map(c => c.key),
    ];

    try {
      const saved = localStorage.getItem('cpass-column-order');
      if (saved) {
        const savedOrder = JSON.parse(saved);
        // 保存された順序をベースに、新しい列を末尾に追加
        const known = new Set(savedOrder);
        columnOrder = savedOrder.filter(k => defaultOrder.includes(k));
        for (const k of defaultOrder) {
          if (!known.has(k)) columnOrder.push(k);
        }
        return;
      }
    } catch {}
    columnOrder = defaultOrder;
  }

  function saveColumnSettings() {
    try {
      localStorage.setItem('cpass-visible-columns', JSON.stringify(visibleColumns));
      localStorage.setItem('cpass-column-order', JSON.stringify(columnOrder));
    } catch {}
  }

  function isColumnVisible(key) {
    return visibleColumns[key] !== false;
  }

  function getAllColumnDefs() {
    // キー→定義のマップを作成
    const defMap = {};
    for (const c of FIXED_COLUMNS) {
      defMap[c.key] = { key: c.key, label: c.label, group: 'basic' };
    }
    for (const ft of allFeeTypes) {
      defMap[ft.feeType] = { key: ft.feeType, label: ft.feeType, group: ft.category === 'customs' ? 'customs' : 'shipping' };
    }
    for (const c of FIXED_AFTER) {
      defMap[c.key] = { key: c.key, label: c.label, group: 'summary' };
    }
    // columnOrderの順序で返す
    return columnOrder.filter(k => k in defMap).map(k => defMap[k]);
  }

  let _dragSrcKey = null;

  function renderColumnToggles() {
    const container = document.getElementById('columnToggles');
    if (!container) return;

    const allCols = getAllColumnDefs();

    container.innerHTML = `
      <div class="col-toggle-hint">ドラッグで並び替え</div>
      ${allCols.map(c => {
        const groupLabel = c.group === 'basic' ? '基本' : c.group === 'shipping' ? '送料' : c.group === 'customs' ? '関税' : '集計';
        return `
          <div class="col-toggle-item" draggable="true" data-col-key="${c.key}">
            <span class="col-drag-handle">⠿</span>
            <input type="checkbox" data-col="${c.key}" ${isColumnVisible(c.key) ? 'checked' : ''}>
            <span class="col-toggle-label">${c.label}</span>
            <span class="col-toggle-badge col-badge-${c.group}">${groupLabel}</span>
          </div>
        `;
      }).join('')}
    `;

    // チェックボックスのイベント
    container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => {
        visibleColumns[cb.dataset.col] = cb.checked;
        saveColumnSettings();
        render();
      });
    });

    // ドラッグ&ドロップイベント
    container.querySelectorAll('.col-toggle-item[draggable]').forEach(item => {
      item.addEventListener('dragstart', (e) => {
        _dragSrcKey = item.dataset.colKey;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      item.addEventListener('dragend', () => {
        _dragSrcKey = null;
        item.classList.remove('dragging');
        container.querySelectorAll('.col-toggle-item').forEach(el => el.classList.remove('drag-over'));
      });

      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        // ドロップ先のハイライト
        container.querySelectorAll('.col-toggle-item').forEach(el => el.classList.remove('drag-over'));
        item.classList.add('drag-over');
      });

      item.addEventListener('dragleave', () => {
        item.classList.remove('drag-over');
      });

      item.addEventListener('drop', (e) => {
        e.preventDefault();
        item.classList.remove('drag-over');
        const targetKey = item.dataset.colKey;
        if (_dragSrcKey && _dragSrcKey !== targetKey) {
          // columnOrder内で移動
          const srcIdx = columnOrder.indexOf(_dragSrcKey);
          const tgtIdx = columnOrder.indexOf(targetKey);
          if (srcIdx !== -1 && tgtIdx !== -1) {
            columnOrder.splice(srcIdx, 1);
            columnOrder.splice(tgtIdx, 0, _dragSrcKey);
            saveColumnSettings();
            renderColumnToggles();
            render();
          }
        }
      });
    });
  }

  // --- レンダリング ---
  function render() {
    renderSummary();
    renderMonthly();
    renderDetail();
  }

  function renderSummary() {
    const totals = aggregateTotals(filteredRecords);

    const feeCards = allFeeTypes.map(ft => ({
      label: ft.feeType,
      value: formatJPY(totals.byType[ft.feeType] || 0),
      sub: ft.category === 'customs' ? '関税系' : '送料系',
      category: ft.category,
    }));

    const confirmedCount = filteredRecords.filter(r => r.confirmed).length;
    const unconfirmedCount = filteredRecords.length - confirmedCount;

    const cards = [
      { label: '取得件数', value: `${totals.count}件`, sub: `確定: ${confirmedCount}件 / 未確定: ${unconfirmedCount}件` },
      ...feeCards,
      { label: '送料系 小計', value: formatJPY(totals.shippingTotal), sub: '運送料金 + 燃料割増金 等', isSubtotal: true, category: 'shipping' },
      { label: '関税系 小計', value: formatJPY(totals.customsTotal), sub: '関税 + 手数料 等', isSubtotal: true, category: 'customs' },
      { label: '合計', value: formatJPY(totals.total), sub: `${totals.count}件の合計`, isTotal: true },
    ];

    document.getElementById('summaryCards').innerHTML = cards.map(c => {
      let cls = 'summary-card';
      if (c.isTotal) cls += ' total';
      else if (c.isSubtotal) cls += ` subtotal ${c.category}`;
      return `
        <div class="${cls}">
          <div class="summary-card-label">${c.label}</div>
          <div class="summary-card-value">${c.value}</div>
          ${c.sub ? `<div class="summary-card-sub">${c.sub}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  function renderMonthly() {
    const monthly = aggregateByMonth(filteredRecords);
    const totals = aggregateTotals(filteredRecords);

    // columnOrderに従って月別テーブルの料金列を並べる
    const allCols = getAllColumnDefs();
    // 月別テーブルに表示する列（料金系 + 小計系 + 確定のみ）
    const monthlyColKeys = new Set([
      ...allFeeTypes.map(ft => ft.feeType),
      'shippingTotal', 'customsTotal', 'confirmed',
    ]);
    const monthlyCols = allCols.filter(c => monthlyColKeys.has(c.key) && isColumnVisible(c.key));

    document.getElementById('monthlyHead').innerHTML = `<tr>
      <th>月</th>
      <th class="num">件数</th>
      ${monthlyCols.map(c => `<th class="num">${c.label}</th>`).join('')}
      <th class="num">合計</th>
    </tr>`;

    document.getElementById('monthlyBody').innerHTML = monthly.map(m => `
      <tr>
        <td>${m.month}</td>
        <td class="num">${m.count}</td>
        ${monthlyCols.map(c => {
          if (c.key === 'shippingTotal') return `<td class="num">${formatJPY(m.shippingTotal)}</td>`;
          if (c.key === 'customsTotal') return `<td class="num">${formatJPY(m.customsTotal)}</td>`;
          if (c.key === 'confirmed') return `<td class="num">${m.confirmedCount}/${m.count}</td>`;
          return `<td class="num">${formatJPY(m.byType[c.key] || 0)}</td>`;
        }).join('')}
        <td class="num"><strong>${formatJPY(m.total)}</strong></td>
      </tr>
    `).join('');

    document.getElementById('monthlyFoot').innerHTML = `<tr>
      <td><strong>合計</strong></td>
      <td class="num">${totals.count}</td>
      ${monthlyCols.map(c => {
        if (c.key === 'shippingTotal') return `<td class="num">${formatJPY(totals.shippingTotal)}</td>`;
        if (c.key === 'customsTotal') return `<td class="num">${formatJPY(totals.customsTotal)}</td>`;
        if (c.key === 'confirmed') return `<td class="num">${totals.confirmedCount}/${totals.count}</td>`;
        return `<td class="num">${formatJPY(totals.byType[c.key] || 0)}</td>`;
      }).join('')}
      <td class="num"><strong>${formatJPY(totals.total)}</strong></td>
    </tr>`;
  }

  // 列定義からヘッダHTMLを生成
  function buildHeaderCell(col) {
    const key = col.key;
    const label = col.label;
    const isFee = col.group === 'shipping' || col.group === 'customs';
    const isNum = isFee || ['shippingTotal', 'customsTotal', 'totalAmount'].includes(key);
    const sortable = key !== 'trackingNumber' && key !== 'packageType' && key !== 'skus';
    const colSortKey = isFee && !['shippingTotal', 'customsTotal', 'totalAmount'].includes(key)
      ? `fee:${key}` : key;
    const cls = isNum ? ' class="num"' : '';
    return sortable
      ? `<th${cls} data-sort="${colSortKey}">${label}</th>`
      : `<th${cls}>${label}</th>`;
  }

  // 列定義からセルHTMLを生成
  function buildBodyCell(col, record, feeMap) {
    const key = col.key;
    switch (key) {
      case 'orderId': return `<td title="${record.orderId}">${truncate(record.orderId, 24)}</td>`;
      case 'date': return `<td>${formatDateShort(record.date)}</td>`;
      case 'carrier': return `<td>${record.carrier || ''}</td>`;
      case 'trackingNumber': return `<td title="${record.trackingNumber || ''}">${truncate(record.trackingNumber, 18)}</td>`;
      case 'destination': return `<td>${record.destination || ''}</td>`;
      case 'packageType': return `<td>${record.packageType || ''}</td>`;
      case 'shippingTotal': return `<td class="num">${formatJPY(record.shippingTotal)}</td>`;
      case 'customsTotal': return `<td class="num">${formatJPY(record.customsTotal)}</td>`;
      case 'totalAmount': return `<td class="num"><strong>${formatJPY(record.totalAmount)}</strong></td>`;
      case 'confirmed': {
        const label = record.confirmed ? '確定' : '未確定';
        const cls = record.confirmed ? 'status-confirmed' : 'status-unconfirmed';
        return `<td><span class="${cls}">${label}</span></td>`;
      }
      case 'skus': {
        const txt = (record.skus || []).map(s => s.description).join(', ');
        return `<td title="${txt}">${truncate(txt, 30)}</td>`;
      }
      default: // 動的料金列
        return `<td class="num">${formatJPY(feeMap[key] || 0)}</td>`;
    }
  }

  function renderDetail() {
    const allCols = getAllColumnDefs();
    const visCols = allCols.filter(c => isColumnVisible(c.key));

    // ヘッダ生成（表示列のみ、列順序に従う）
    let headerHtml = '<tr>';
    for (const col of visCols) {
      headerHtml += buildHeaderCell(col);
    }
    headerHtml += '</tr>';

    document.getElementById('detailHead').innerHTML = headerHtml;

    // ソートリスナー
    document.querySelectorAll('#detailTable th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (sortKey === key) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortKey = key;
          sortDir = 'asc';
        }
        renderDetail();
      });
    });

    // ソート
    const sorted = [...filteredRecords].sort((a, b) => {
      let va, vb;
      if (sortKey.startsWith('fee:')) {
        // 動的料金列のソート
        const feeType = sortKey.slice(4);
        va = getFeeAmount(a, feeType);
        vb = getFeeAmount(b, feeType);
      } else {
        va = getNestedValue(a, sortKey);
        vb = getNestedValue(b, sortKey);
      }
      const cmp = typeof va === 'number' && typeof vb === 'number'
        ? va - vb
        : String(va ?? '').localeCompare(String(vb ?? ''));
      return sortDir === 'asc' ? cmp : -cmp;
    });

    // ページネーション
    const totalPages = Math.max(1, Math.ceil(sorted.length / PER_PAGE));
    currentPage = Math.min(currentPage, totalPages);
    const start = (currentPage - 1) * PER_PAGE;
    const pageItems = sorted.slice(start, start + PER_PAGE);

    document.getElementById('detailCount').textContent = `(${filteredRecords.length}件)`;

    document.getElementById('detailBody').innerHTML = pageItems.map(r => {
      const feeMap = buildFeeMap(r);
      let rowHtml = '<tr>';
      for (const col of visCols) {
        rowHtml += buildBodyCell(col, r, feeMap);
      }
      rowHtml += '</tr>';
      return rowHtml;
    }).join('');

    // ソートヘッダ更新
    document.querySelectorAll('#detailTable th[data-sort]').forEach(th => {
      th.classList.remove('asc', 'desc');
      if (th.dataset.sort === sortKey) th.classList.add(sortDir);
    });

    renderPagination(totalPages);
  }

  function getFeeAmount(record, feeType) {
    if (!record.feeItems) return 0;
    return record.feeItems
      .filter(f => f.feeType === feeType)
      .reduce((s, f) => s + f.amount, 0);
  }

  function buildFeeMap(record) {
    const map = {};
    if (record.feeItems) {
      for (const f of record.feeItems) {
        map[f.feeType] = (map[f.feeType] || 0) + f.amount;
      }
    }
    return map;
  }

  function renderPagination(totalPages) {
    if (totalPages <= 1) {
      document.getElementById('pagination').innerHTML = '';
      return;
    }

    let html = `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">&lt;</button>`;

    const pages = getPaginationRange(currentPage, totalPages);
    for (const p of pages) {
      if (p === '...') {
        html += '<span style="padding:0 4px">...</span>';
      } else {
        html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
      }
    }

    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">&gt;</button>`;

    document.getElementById('pagination').innerHTML = html;
  }

  // --- イベントリスナー ---
  function setupEventListeners() {
    // ページネーション
    document.getElementById('pagination').addEventListener('click', (e) => {
      const btn = e.target.closest('.page-btn');
      if (btn && !btn.disabled) {
        currentPage = parseInt(btn.dataset.page, 10);
        renderDetail();
        document.getElementById('detailTable').scrollIntoView({ behavior: 'smooth' });
      }
    });

    // フィルタ
    const filterIds = ['filterFrom', 'filterTo', 'filterCarrier', 'filterDest', 'filterConfirmed', 'filterSearch'];
    for (const id of filterIds) {
      document.getElementById(id).addEventListener('input', applyFilters);
      document.getElementById(id).addEventListener('change', applyFilters);
    }

    document.getElementById('btnResetFilter').addEventListener('click', () => {
      for (const id of filterIds) document.getElementById(id).value = '';
      applyFilters();
    });

    // 表示列トグル開閉
    const toggleBtn = document.getElementById('btnColumnToggle');
    const togglePanel = document.getElementById('columnTogglePanel');
    if (toggleBtn && togglePanel) {
      toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        togglePanel.classList.toggle('open');
      });
      // パネル外クリックで閉じる
      document.addEventListener('click', (e) => {
        if (!togglePanel.contains(e.target) && e.target !== toggleBtn) {
          togglePanel.classList.remove('open');
        }
      });
    }

    // CSV出力
    document.getElementById('btnExportAll').addEventListener('click', () => exportCsv(filteredRecords));
    document.getElementById('btnExportMonthly').addEventListener('click', () => exportMonthlyCsv());

    // 再読み込み
    document.getElementById('btnRefresh').addEventListener('click', loadData);
  }

  // --- フィルタ ---
  function applyFilters() {
    const fromMonth = document.getElementById('filterFrom').value;
    const toMonth = document.getElementById('filterTo').value;
    const carrier = document.getElementById('filterCarrier').value;
    const dest = document.getElementById('filterDest').value;
    const confirmedFilter = document.getElementById('filterConfirmed').value;
    const search = document.getElementById('filterSearch').value.toLowerCase();

    filteredRecords = allRecords.filter(r => {
      const month = extractMonth(r.date);
      if (fromMonth && month < fromMonth) return false;
      if (toMonth && month > toMonth) return false;
      if (carrier && r.carrier !== carrier) return false;
      if (dest && r.destination !== dest) return false;
      if (confirmedFilter === 'confirmed' && !r.confirmed) return false;
      if (confirmedFilter === 'unconfirmed' && r.confirmed) return false;
      if (search) {
        const haystack = [r.orderId, r.trackingNumber, ...(r.skus || []).map(s => s.description)].join(' ').toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });

    currentPage = 1;
    render();
  }

  function populateFilterOptions() {
    const carriers = [...new Set(allRecords.map(r => r.carrier).filter(Boolean))].sort();
    const carrierSelect = document.getElementById('filterCarrier');
    carriers.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = c;
      carrierSelect.appendChild(opt);
    });

    const dests = [...new Set(allRecords.map(r => r.destination).filter(Boolean))].sort();
    const destSelect = document.getElementById('filterDest');
    dests.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      destSelect.appendChild(opt);
    });
  }

  // --- CSV出力（全列を列順序に従って出力） ---
  function exportCsv(records) {
    const BOM = '\uFEFF';
    const allCols = getAllColumnDefs();
    // HSコードは末尾に追加
    const headers = [...allCols.map(c => c.label), 'HSコード'];
    const rows = records.map(r => {
      const feeMap = buildFeeMap(r);
      const cells = allCols.map(c => {
        switch (c.key) {
          case 'orderId': return r.orderId;
          case 'date': return r.date;
          case 'carrier': return r.carrier;
          case 'trackingNumber': return r.trackingNumber;
          case 'destination': return r.destination;
          case 'packageType': return r.packageType;
          case 'shippingTotal': return r.shippingTotal;
          case 'customsTotal': return r.customsTotal;
          case 'totalAmount': return r.totalAmount;
          case 'confirmed': return r.confirmed ? '確定' : '未確定';
          case 'skus': return (r.skus || []).map(s => s.description).join(' / ');
          default: return feeMap[c.key] || 0;
        }
      });
      cells.push((r.skus || []).map(s => s.hsCode).join(' / '));
      return cells;
    });
    downloadCsv(BOM + buildCsv(headers, rows), 'cpass-fee-details.csv');
  }

  function exportMonthlyCsv() {
    const BOM = '\uFEFF';
    const monthly = aggregateByMonth(filteredRecords);
    const allCols = getAllColumnDefs();
    // 月別に意味のある列のみ
    const monthlyColKeys = new Set([
      ...allFeeTypes.map(ft => ft.feeType),
      'shippingTotal', 'customsTotal', 'confirmed',
    ]);
    const monthlyCols = allCols.filter(c => monthlyColKeys.has(c.key));
    const headers = ['月', '件数', ...monthlyCols.map(c => c.label), '合計'];
    const rows = monthly.map(m => {
      const cells = [m.month, m.count];
      for (const c of monthlyCols) {
        if (c.key === 'shippingTotal') cells.push(m.shippingTotal);
        else if (c.key === 'customsTotal') cells.push(m.customsTotal);
        else if (c.key === 'confirmed') cells.push(`${m.confirmedCount}/${m.count}`);
        else cells.push(m.byType[c.key] || 0);
      }
      cells.push(m.total);
      return cells;
    });
    downloadCsv(BOM + buildCsv(headers, rows), 'cpass-fee-monthly.csv');
  }

  function buildCsv(headers, rows) {
    const esc = (c) => `"${String(c ?? '').replace(/"/g, '""')}"`;
    return [headers.map(esc).join(','), ...rows.map(r => r.map(esc).join(','))].join('\r\n');
  }

  function downloadCsv(content, filename) {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // --- 集計関数（常に全データで計算、表示列に依存しない） ---
  function aggregateTotals(records) {
    const t = {
      count: records.length,
      shippingTotal: 0,
      customsTotal: 0,
      total: 0,
      confirmedCount: 0,
      byType: {},
    };
    for (const r of records) {
      t.shippingTotal += r.shippingTotal || 0;
      t.customsTotal += r.customsTotal || 0;
      t.total += r.totalAmount || 0;
      if (r.confirmed) t.confirmedCount++;
      if (r.feeItems) {
        for (const f of r.feeItems) {
          t.byType[f.feeType] = (t.byType[f.feeType] || 0) + f.amount;
        }
      }
    }
    return t;
  }

  function aggregateByMonth(records) {
    const m = {};
    for (const r of records) {
      const month = extractMonth(r.date);
      if (!m[month]) {
        m[month] = { month, count: 0, shippingTotal: 0, customsTotal: 0, total: 0, confirmedCount: 0, byType: {} };
      }
      m[month].count++;
      m[month].shippingTotal += r.shippingTotal || 0;
      m[month].customsTotal += r.customsTotal || 0;
      m[month].total += r.totalAmount || 0;
      if (r.confirmed) m[month].confirmedCount++;
      if (r.feeItems) {
        for (const f of r.feeItems) {
          m[month].byType[f.feeType] = (m[month].byType[f.feeType] || 0) + f.amount;
        }
      }
    }
    return Object.values(m).sort((a, b) => a.month.localeCompare(b.month));
  }

  // --- ユーティリティ ---
  function formatJPY(num) {
    if (typeof num !== 'number' || isNaN(num)) return '-';
    return '\u00A5' + num.toLocaleString('ja-JP');
  }

  function formatDateShort(dateStr) {
    if (dateStr == null || dateStr === '') return '-';
    const s = String(dateStr);
    const m = s.match(/(\d{4})[/-](\d{2})[/-](\d{2})/);
    return m ? `${m[1]}/${m[2]}/${m[3]}` : s;
  }

  function extractMonth(dateStr) {
    if (dateStr == null || dateStr === '') return '不明';
    const s = String(dateStr);
    const m = s.match(/(\d{4})[/-](\d{2})/);
    return m ? `${m[1]}-${m[2]}` : '不明';
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
  }

  function getNestedValue(obj, path) {
    return path.split('.').reduce((o, k) => o?.[k], obj);
  }

  function getPaginationRange(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = [];
    pages.push(1);
    if (current > 3) pages.push('...');
    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
      pages.push(i);
    }
    if (current < total - 2) pages.push('...');
    pages.push(total);
    return pages;
  }
})();
