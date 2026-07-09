// ---- Theme ----
const themeToggleBtn = document.getElementById("theme-toggle");
const themeToggleIcon = document.getElementById("theme-toggle-icon");

function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  themeToggleIcon.textContent = theme === "dark" ? "☀️" : "🌙";
}

const savedTheme =
  localStorage.getItem("theme") ||
  (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
applyTheme(savedTheme);

themeToggleBtn.addEventListener("click", () => {
  const next = document.documentElement.classList.contains("dark") ? "light" : "dark";
  localStorage.setItem("theme", next);
  applyTheme(next);
});

// ---- Toasts ----
const toastContainer = document.getElementById("toast-container");
function showToast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ---- Tab switching ----
const tabButtons = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tab-panel");

function activateTab(name) {
  tabButtons.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  panels.forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${name}`));
  if (name === "documents") loadDocuments();
  if (name === "monitoring") loadMonitoring();
  if (name === "traces") loadTraces();
  if (name === "eval") loadLatestEval();
}
tabButtons.forEach((b) => b.addEventListener("click", () => activateTab(b.dataset.tab)));
activateTab("chat");

// ---- Formatting helpers ----
function fmtMs(ms) {
  if (ms == null) return "-";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}
function fmtCost(usd) {
  if (usd == null) return "-";
  return `$${usd.toFixed(4)}`;
}
function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
// Parses a fetch Response as JSON, tolerating non-JSON error bodies (e.g. a
// platform-level "Internal Server Error" plain-text page) so the UI shows a
// readable message instead of a raw "Unexpected token" parse error.
async function parseJsonSafe(res) {
  const raw = await res.text();
  try {
    return JSON.parse(raw);
  } catch {
    return { detail: raw.slice(0, 200) || `HTTP ${res.status} ${res.statusText}` };
  }
}
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// Renders model-generated markdown to sanitized HTML. Sanitizing matters
// here specifically because the "markdown" being rendered can include text
// quoted from uploaded documents — an uploaded file containing something
// like <script> in its content could otherwise come back through the model
// and execute in the browser (stored-XSS-via-document-upload).
function renderMarkdown(text) {
  const html = marked.parse(text || "", { breaks: true });
  return DOMPurify.sanitize(html);
}

// Turns [1], [2] citation markers into clickable spans. Runs after
// sanitization, as a plain string replace over the resulting HTML.
function linkifyCitations(html) {
  return html.replace(/\[(\d+)\]/g, '<span class="citation-ref" data-idx="$1">[$1]</span>');
}

// ---- Chat ----
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSubmitBtn = document.getElementById("chat-submit-btn");
const clearChatBtn = document.getElementById("clear-chat-btn");

let msgCounter = 0;
const sourcesByMessage = {};

function setChatBusy(busy) {
  chatInput.disabled = busy;
  chatSubmitBtn.disabled = busy;
  chatSubmitBtn.textContent = busy ? "Thinking…" : "Ask";
}

function appendUserBubble(text) {
  const wrap = document.createElement("div");
  wrap.innerHTML = `<div class="chat-bubble-user">${escapeHtml(text)}</div>`;
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendAssistantPlaceholder(msgId) {
  const wrap = document.createElement("div");
  wrap.dataset.msgId = String(msgId);
  wrap.innerHTML = `<div class="chat-bubble-assistant"><span class="text-slate-400 dark:text-slate-500">Thinking…</span></div>`;
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
  return wrap;
}

function sourcesSummaryHtml(sources) {
  if (!sources.length) return "";
  return `<div class="mt-2 text-xs text-slate-500 dark:text-slate-400">Sources: ${sources
    .map((s, i) => `[${i + 1}] ${escapeHtml(s.document)} (score ${s.score})`)
    .join(" · ")}</div>`;
}

function renderAssistantContent(msgId, text, sources, isFinal, doneMeta) {
  const wrap = chatLog.querySelector(`[data-msg-id="${msgId}"]`);
  if (!wrap) return;

  const bodyHtml = linkifyCitations(renderMarkdown(text));
  const footerHtml = isFinal
    ? `${sourcesSummaryHtml(sources)}<div class="mt-2 text-[11px] text-slate-400 dark:text-slate-500">${
        doneMeta.model
      } · ${fmtMs(doneMeta.total_ms)} · ${doneMeta.input_tokens}+${doneMeta.output_tokens} tok · ${fmtCost(
        doneMeta.cost_usd
      )}</div>`
    : "";

  wrap.innerHTML = `<div class="chat-bubble-assistant prose prose-sm dark:prose-invert max-w-none">${bodyHtml}${footerHtml}</div>`;
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderAssistantError(msgId, message) {
  const wrap = chatLog.querySelector(`[data-msg-id="${msgId}"]`);
  if (!wrap) return;
  wrap.innerHTML = `<div class="chat-bubble-assistant text-red-600 dark:text-red-400">Error: ${escapeHtml(
    message
  )}</div>`;
}

// Expand/collapse a citation's source excerpt inline below the answer.
chatLog.addEventListener("click", (e) => {
  const ref = e.target.closest(".citation-ref");
  if (!ref) return;
  const wrap = ref.closest("[data-msg-id]");
  if (!wrap) return;

  const idx = parseInt(ref.dataset.idx, 10);
  const sources = sourcesByMessage[wrap.dataset.msgId] || [];
  const source = sources[idx - 1];
  const bubble = ref.closest(".chat-bubble-assistant");

  const existing = bubble.querySelector(`.citation-detail[data-idx="${idx}"]`);
  if (existing) {
    existing.remove();
    return;
  }
  bubble.querySelectorAll(".citation-detail").forEach((d) => d.remove());

  const detail = document.createElement("div");
  detail.className = "citation-detail";
  detail.dataset.idx = String(idx);
  detail.innerHTML = source
    ? `<strong>[${idx}] ${escapeHtml(source.document)}</strong> (score ${source.score})<br>${escapeHtml(
        source.text
      )}`
    : `No source data available for [${idx}].`;
  bubble.appendChild(detail);
});

function parseSseEvent(rawEvent) {
  const dataLine = rawEvent.split("\n").find((l) => l.startsWith("data:"));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice(5).trim());
  } catch {
    return null;
  }
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = chatInput.value.trim();
  if (!question) return;

  appendUserBubble(question);
  chatInput.value = "";
  setChatBusy(true);

  const msgId = ++msgCounter;
  appendAssistantPlaceholder(msgId);

  let sources = [];
  let answerText = "";
  let doneMeta = null;
  let streamError = null;

  try {
    const res = await fetch("/api/query/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok || !res.body) {
      const data = await parseJsonSafe(res);
      throw new Error(data.detail || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let sawAnyDelta = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        const evt = parseSseEvent(rawEvent);
        if (!evt) continue;

        if (evt.type === "sources") {
          sources = evt.sources;
          sourcesByMessage[msgId] = sources;
        } else if (evt.type === "delta") {
          answerText += evt.text;
          sawAnyDelta = true;
          renderAssistantContent(msgId, answerText, sources, false);
        } else if (evt.type === "done") {
          doneMeta = evt;
        } else if (evt.type === "error") {
          streamError = evt.detail;
        }
      }
    }

    if (streamError) throw new Error(streamError);
    if (!sawAnyDelta) throw new Error("No response received from the model.");
    renderAssistantContent(msgId, answerText, sources, true, doneMeta);
  } catch (err) {
    renderAssistantError(msgId, err.message);
  } finally {
    setChatBusy(false);
  }
});

clearChatBtn.addEventListener("click", () => {
  chatLog.innerHTML = "";
  for (const key of Object.keys(sourcesByMessage)) delete sourcesByMessage[key];
});

// ---- Documents ----
const dropzone = document.getElementById("dropzone");
const uploadInput = document.getElementById("upload-input");
const uploadStatusList = document.getElementById("upload-status-list");
const documentsTable = document.getElementById("documents-table");

async function loadDocuments() {
  const res = await fetch("/api/documents");
  const docs = await parseJsonSafe(res);
  documentsTable.innerHTML = docs
    .map(
      (d) => `
      <tr class="border-t dark:border-slate-700">
        <td class="px-4 py-2">${escapeHtml(d.filename)}</td>
        <td class="px-4 py-2 text-slate-500 dark:text-slate-400">${new Date(d.uploaded_at).toLocaleString()}</td>
        <td class="px-4 py-2">${d.num_chunks}</td>
        <td class="px-4 py-2 text-slate-500 dark:text-slate-400">${fmtBytes(d.size_bytes)}</td>
        <td class="px-4 py-2 text-right">
          <button class="text-red-600 dark:text-red-400 text-xs hover:underline" data-delete="${d.id}">Delete</button>
        </td>
      </tr>`
    )
    .join("") ||
    `<tr><td colspan="5" class="px-4 py-6 text-center text-slate-400 dark:text-slate-500">No documents uploaded yet</td></tr>`;

  documentsTable.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this document and its chunks?")) return;
      const res = await fetch(`/api/documents/${btn.dataset.delete}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Document deleted", "success");
      } else {
        const data = await parseJsonSafe(res);
        showToast(data.detail || "Delete failed", "error");
      }
      loadDocuments();
    });
  });
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;

  uploadStatusList.innerHTML = "";
  let successCount = 0;

  for (const file of files) {
    const row = document.createElement("div");
    row.className = "upload-status-row text-slate-600 dark:text-slate-300";
    row.textContent = `⏳ Uploading ${file.name}…`;
    uploadStatusList.appendChild(row);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/documents/upload", { method: "POST", body: formData });
      const data = await parseJsonSafe(res);
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      row.textContent = `✅ ${file.name} — indexed ${data.num_chunks} chunks`;
      successCount++;
    } catch (err) {
      row.textContent = `❌ ${file.name} — ${err.message}`;
    }
  }

  loadDocuments();
  showToast(
    `Uploaded ${successCount}/${files.length} file(s)`,
    successCount === files.length ? "success" : "error"
  );
}

dropzone.addEventListener("click", () => uploadInput.click());
uploadInput.addEventListener("change", () => {
  uploadFiles(uploadInput.files);
  uploadInput.value = "";
});
["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
});

// ---- Monitoring ----
let volumeChart, latencyChart;

function statTile(label, value) {
  return `<div class="stat-tile"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

async function loadMonitoring() {
  const [summaryRes, seriesRes] = await Promise.all([
    fetch("/api/metrics/summary"),
    fetch("/api/metrics/timeseries?hours=24"),
  ]);
  const summary = await parseJsonSafe(summaryRes);
  const series = await parseJsonSafe(seriesRes);

  document.getElementById("stat-tiles").innerHTML = [
    statTile("Total queries", summary.total_queries),
    statTile("Avg latency", fmtMs(summary.avg_latency_ms)),
    statTile("P95 latency", fmtMs(summary.p95_latency_ms)),
    statTile("Error rate", `${(summary.error_rate * 100).toFixed(1)}%`),
    statTile("Total cost (est.)", fmtCost(summary.total_cost_usd)),
    statTile("Tokens in/out", `${summary.total_input_tokens}/${summary.total_output_tokens}`),
    statTile("Documents", summary.document_count),
    statTile("Chunks indexed", summary.chunk_count),
  ].join("");

  const labels = series.map((s) => s.hour.slice(5).replace("T", " "));
  const counts = series.map((s) => s.count);
  const latencies = series.map((s) => s.avg_latency_ms);

  if (volumeChart) volumeChart.destroy();
  if (latencyChart) latencyChart.destroy();

  volumeChart = new Chart(document.getElementById("chart-volume"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Queries", data: counts, backgroundColor: "#4f46e5" }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });

  latencyChart = new Chart(document.getElementById("chart-latency"), {
    type: "line",
    data: {
      labels,
      datasets: [{ label: "Avg latency (ms)", data: latencies, borderColor: "#0ea5e9", tension: 0.3 }],
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });
}

// ---- Traces ----
const tracesTable = document.getElementById("traces-table");

async function loadTraces() {
  const res = await fetch("/api/metrics/traces?limit=50");
  const data = await parseJsonSafe(res);
  tracesTable.innerHTML = data.items
    .map((t) => {
      const status = t.error
        ? `<span class="text-red-600 dark:text-red-400">error</span>`
        : `<span class="text-green-600 dark:text-green-400">ok</span>`;
      return `
        <tr class="border-t dark:border-slate-700 align-top">
          <td class="px-4 py-2 text-slate-500 dark:text-slate-400 whitespace-nowrap">${new Date(
            t.created_at
          ).toLocaleString()}</td>
          <td class="px-4 py-2">${t.kind}</td>
          <td class="px-4 py-2 max-w-sm">${escapeHtml(t.question)}</td>
          <td class="px-4 py-2 text-slate-500 dark:text-slate-400">${escapeHtml(t.model || "-")}</td>
          <td class="px-4 py-2">${t.input_tokens ?? 0}/${t.output_tokens ?? 0}</td>
          <td class="px-4 py-2">${fmtCost(t.cost_usd)}</td>
          <td class="px-4 py-2">${fmtMs(t.total_ms)}</td>
          <td class="px-4 py-2">${status}</td>
        </tr>`;
    })
    .join("") ||
    `<tr><td colspan="8" class="px-4 py-6 text-center text-slate-400 dark:text-slate-500">No traces yet — ask a question first</td></tr>`;
}

// ---- Eval ----
const runEvalBtn = document.getElementById("run-eval-btn");
const evalTiles = document.getElementById("eval-tiles");
const evalTable = document.getElementById("eval-table");

function renderEvalReport(report) {
  if (!report || report.available === false) {
    evalTiles.innerHTML = `<div class="col-span-5 text-slate-400 dark:text-slate-500 text-sm">No eval report yet — click "Run Eval".</div>`;
    evalTable.innerHTML = "";
    return;
  }
  evalTiles.innerHTML = [
    statTile("Cases", report.num_cases),
    statTile("Avg score (1-5)", report.avg_score),
    statTile("Pass rate (&ge;4)", `${(report.pass_rate_at_4 * 100).toFixed(0)}%`),
    statTile("Retrieval hit rate", `${(report.retrieval_hit_rate * 100).toFixed(0)}%`),
    statTile("Errors", `${report.error_count ?? 0}/${report.num_cases}`),
  ].join("");

  evalTable.innerHTML = report.results
    .map(
      (r) => `
      <tr class="border-t dark:border-slate-700 align-top">
        <td class="px-4 py-2 max-w-md">${escapeHtml(r.question)}</td>
        <td class="px-4 py-2"><span class="score-pill score-${r.score}">${r.score}/5</span></td>
        <td class="px-4 py-2">${r.retrieval_hit ? "✅" : "❌"}</td>
        <td class="px-4 py-2">${fmtMs(r.latency_ms)}</td>
        <td class="px-4 py-2 max-w-md text-slate-600 dark:text-slate-300">${escapeHtml(r.judge_reasoning)}</td>
      </tr>`
    )
    .join("");
}

async function loadLatestEval() {
  const res = await fetch("/api/eval/latest");
  const data = await parseJsonSafe(res);
  renderEvalReport(data);
}

runEvalBtn.addEventListener("click", async () => {
  runEvalBtn.disabled = true;
  runEvalBtn.textContent = "Running…";
  try {
    const res = await fetch("/api/eval/run", { method: "POST" });
    const data = await parseJsonSafe(res);
    if (!res.ok) throw new Error(data.detail || "Eval failed");
    renderEvalReport(data);
    showToast("Eval run complete", "success");
  } catch (err) {
    evalTiles.innerHTML = `<div class="col-span-5 text-red-600 dark:text-red-400 text-sm">Error: ${escapeHtml(
      err.message
    )}</div>`;
    showToast(err.message, "error");
  } finally {
    runEvalBtn.disabled = false;
    runEvalBtn.textContent = "Run Eval";
  }
});
