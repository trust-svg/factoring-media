/**
 * ui.js — ページ内注入UI（コントロールパネル）
 * content.jsから呼び出される
 */
const CpassUI = {
  panel: null,
  state: 'idle', // idle | ready | collecting | done | error

  /**
   * コントロールパネルを注入
   */
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
          <button class="cpass-fv-btn cpass-fv-btn-primary cpass-fv-start" disabled>
            一括取得
          </button>
          <button class="cpass-fv-btn cpass-fv-btn-secondary cpass-fv-dashboard" disabled>
            結果を表示
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(this.panel);

    // イベント
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

  /**
   * ステータス更新
   */
  setStatus(state, text) {
    this.state = state;
    const dot = this.panel.querySelector('.cpass-fv-status-dot');
    const statusText = this.panel.querySelector('.cpass-fv-status-text');
    const hint = this.panel.querySelector('.cpass-fv-hint');

    dot.className = `cpass-fv-status-dot ${state}`;
    statusText.textContent = text;

    // ヒント表示制御
    if (state === 'idle') {
      hint.style.display = '';
      hint.textContent = 'いずれかの行の「詳細」をクリックしてAPIを検出してください。';
    } else {
      hint.style.display = 'none';
    }
  },

  /**
   * API検出完了時
   */
  onApiReady() {
    this.setStatus('ready', 'API検出完了 - 取得可能');
    this.panel.querySelector('.cpass-fv-start').disabled = false;
  },

  /**
   * 収集開始
   */
  startCollecting() {
    this.setStatus('collecting', '取得中...');
    this.panel.querySelector('.cpass-fv-start').disabled = true;
    this.panel.querySelector('.cpass-fv-progress').style.display = '';
    this.panel.querySelector('.cpass-fv-error').style.display = 'none';
  },

  /**
   * 進捗更新
   */
  updateProgress(current, total) {
    const pct = total > 0 ? (current / total * 100) : 0;
    this.panel.querySelector('.cpass-fv-progress-fill').style.width = `${pct}%`;
    this.panel.querySelector('.cpass-fv-progress-text').textContent = `${current} / ${total}`;
    this.panel.querySelector('.cpass-fv-status-text').textContent = `取得中... ${current}/${total}`;
  },

  /**
   * 収集完了
   */
  onComplete(count, errors) {
    const text = errors > 0
      ? `完了 (${count}件取得, ${errors}件エラー)`
      : `完了 (${count}件取得)`;
    this.setStatus('done', text);
    this.panel.querySelector('.cpass-fv-start').disabled = false;
    this.panel.querySelector('.cpass-fv-start').textContent = '再取得';
    this.panel.querySelector('.cpass-fv-dashboard').disabled = false;
  },

  /**
   * エラー表示
   */
  showError(message) {
    this.setStatus('error', 'エラー発生');
    const errorEl = this.panel.querySelector('.cpass-fv-error');
    errorEl.style.display = '';
    errorEl.textContent = message;
    this.panel.querySelector('.cpass-fv-start').disabled = false;
  },

  /**
   * パネル削除
   */
  remove() {
    if (this.panel) {
      this.panel.remove();
      this.panel = null;
    }
  },

  // コールバック
  onStart: null,
  onDashboard: null,
};
