document.addEventListener('DOMContentLoaded', () => {
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const infoSection = document.getElementById('infoSection');
  const itemCount = document.getElementById('itemCount');
  const errorCount = document.getElementById('errorCount');
  const lastRun = document.getElementById('lastRun');
  const btnDashboard = document.getElementById('btnDashboard');
  const btnClear = document.getElementById('btnClear');

  // ステータス取得
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (status) => {
    if (!status) {
      statusText.textContent = '未接続';
      return;
    }

    statusDot.className = `status-dot ${status.state}`;

    switch (status.state) {
      case 'idle':
        statusText.textContent = '待機中';
        break;
      case 'collecting':
        statusText.textContent = `取得中... ${status.current}/${status.total}`;
        break;
      case 'done':
        statusText.textContent = '取得完了';
        infoSection.style.display = '';
        itemCount.textContent = `${status.current}件`;
        errorCount.textContent = `${status.errors}件`;
        lastRun.textContent = formatDate(status.lastRun);
        btnDashboard.disabled = false;
        break;
      case 'error':
        statusText.textContent = 'エラー';
        statusDot.className = 'status-dot error';
        break;
    }
  });

  // ダッシュボード表示
  btnDashboard.addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'OPEN_DASHBOARD' });
    window.close();
  });

  // データクリア
  btnClear.addEventListener('click', () => {
    if (confirm('保存されたデータをすべて削除しますか？')) {
      chrome.runtime.sendMessage({ type: 'CLEAR_DATA' }, () => {
        statusDot.className = 'status-dot idle';
        statusText.textContent = '待機中';
        infoSection.style.display = 'none';
        btnDashboard.disabled = true;
      });
    }
  });

  function formatDate(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
});
