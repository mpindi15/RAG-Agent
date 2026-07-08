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

// ---- Chat ----
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

function appendBubble(role, html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = `<div class="${role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}">${html}</div>`;
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
  return wrap;
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = chatInput.value.trim();
  if (!question) return;
  appendBubble("user", escapeHtml(question));
  chatInput.value = "";
  const pending = appendBubble("assistant", '<span class="text-slate-400">Thinking…</span>');

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await parseJsonSafe(res);
    if (!res.ok) throw new Error(data.detail || "Request failed");

    const sourcesHtml = data.sources.length
      ? `<div class="mt-2 text-xs text-slate-500">Sources: ${data.sources
          .map((s, i) => `[${i + 1}] ${escapeHtml(s.document)} (score ${s.score})`)
          .join(" · ")}</div>`
      : "";
    const metaHtml = `<div class="mt-2 text-[11px] text-slate-400">${data.model} · ${fmtMs(
      data.total_ms
    )} · ${data.input_tokens}+${data.output_tokens} tok · ${fmtCost(data.cost_usd)}</div>`;

    pending.innerHTML = `<div class="chat-bubble-assistant">${escapeHtml(data.answer)}${sourcesHtml}${metaHtml}</div>`;
  } catch (err) {
    pending.innerHTML = `<div class="chat-bubble-assistant text-red-600">Error: ${escapeHtml(err.message)}</div>`;
  }
});

// ---- Documents ----
const uploadForm = document.getElementById("upload-form");
const uploadInput = document.getElementById("upload-input");
const uploadStatus = document.getElementById("upload-status");
const documentsTable = document.getElementById("documents-table");

async function loadDocuments() {
  const res = await fetch("/api/documents");
  const docs = await parseJsonSafe(res);
  documentsTable.innerHTML = docs
    .map(
      (d) => `
      <tr class="border-t">
        <td class="px-4 py-2">${escapeHtml(d.filename)}</td>
        <td class="px-4 py-2 text-slate-500">${new Date(d.uploaded_at).toLocaleString()}</td>
        <td class="px-4 py-2">${d.num_chunks}</td>
        <td class="px-4 py-2 text-slate-500">${fmtBytes(d.size_bytes)}</td>
        <td class="px-4 py-2 text-right">
          <button class="text-red-600 text-xs hover:underline" data-delete="${d.id}">Delete</button>
        </td>
      </tr>`
    )
    .join("") || `<tr><td colspan="5" class="px-4 py-6 text-center text-slate-400">No documents uploaded yet</td></tr>`;

  documentsTable.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this document and its chunks?")) return;
      await fetch(`/api/documents/${btn.dataset.delete}`, { method: "DELETE" });
      loadDocuments();
    });
  });
}

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = uploadInput.files[0];
  if (!file) return;
  uploadStatus.textContent = "Uploading…";
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/documents/upload", { method: "POST", body: formData });
    const data = await parseJsonSafe(res);
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    uploadStatus.textContent = `Indexed ${data.num_chunks} chunks from ${data.filename}`;
    uploadInput.value = "";
    loadDocuments();
  } catch (err) {
    uploadStatus.textContent = `Error: ${err.message}`;
  }
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
  const summary = await summaryRes.json();
  const series = await seriesRes.json();

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
        ? `<span class="text-red-600">error</span>`
        : `<span class="text-green-600">ok</span>`;
      return `
        <tr class="border-t align-top">
          <td class="px-4 py-2 text-slate-500 whitespace-nowrap">${new Date(t.created_at).toLocaleString()}</td>
          <td class="px-4 py-2">${t.kind}</td>
          <td class="px-4 py-2 max-w-sm">${escapeHtml(t.question)}</td>
          <td class="px-4 py-2 text-slate-500">${escapeHtml(t.model || "-")}</td>
          <td class="px-4 py-2">${t.input_tokens ?? 0}/${t.output_tokens ?? 0}</td>
          <td class="px-4 py-2">${fmtCost(t.cost_usd)}</td>
          <td class="px-4 py-2">${fmtMs(t.total_ms)}</td>
          <td class="px-4 py-2">${status}</td>
        </tr>`;
    })
    .join("") || `<tr><td colspan="8" class="px-4 py-6 text-center text-slate-400">No traces yet — ask a question first</td></tr>`;
}

// ---- Eval ----
const runEvalBtn = document.getElementById("run-eval-btn");
const evalTiles = document.getElementById("eval-tiles");
const evalTable = document.getElementById("eval-table");

function renderEvalReport(report) {
  if (!report || report.available === false) {
    evalTiles.innerHTML = `<div class="col-span-4 text-slate-400 text-sm">No eval report yet — click "Run Eval".</div>`;
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
      <tr class="border-t align-top">
        <td class="px-4 py-2 max-w-md">${escapeHtml(r.question)}</td>
        <td class="px-4 py-2"><span class="score-pill score-${r.score}">${r.score}/5</span></td>
        <td class="px-4 py-2">${r.retrieval_hit ? "✅" : "❌"}</td>
        <td class="px-4 py-2">${fmtMs(r.latency_ms)}</td>
        <td class="px-4 py-2 max-w-md text-slate-600">${escapeHtml(r.judge_reasoning)}</td>
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
  } catch (err) {
    evalTiles.innerHTML = `<div class="col-span-4 text-red-600 text-sm">Error: ${escapeHtml(err.message)}</div>`;
  } finally {
    runEvalBtn.disabled = false;
    runEvalBtn.textContent = "Run Eval";
  }
});
