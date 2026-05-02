/* generate.js — 動画作成パネルのロジック + タブ切替 */

let CAPABILITIES = [];
let state = {
  provider: null,
  quality: "low",
  aspect: "9:16",
  duration: 10,
  imageSource: "generated",
  cameraPreset: "",
};

// ---------- capabilities ----------

async function loadCapabilities() {
  const resp = await fetch("/api/providers/capabilities");
  CAPABILITIES = await resp.json();
  state.provider = CAPABILITIES[0].name;
  renderProviders();
  renderAspects();
  renderDurations();
  refreshChipsForProvider();
  refreshCostEstimate();
}

// ---------- render helpers ----------

function renderProviders() {
  const seg = document.getElementById("provider-segmented");
  seg.innerHTML = CAPABILITIES.map(p =>
    `<button class="segmented__btn ${p.name === state.provider ? "segmented__btn--active" : ""}"
       data-provider="${p.name}" role="radio" aria-checked="${p.name === state.provider}">
       ${p.name}
     </button>`
  ).join("");
}

function renderAspects() {
  const ALL_ASPECTS = ["9:16", "16:9", "1:1", "4:3", "3:4", "21:9"];
  const grid = document.getElementById("aspect-grid");
  grid.innerHTML = ALL_ASPECTS.map(a =>
    `<button class="chip" data-aspect="${a}" role="radio" aria-checked="${a === state.aspect}">
       <svg class="chip__icon"><use href="#aspect-${a.replace(":", "-")}"/></svg>
       <span>${a}</span>
     </button>`
  ).join("");
}

function renderDurations() {
  const cap = CAPABILITIES.find(p => p.name === state.provider);
  const seg = document.getElementById("duration-segmented");
  seg.innerHTML = cap.supported_durations.map(d =>
    `<button class="segmented__btn ${d === state.duration ? "segmented__btn--active" : ""}"
       data-duration="${d}" role="radio" aria-checked="${d === state.duration}">
       ${d}秒
     </button>`
  ).join("");
}

function refreshChipsForProvider() {
  const cap = CAPABILITIES.find(p => p.name === state.provider);

  // aspect chips
  document.querySelectorAll("#aspect-grid .chip").forEach(c => {
    const a = c.dataset.aspect;
    const supported = cap.supported_aspects.includes(a);
    c.classList.toggle("chip--disabled", !supported);
    c.classList.toggle("chip--active", supported && a === state.aspect);
    c.setAttribute("aria-checked", String(supported && a === state.aspect));
  });

  // fallback if current aspect is no longer supported
  if (!cap.supported_aspects.includes(state.aspect)) {
    state.aspect = cap.supported_aspects[0];
    refreshChipsForProvider(); // one extra pass after correction
    return;
  }

  // quality buttons
  document.querySelectorAll("#quality-segmented .segmented__btn").forEach(b => {
    const q = b.dataset.quality;
    b.classList.toggle("segmented__btn--disabled", !cap.supported_qualities.includes(q));
    b.classList.toggle("segmented__btn--active", q === state.quality);
    b.setAttribute("aria-checked", String(q === state.quality));
  });

  // fallback if current quality is no longer supported
  if (!cap.supported_qualities.includes(state.quality)) {
    state.quality = cap.supported_qualities[0];
    refreshChipsForProvider();
    return;
  }

  // duration fallback
  if (!cap.supported_durations.includes(state.duration)) {
    state.duration = cap.supported_durations[0];
    renderDurations();
  }
}

function refreshCostEstimate() {
  const cap = CAPABILITIES.find(p => p.name === state.provider);
  const rate = cap.rate_map[state.quality] ?? 0;
  const cost = cap.cost_basis === "per_second" ? rate * state.duration : rate;
  document.getElementById("cost-estimate").textContent = `$${cost.toFixed(4)}`;
}

// ---------- event wiring ----------

function wireProviderSegmented() {
  document.getElementById("provider-segmented").addEventListener("click", e => {
    const btn = e.target.closest("[data-provider]");
    if (!btn) return;
    state.provider = btn.dataset.provider;
    renderProviders();
    renderDurations();
    refreshChipsForProvider();
    refreshCostEstimate();
  });
}

function wireAspectGrid() {
  document.getElementById("aspect-grid").addEventListener("click", e => {
    const btn = e.target.closest("[data-aspect]");
    if (!btn || btn.classList.contains("chip--disabled")) return;
    state.aspect = btn.dataset.aspect;
    refreshChipsForProvider();
    refreshCostEstimate();
  });
}

function wireDurationSegmented() {
  document.getElementById("duration-segmented").addEventListener("click", e => {
    const btn = e.target.closest("[data-duration]");
    if (!btn) return;
    state.duration = parseInt(btn.dataset.duration, 10);
    renderDurations();
    refreshCostEstimate();
  });
}

function wireImageSourceSegmented() {
  const seg = document.getElementById("image-source-segmented");
  const fileInput = document.getElementById("image-file");
  const imagePromptSection = document.getElementById("image-prompt").closest(".section");

  seg.addEventListener("click", e => {
    const btn = e.target.closest("[data-image-source]");
    if (!btn) return;
    state.imageSource = btn.dataset.imageSource;

    seg.querySelectorAll(".segmented__btn").forEach(b => {
      const active = b.dataset.imageSource === state.imageSource;
      b.classList.toggle("segmented__btn--active", active);
      b.setAttribute("aria-checked", String(active));
    });

    const isUpload = state.imageSource === "uploaded";
    fileInput.hidden = !isUpload;
    // hide image-prompt textarea when uploading (it is unused)
    imagePromptSection.hidden = isUpload;
  });
}

function wireQualitySegmented() {
  document.getElementById("quality-segmented").addEventListener("click", e => {
    const btn = e.target.closest("[data-quality]");
    if (!btn || btn.classList.contains("segmented__btn--disabled")) return;
    state.quality = btn.dataset.quality;
    refreshChipsForProvider();
    refreshCostEstimate();
  });
}

function wireCameraPreset() {
  document.getElementById("camera-preset").addEventListener("change", e => {
    state.cameraPreset = e.target.value;
  });
}

// ---------- generate button ----------

async function handleGenerate() {
  const btn = document.getElementById("generate-btn");
  const errorBanner = document.getElementById("error-banner");
  btn.disabled = true;
  btn.textContent = "生成中…";
  errorBanner.hidden = true;

  try {
    if (state.imageSource === "uploaded") {
      const file = document.getElementById("image-file").files[0];
      if (!file) throw new Error("画像ファイルを選択してください");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("video_prompt", document.getElementById("video-prompt").value);
      fd.append("provider", state.provider);
      fd.append("aspect_ratio", state.aspect);
      fd.append("duration_seconds", String(state.duration));
      if (state.cameraPreset) fd.append("camera_preset", state.cameraPreset);
      // quality is intentionally omitted — /api/upload-image does not accept it
      const resp = await fetch("/api/upload-image", { method: "POST", body: fd });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      showToast(`生成開始: Job #${data.job_id}`);
    } else {
      const resp = await fetch("/api/generate/image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_prompt: document.getElementById("image-prompt").value,
          video_prompt: document.getElementById("video-prompt").value,
          provider: state.provider,
          aspect_ratio: state.aspect,
          duration_seconds: state.duration,
          camera_preset: state.cameraPreset || null,
          image_source: state.imageSource,
          quality: state.quality,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      showToast(`生成開始: Job #${data.job_id}`);
    }
    loadStats();
  } catch (e) {
    errorBanner.textContent = `エラー: ${e.message}`;
    errorBanner.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "動画を作成";
  }
}

// ---------- tab switching ----------

function switchToPanel(panelName) {
  // topbar tabs
  document.querySelectorAll(".topbar__tab[data-panel]").forEach(t => {
    const active = t.dataset.panel === panelName;
    t.classList.toggle("topbar__tab--active", active);
    t.setAttribute("aria-selected", String(active));
  });

  // 動画作成 sidebar + canvas shown together
  const generateSidebar = document.getElementById("panel-generate-sidebar");
  const generateCanvas = document.getElementById("panel-generate-canvas");
  const pendingPanel = document.getElementById("panel-pending");
  const confirmedPanel = document.getElementById("panel-confirmed");

  generateSidebar.hidden = panelName !== "generate";
  generateCanvas.hidden = panelName !== "generate";
  pendingPanel.hidden = panelName !== "pending";
  confirmedPanel.hidden = panelName !== "confirmed";

  if (panelName === "pending") loadPending();
  if (panelName === "confirmed") loadConfirmed();
}

function wireTabSwitching() {
  document.querySelectorAll(".topbar__tab[data-panel]").forEach(tab => {
    tab.addEventListener("click", () => switchToPanel(tab.dataset.panel));
  });
}

// ---------- stats ----------

async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    const d = await r.json();
    document.getElementById("header-stats").textContent =
      `完成: ${d.done}本 / コスト: $${d.total_cost_usd.toFixed(2)}`;
  } catch (_) {
    // silently ignore — stats are informational
  }
}

// ---------- pending ----------

async function loadPending() {
  const r = await fetch("/api/jobs?status=PENDING");
  const jobs = await r.json();
  const grid = document.getElementById("pending-grid");
  if (!jobs.length) {
    grid.innerHTML = '<div class="empty-state">承認待ちの画像はありません</div>';
    return;
  }
  grid.innerHTML = jobs.map(j => `
    <div class="image-card" id="job-card-${j.id}">
      ${j.image_path
        ? `<img src="/output/pending/job_${j.id}.jpg" loading="lazy">`
        : '<div style="aspect-ratio:9/16;background:var(--surface);display:flex;align-items:center;justify-content:center;color:var(--text-secondary)">生成中...</div>'}
      <div style="padding:8px;font-size:11px;color:var(--text-secondary)">パターン${j.pattern}</div>
      <div class="card-footer">
        <button class="btn btn-success" onclick="approveJob(${j.id}, this)">承認</button>
        <button class="btn btn-danger" onclick="rejectJob(${j.id}, this)">却下</button>
      </div>
    </div>
  `).join("");
}

// ---------- confirmed ----------

async function loadConfirmed() {
  const r = await fetch("/api/jobs?status=DONE");
  const jobs = await r.json();
  const grid = document.getElementById("confirmed-grid");
  if (!jobs.length) {
    grid.innerHTML = '<div class="empty-state">確定済み動画はまだありません</div>';
    return;
  }
  grid.innerHTML = jobs.map(j => `
    <div class="video-card">
      <video src="/output/videos/job_${j.id}.mp4" controls playsinline></video>
      <div class="card-info">
        パターン${j.pattern} — $${(j.image_cost_usd + j.video_cost_usd).toFixed(2)}<br>
        <a href="/output/videos/job_${j.id}.mp4" download style="color:var(--accent)">ダウンロード</a>
      </div>
    </div>
  `).join("");
}

// ---------- approve / reject ----------

async function approveJob(jobId, btn) {
  btn.disabled = true;
  const r = await fetch(`/api/approve/${jobId}`, { method: "POST" });
  if (r.ok) {
    document.getElementById(`job-card-${jobId}`)?.remove();
    showToast(`Job #${jobId} を承認しました。動画生成中...`);
    loadStats();
  }
}

async function rejectJob(jobId, btn) {
  btn.disabled = true;
  const r = await fetch(`/api/reject/${jobId}`, { method: "POST" });
  if (r.ok) {
    document.getElementById(`job-card-${jobId}`)?.remove();
    showToast(`Job #${jobId} を却下しました`);
    loadStats();
  }
}

// ---------- batch ----------

async function startBatch(btn) {
  btn.disabled = true;
  btn.textContent = "生成中...";
  const r = await fetch("/api/generate/batch", { method: "POST" });
  const d = await r.json();
  showToast(`バッチ生成開始: ${d.job_count}本`);
  btn.disabled = false;
  btn.textContent = "バッチ生成（月10本）";
}

// ---------- toast ----------

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.display = "block";
  setTimeout(() => { t.style.display = "none"; }, 3000);
}

// ---------- template prefill via ?template_id= ----------

async function applyUrlTemplatePrefill() {
  const params = new URLSearchParams(window.location.search);
  const tid = params.get("template_id");
  if (!tid) return;

  try {
    const resp = await fetch(`/api/templates/${tid}`);
    if (!resp.ok) {
      showToast(`テンプレ #${tid} の読み込みに失敗しました`);
      return;
    }
    const tmpl = await resp.json();

    if (tmpl.image_prompt) document.getElementById("image-prompt").value = tmpl.image_prompt;
    if (tmpl.video_prompt) document.getElementById("video-prompt").value = tmpl.video_prompt;

    if (tmpl.default_provider && CAPABILITIES.find(p => p.name === tmpl.default_provider)) {
      state.provider = tmpl.default_provider;
      renderProviders();
    }
    if (tmpl.default_aspect) {
      state.aspect = tmpl.default_aspect;
    }
    if (tmpl.default_duration) {
      state.duration = tmpl.default_duration;
    }
    if (tmpl.default_camera_preset !== undefined) {
      state.cameraPreset = tmpl.default_camera_preset;
      document.getElementById("camera-preset").value = tmpl.default_camera_preset;
    }
    if (tmpl.default_quality) {
      state.quality = tmpl.default_quality;
    }

    renderDurations();
    refreshChipsForProvider();
    refreshCostEstimate();
  } catch (e) {
    showToast(`テンプレ #${tid} の読み込みエラー: ${e.message}`);
  }
}

// ---------- boot ----------

window.addEventListener("DOMContentLoaded", async () => {
  wireProviderSegmented();
  wireAspectGrid();
  wireDurationSegmented();
  wireImageSourceSegmented();
  wireQualitySegmented();
  wireCameraPreset();
  wireTabSwitching();

  document.getElementById("generate-btn").addEventListener("click", handleGenerate);

  await loadCapabilities();
  await applyUrlTemplatePrefill();

  loadStats();
  setInterval(loadStats, 30000);
});
