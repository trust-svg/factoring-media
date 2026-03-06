document.addEventListener("DOMContentLoaded", () => {
  const apiKeyInput = document.getElementById("apiKey");
  const modelSelect = document.getElementById("model");
  const saveBtn = document.getElementById("saveBtn");
  const status = document.getElementById("status");
  const toggleKey = document.getElementById("toggleKey");

  // Load saved settings
  chrome.storage.sync.get(["apiKey", "model"], (data) => {
    if (data.apiKey) apiKeyInput.value = data.apiKey;
    if (data.model) modelSelect.value = data.model;
  });

  // Toggle API key visibility
  toggleKey.addEventListener("click", () => {
    apiKeyInput.type = apiKeyInput.type === "password" ? "text" : "password";
  });

  // Save settings
  saveBtn.addEventListener("click", () => {
    const apiKey = apiKeyInput.value.trim();
    const model = modelSelect.value;

    if (!apiKey) {
      status.textContent = "APIキーを入力してください";
      status.style.color = "#c62828";
      return;
    }

    chrome.storage.sync.set({ apiKey, model }, () => {
      status.textContent = "保存しました";
      status.style.color = "#2e7d32";
      setTimeout(() => { status.textContent = ""; }, 2000);
    });
  });
});
