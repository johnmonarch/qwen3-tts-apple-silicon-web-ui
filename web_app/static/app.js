const state = {
  availableModels: [],
  installedModels: [],
  voices: [],
  currentTTSJobId: null,
  ttsPollTimer: null,
  downloadPollTimer: null,
};

const $ = (id) => document.getElementById(id);

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      detail = data.detail || JSON.stringify(data);
    } catch (_) {
      const text = await response.text();
      if (text) {
        detail = text;
      }
    }
    throw new Error(detail);
  }
  return response.json();
}

function setStatus(id, message, isError = false) {
  const el = $(id);
  if (!el) return;
  el.textContent = message;
  el.style.color = isError ? "#9b3028" : "";
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let n = value;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatRate(bps) {
  const n = Number(bps || 0);
  if (!Number.isFinite(n) || n <= 0) return "-";
  return `${formatBytes(n)}/s`;
}

function formatEta(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n) || n < 0) return "-";
  const mins = Math.floor(n / 60);
  const secs = Math.floor(n % 60);
  if (mins <= 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function resetDownloadUi(message = "No active downloads.") {
  setStatus("downloadStatus", message);
  const bar = $("downloadProgress");
  if (bar) {
    bar.value = 0;
    bar.classList.add("hidden");
  }
  const details = $("downloadDetails");
  if (details) {
    details.textContent = "";
    details.style.color = "";
  }
}

function renderDownloadUi(status) {
  const progress = status.progress || {};
  const failed = status.status === "failed";
  const done = status.status === "done";

  const percent = Number(progress.percent || 0);
  const filesDone = Number(progress.files_done || 0);
  const filesTotal = Number(progress.files_total || 0);
  const bytesDone = Number(progress.bytes_downloaded || 0);
  const bytesTotal = Number(progress.bytes_total || 0);
  const rate = Number(progress.download_rate_bps || 0);

  const headlineParts = [status.status.toUpperCase(), `${percent.toFixed(1)}%`];
  if (filesTotal > 0) {
    headlineParts.push(`${filesDone}/${filesTotal} files`);
  }
  if (rate > 0) {
    headlineParts.push(formatRate(rate));
  }
  setStatus("downloadStatus", headlineParts.join(" | "), failed);

  const detailParts = [];
  if (progress.message) detailParts.push(progress.message);
  if (progress.last_file) detailParts.push(`File: ${progress.last_file}`);
  if (bytesTotal > 0) {
    detailParts.push(`${formatBytes(bytesDone)} / ${formatBytes(bytesTotal)}`);
  } else if (bytesDone > 0) {
    detailParts.push(`${formatBytes(bytesDone)} downloaded`);
  }
  if (progress.eta_seconds !== null && progress.eta_seconds !== undefined && !done) {
    detailParts.push(`ETA ${formatEta(progress.eta_seconds)}`);
  }
  if (failed && status.error) {
    detailParts.push(`Error: ${status.error}`);
  }

  const details = $("downloadDetails");
  if (details) {
    details.textContent = detailParts.join(" • ");
    details.style.color = failed ? "#9b3028" : "";
  }

  const bar = $("downloadProgress");
  if (bar) {
    bar.classList.remove("hidden");
    bar.value = Math.max(0, Math.min(100, percent));
  }
}

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.id === `tab-${tabName}`);
  });
}

function updateModePanel() {
  const mode = $("ttsMode").value;
  $("modeCustom").classList.toggle("hidden", mode !== "custom");
  $("modeDesign").classList.toggle("hidden", mode !== "design");
  $("modeClone").classList.toggle("hidden", mode !== "clone");
}

function modeLabel(mode) {
  if (mode === "custom") return "Custom Voice";
  if (mode === "design") return "Voice Design";
  if (mode === "clone") return "Voice Clone";
  return mode;
}

async function loadHealth() {
  try {
    const [health, version] = await Promise.all([
      fetchJSON("/api/health"),
      fetchJSON("/api/version"),
    ]);
    let runtime = "";
    if (health.runtime_mode === "remote-worker") {
      const worker = health.worker || {};
      runtime = worker.reachable ? "Worker connected" : "Worker offline";
    } else {
      runtime = health.mlx_audio_available ? "Embedded MLX ready" : "Embedded mlx-audio missing";
    }
    $("healthStatus").textContent = `${runtime} | UI ${version.ui_version}`;
  } catch (error) {
    $("healthStatus").textContent = `Health check failed: ${error.message}`;
  }
}

function renderModelSelect() {
  const select = $("ttsModel");
  select.innerHTML = "";
  const installed = state.availableModels.filter((model) => model.installed);

  installed.forEach((model) => {
    const opt = document.createElement("option");
    opt.value = model.id;
    opt.textContent = `${model.tier} / ${model.capability}`;
    select.appendChild(opt);
  });

  if (!installed.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Install a model first";
    select.appendChild(opt);
  }
}

function renderAvailableModels() {
  const root = $("availableModels");
  if (!state.availableModels.length) {
    root.innerHTML = "<p class='muted'>No models in registry.</p>";
    return;
  }

  const table = document.createElement("table");
  table.className = "table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Tier</th>
        <th>Capability</th>
        <th>Repo</th>
        <th>Size</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector("tbody");
  state.availableModels.forEach((model) => {
    const row = document.createElement("tr");
    const action = model.installed
      ? `<span class="muted">Installed</span>`
      : `<button data-download="${model.id}">Download</button>`;

    row.innerHTML = `
      <td>${model.tier}</td>
      <td>${model.capability}</td>
      <td><code>${model.repo_id}</code></td>
      <td>${model.size_gb} GB</td>
      <td>${action}</td>
    `;
    tbody.appendChild(row);
  });

  root.innerHTML = "";
  root.appendChild(table);

  root.querySelectorAll("button[data-download]").forEach((button) => {
    button.addEventListener("click", () => {
      startDownload(button.dataset.download);
    });
  });
}

function renderInstalledModels() {
  const root = $("installedModels");
  if (!state.installedModels.length) {
    root.innerHTML = "<p class='muted'>No installed models.</p>";
    return;
  }

  const table = document.createElement("table");
  table.className = "table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Tier</th>
        <th>Capability</th>
        <th>Path</th>
        <th>Size</th>
        <th>Status</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector("tbody");
  state.installedModels.forEach((model) => {
    const row = document.createElement("tr");
    const status = model.valid ? "Ready" : model.validation_message;

    row.innerHTML = `
      <td>${model.tier}</td>
      <td>${model.capability}</td>
      <td><code>${model.path}</code></td>
      <td>${model.size_human}</td>
      <td>${status}</td>
      <td><button class="danger" data-remove="${model.id}">Remove</button></td>
    `;
    tbody.appendChild(row);
  });

  root.innerHTML = "";
  root.appendChild(table);

  root.querySelectorAll("button[data-remove]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm("Remove this model set from disk?")) return;
      try {
        await fetchJSON("/api/models/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_set_id: button.dataset.remove }),
        });
        await loadModels();
      } catch (error) {
        setStatus("downloadStatus", error.message, true);
      }
    });
  });
}

async function loadModels() {
  try {
    const [available, installed] = await Promise.all([
      fetchJSON("/api/models/available"),
      fetchJSON("/api/models/installed"),
    ]);
    state.availableModels = available.models || [];
    state.installedModels = installed.models || [];

    renderModelSelect();
    renderAvailableModels();
    renderInstalledModels();
  } catch (error) {
    setStatus("downloadStatus", error.message, true);
  }
}

async function startDownload(modelSetId) {
  try {
    const token = $("downloadToken").value.trim();
    const revision = $("downloadRevision").value.trim();
    const body = {
      model_set_id: modelSetId,
      token: token || null,
      revision: revision || null,
    };

    const result = await fetchJSON("/api/models/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderDownloadUi({
      status: "queued",
      progress: {
        percent: 0,
        files_done: 0,
        files_total: 0,
        message: "Queued",
      },
    });
    pollDownload(result.job_id);
  } catch (error) {
    setStatus("downloadStatus", error.message, true);
  }
}

function pollDownload(jobId) {
  if (state.downloadPollTimer) {
    clearInterval(state.downloadPollTimer);
  }

  state.downloadPollTimer = setInterval(async () => {
    try {
      const status = await fetchJSON(`/api/models/download/${jobId}`);
      renderDownloadUi(status);

      if (status.status === "done" || status.status === "failed") {
        clearInterval(state.downloadPollTimer);
        state.downloadPollTimer = null;
        await loadModels();
      }
    } catch (error) {
      clearInterval(state.downloadPollTimer);
      state.downloadPollTimer = null;
      setStatus("downloadStatus", error.message, true);
    }
  }, 500);
}

function renderVoiceOptions() {
  const select = $("ttsVoiceId");
  select.innerHTML = "";

  if (!state.voices.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No saved voices";
    select.appendChild(opt);
    return;
  }

  state.voices.forEach((voice) => {
    const opt = document.createElement("option");
    opt.value = voice.name;
    opt.textContent = `${voice.name} (${voice.duration_seconds || 0}s)`;
    select.appendChild(opt);
  });
}

function renderVoiceList() {
  const root = $("voiceList");
  if (!state.voices.length) {
    root.innerHTML = "<p class='muted'>No voices enrolled.</p>";
    return;
  }

  const table = document.createElement("table");
  table.className = "table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Name</th>
        <th>Duration</th>
        <th>Preview</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector("tbody");
  state.voices.forEach((voice) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${voice.name}</td>
      <td>${voice.duration_seconds || 0}s</td>
      <td>${voice.audio_url ? `<audio controls src="${voice.audio_url}"></audio>` : "-"}</td>
      <td>
        <button class="secondary" data-rename="${voice.name}">Rename</button>
        <button class="danger" data-delete="${voice.name}">Delete</button>
      </td>
    `;
    tbody.appendChild(row);
  });

  root.innerHTML = "";
  root.appendChild(table);

  root.querySelectorAll("button[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm(`Delete voice ${button.dataset.delete}?`)) return;
      try {
        await fetchJSON("/api/voices/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: button.dataset.delete }),
        });
        await loadVoices();
      } catch (error) {
        alert(error.message);
      }
    });
  });

  root.querySelectorAll("button[data-rename]").forEach((button) => {
    button.addEventListener("click", async () => {
      const newName = prompt("New voice name:", button.dataset.rename);
      if (!newName || newName === button.dataset.rename) return;
      try {
        await fetchJSON("/api/voices/rename", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            old_name: button.dataset.rename,
            new_name: newName,
          }),
        });
        await loadVoices();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

async function loadVoices() {
  try {
    const result = await fetchJSON("/api/voices");
    state.voices = result.voices || [];
    renderVoiceOptions();
    renderVoiceList();
  } catch (error) {
    console.error(error);
  }
}

async function submitVoiceEnroll(event) {
  event.preventDefault();
  const formData = new FormData();

  const audioInput = $("voiceAudio");
  if (!audioInput.files.length) {
    alert("Select an audio file first");
    return;
  }

  formData.append("name", $("voiceName").value.trim());
  formData.append("transcript", $("voiceTranscript").value.trim());
  formData.append("audio", audioInput.files[0]);

  try {
    await fetchJSON("/api/voices/enroll", {
      method: "POST",
      body: formData,
    });
    $("voiceEnrollForm").reset();
    await loadVoices();
  } catch (error) {
    alert(error.message);
  }
}

async function generateTTS() {
  const mode = $("ttsMode").value;
  const payload = {
    mode,
    model_set_id: $("ttsModel").value,
    text: $("ttsText").value.trim(),
  };

  if (!payload.model_set_id) {
    setStatus("ttsStatus", "Install and select a model first.", true);
    return;
  }

  if (!payload.text) {
    setStatus("ttsStatus", "Enter text first.", true);
    return;
  }

  if (mode === "custom") {
    payload.voice = $("ttsVoice").value.trim() || "Vivian";
    payload.speed = Number($("ttsSpeed").value || 1.0);
    payload.instruct = $("ttsInstructCustom").value.trim() || "Normal tone";
  }

  if (mode === "design") {
    payload.instruct = $("ttsInstructDesign").value.trim();
  }

  if (mode === "clone") {
    payload.voice_id = $("ttsVoiceId").value;
    if (!payload.voice_id) {
      setStatus("ttsStatus", "Enroll or select a saved voice for clone mode.", true);
      return;
    }
  }

  try {
    const result = await fetchJSON("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.currentTTSJobId = result.job_id;
    $("cancelBtn").disabled = false;
    $("ttsPlayer").classList.add("hidden");
    setStatus("ttsStatus", `Queued (${result.job_id.slice(0, 8)})`);
    pollTTSJob(result.job_id);
  } catch (error) {
    setStatus("ttsStatus", error.message, true);
  }
}

function pollTTSJob(jobId) {
  if (state.ttsPollTimer) {
    clearInterval(state.ttsPollTimer);
  }

  state.ttsPollTimer = setInterval(async () => {
    try {
      const job = await fetchJSON(`/api/tts/${jobId}`);
      const status = job.status;
      setStatus("ttsStatus", `${status.toUpperCase()} | ${modeLabel(job.request.mode)}`,
        status === "failed" || status === "cancelled");

      if (status === "done") {
        clearInterval(state.ttsPollTimer);
        state.ttsPollTimer = null;
        $("cancelBtn").disabled = true;

        const outputUrl = job.result?.output_url;
        if (outputUrl) {
          const player = $("ttsPlayer");
          player.src = outputUrl;
          player.classList.remove("hidden");
          player.play().catch(() => {});
          await loadOutputs();
        }
      }

      if (status === "failed") {
        clearInterval(state.ttsPollTimer);
        state.ttsPollTimer = null;
        $("cancelBtn").disabled = true;
        setStatus("ttsStatus", `FAILED: ${job.error || "Unknown error"}`, true);
      }

      if (status === "cancelled") {
        clearInterval(state.ttsPollTimer);
        state.ttsPollTimer = null;
        $("cancelBtn").disabled = true;
        setStatus("ttsStatus", "Cancelled", true);
      }
    } catch (error) {
      clearInterval(state.ttsPollTimer);
      state.ttsPollTimer = null;
      $("cancelBtn").disabled = true;
      setStatus("ttsStatus", error.message, true);
    }
  }, 900);
}

async function cancelCurrentTTS() {
  if (!state.currentTTSJobId) return;
  try {
    await fetchJSON(`/api/tts/${state.currentTTSJobId}/cancel`, {
      method: "POST",
    });
  } catch (error) {
    setStatus("ttsStatus", error.message, true);
  }
}

function renderOutputs(outputs) {
  const root = $("outputList");
  if (!outputs.length) {
    root.innerHTML = "<p class='muted'>No outputs yet.</p>";
    return;
  }

  const table = document.createElement("table");
  table.className = "table";
  table.innerHTML = `
    <thead>
      <tr>
        <th></th>
        <th>Time</th>
        <th>Mode</th>
        <th>Model</th>
        <th>Audio</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector("tbody");

  outputs.forEach((item) => {
    const row = document.createElement("tr");
    const ts = new Date(item.timestamp).toLocaleString();
    const audio = item.output_url ? `<audio controls src="${item.output_url}"></audio>` : "missing";
    const download = item.output_url
      ? `<a href="${item.output_url}" download>WAV</a>`
      : "-";

    row.innerHTML = `
      <td><input type="checkbox" data-output-id="${item.id}" /></td>
      <td>${ts}</td>
      <td>${modeLabel(item.mode)}</td>
      <td><code>${item.model_set_id || ""}</code></td>
      <td>${audio}</td>
      <td>
        ${download}
        <button class="danger" data-delete-output="${item.id}">Delete</button>
      </td>
    `;
    tbody.appendChild(row);
  });

  root.innerHTML = "";
  root.appendChild(table);

  root.querySelectorAll("button[data-delete-output]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm("Delete this output?")) return;
      try {
        await fetchJSON("/api/outputs/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ output_id: button.dataset.deleteOutput }),
        });
        await loadOutputs();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

async function loadOutputs() {
  try {
    const result = await fetchJSON("/api/outputs");
    renderOutputs(result.outputs || []);
  } catch (error) {
    console.error(error);
  }
}

async function zipSelectedOutputs() {
  const checked = [...document.querySelectorAll("input[data-output-id]:checked")]
    .map((el) => el.dataset.outputId)
    .filter(Boolean);

  if (!checked.length) {
    alert("Select at least one output first.");
    return;
  }

  const response = await fetch("/api/outputs/zip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ output_ids: checked }),
  });

  if (!response.ok) {
    const msg = await response.text();
    alert(msg || "ZIP export failed");
    return;
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "outputs.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadSettings() {
  try {
    const settings = await fetchJSON("/api/settings");
    $("settingTier").value = settings.default_model_tier || "Lite";
    $("settingSaveOutputs").value = String(settings.save_outputs);
    $("settingPersistToken").value = String(settings.persist_hf_token);
    $("settingHFToken").value = settings.hf_token || "";
    $("settingLogRawText").value = String(settings.log_raw_text);

    const tokenState = settings.has_hf_token ? "Token available" : "No token stored";
    setStatus("settingsStatus", tokenState);
  } catch (error) {
    setStatus("settingsStatus", error.message, true);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    default_model_tier: $("settingTier").value,
    save_outputs: $("settingSaveOutputs").value === "true",
    persist_hf_token: $("settingPersistToken").value === "true",
    hf_token: $("settingHFToken").value,
    log_raw_text: $("settingLogRawText").value === "true",
  };

  try {
    await fetchJSON("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus("settingsStatus", "Settings saved.");
  } catch (error) {
    setStatus("settingsStatus", error.message, true);
  }
}

function wireEvents() {
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });

  $("ttsMode").addEventListener("change", updateModePanel);
  $("generateBtn").addEventListener("click", generateTTS);
  $("cancelBtn").addEventListener("click", cancelCurrentTTS);

  $("voiceEnrollForm").addEventListener("submit", submitVoiceEnroll);
  $("refreshOutputsBtn").addEventListener("click", loadOutputs);
  $("zipOutputsBtn").addEventListener("click", zipSelectedOutputs);
  $("settingsForm").addEventListener("submit", saveSettings);
}

async function init() {
  wireEvents();
  updateModePanel();
  resetDownloadUi();

  await Promise.all([
    loadHealth(),
    loadModels(),
    loadVoices(),
    loadOutputs(),
    loadSettings(),
  ]);
}

document.addEventListener("DOMContentLoaded", init);
