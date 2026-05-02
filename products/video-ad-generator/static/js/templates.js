const grid = document.getElementById("template-grid");
const showArchived = document.getElementById("show-archived");
const btnNew = document.getElementById("btn-new");
const dialog = document.getElementById("modal");
const errorEl = document.getElementById("m-error");

const fields = {
  id: document.getElementById("m-id"),
  name: document.getElementById("m-name"),
  category: document.getElementById("m-category"),
  image_prompt: document.getElementById("m-image-prompt"),
  video_prompt: document.getElementById("m-video-prompt"),
  default_provider: document.getElementById("m-provider"),
  default_quality: document.getElementById("m-quality"),
  default_aspect: document.getElementById("m-aspect"),
  default_duration: document.getElementById("m-duration"),
  default_camera_preset: document.getElementById("m-camera"),
};

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

async function loadTemplates() {
  const items = await fetch(`/api/templates?include_archived=${showArchived.checked}`).then(r => r.json());
  if (items.length === 0) {
    grid.innerHTML = `<div class="empty-state">テンプレートがありません</div>`;
    return;
  }
  grid.innerHTML = items.map(t => {
    const qualityClass = t.default_quality === "high" ? "template-card__badge--quality-high" : "";
    const camera = t.default_camera_preset
      ? `<span class="template-card__badge">${escapeHtml(t.default_camera_preset)}</span>`
      : "";
    const archiveBtn = t.is_archived
      ? ""
      : `<button data-action="archive" data-id="${t.id}">アーカイブ</button>`;
    return `
      <div class="template-card ${t.is_archived ? "template-card--archived" : ""}">
        <div class="template-card__title">${escapeHtml(t.name)}</div>
        <div class="template-card__category">${escapeHtml(t.category)}</div>
        <div class="template-card__badges">
          <span class="template-card__badge">${escapeHtml(t.default_provider)}</span>
          <span class="template-card__badge ${qualityClass}">${escapeHtml(t.default_quality)}</span>
          <span class="template-card__badge">${escapeHtml(t.default_aspect)}</span>
          <span class="template-card__badge">${t.default_duration}s</span>
          ${camera}
        </div>
        <div class="template-card__actions">
          <button data-action="edit" data-id="${t.id}">編集</button>
          ${archiveBtn}
          <button class="template-card__cta" data-action="use" data-id="${t.id}">→ 動画作成</button>
        </div>
      </div>
    `;
  }).join("");
}

function openModal(template) {
  document.getElementById("modal-title").textContent = template ? "テンプレート編集" : "テンプレート作成";
  fields.id.value = template?.id ?? "";
  fields.name.value = template?.name ?? "";
  fields.category.value = template?.category ?? "custom";
  fields.image_prompt.value = template?.image_prompt ?? "";
  fields.video_prompt.value = template?.video_prompt ?? "";
  fields.default_provider.value = template?.default_provider ?? "seedance";
  fields.default_quality.value = template?.default_quality ?? "low";
  fields.default_aspect.value = template?.default_aspect ?? "9:16";
  fields.default_duration.value = String(template?.default_duration ?? 10);
  fields.default_camera_preset.value = template?.default_camera_preset ?? "";
  errorEl.textContent = "";
  dialog.showModal();
}

function closeModal() {
  dialog.close();
}

async function save() {
  const id = fields.id.value;
  const body = {
    name: fields.name.value,
    category: fields.category.value,
    image_prompt: fields.image_prompt.value,
    video_prompt: fields.video_prompt.value,
    default_provider: fields.default_provider.value,
    default_quality: fields.default_quality.value,
    default_aspect: fields.default_aspect.value,
    default_duration: parseInt(fields.default_duration.value, 10),
    default_camera_preset: fields.default_camera_preset.value || null,
  };
  const url = id ? `/api/templates/${id}` : "/api/templates";
  const method = id ? "PATCH" : "POST";
  const resp = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    errorEl.textContent = await resp.text();
    return;
  }
  closeModal();
  loadTemplates();
}

async function editTemplate(id) {
  const t = await fetch(`/api/templates/${id}`).then(r => r.json());
  openModal(t);
}

async function archiveTemplate(id) {
  if (!confirm("アーカイブしますか？")) return;
  await fetch(`/api/templates/${id}`, { method: "DELETE" });
  loadTemplates();
}

function useFor(id) {
  window.location.href = `/?template_id=${id}`;
}

grid.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const id = parseInt(btn.dataset.id, 10);
  switch (btn.dataset.action) {
    case "edit": editTemplate(id); break;
    case "archive": archiveTemplate(id); break;
    case "use": useFor(id); break;
  }
});

btnNew.addEventListener("click", () => openModal(null));
showArchived.addEventListener("change", loadTemplates);
document.getElementById("m-cancel").addEventListener("click", closeModal);
document.getElementById("m-save").addEventListener("click", save);

// Native <dialog> shows a backdrop pseudo-element; clicks on it bubble up
// with target === dialog (since the form/content is contained inside).
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) closeModal();
});

loadTemplates();
