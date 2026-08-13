/* Career Radar — runner + results dashboard (EATP-015/016, v3 redesign).
 *
 * States: idle -> working -> (error | done -> results). "working" also
 * renders a dismissible notice banner for needs_intervention events (e.g.
 * LinkedIn login) without leaving the working state, because the run itself
 * doesn't stop for those. "done" holds briefly on the checkmark, then fades
 * into "results" — one more state in this same machine, not a second page.
 *
 * v3 (2026-08-12): Kevin sent a reference mockup + a full written spec and
 * asked for a light "Apple + Aero" glass rebuild — white-roto background,
 * large soft pastel ambient blobs, translucent panels, green as the one
 * functional accent, a sidebar with real run stats, real source logos, and
 * a per-job detail modal (score breakdown + AI summary + pros/cons) so he
 * can decide before ever leaving the app. Confirmed over five preview
 * rounds (palette, identity, glass strength, real logos, AI-summary box,
 * final glass balance) before any of this was built for real.
 */

const states = document.querySelectorAll(".state");
const startBtn = document.getElementById("startBtn");
const retryBtn = document.getElementById("retryBtn");
const sideRerunBtn = document.getElementById("sideRerunBtn");
const topRerunBtn = document.getElementById("topRerunBtn");
const statusText = document.getElementById("statusText");
const barFill = document.getElementById("barFill");
const barPct = document.getElementById("barPct");
const noticeBanner = document.getElementById("noticeBanner");
const noticeText = document.getElementById("noticeText");
const errorMessage = document.getElementById("errorMessage");
const doneMessage = document.getElementById("doneMessage");

const resultsMeta = document.getElementById("resultsMeta");
const resultsGrid = document.getElementById("resultsGrid");
const resultsEmpty = document.getElementById("resultsEmpty");
const searchInput = document.getElementById("searchInput");
const remoteOnlyToggle = document.getElementById("remoteOnlyToggle");
const hideDismissedToggle = document.getElementById("hideDismissedToggle");

const sideStatusLine = document.getElementById("sideStatusLine");
const sideStatusMeta = document.getElementById("sideStatusMeta");
const sideTotal = document.getElementById("sideTotal");
const sideTotalLabel = document.getElementById("sideTotalLabel");
const sideCatBars = document.getElementById("sideCatBars");
const sideSources = document.getElementById("sideSources");

const overlay = document.getElementById("overlay");
const modalBody = document.getElementById("modalBody");

const clearCacheBtn = document.getElementById("clearCacheBtn");
const sideClearCacheBtn = document.getElementById("sideClearCacheBtn");

// How long the "Listo" checkmark holds before fading into the dashboard.
const DONE_HOLD_MS = 1100;

// Grade -> pill color tier (the letter itself stays precise; only the tint groups).
const GRADE_TONE = { "A+": "good", A: "good", B: "mid", C: "low", D: "low" };

// Known platforms get their real brand mark (CC0 "Simple Icons", vendored in
// web/static/icons/); anything else falls back to a colored monogram —
// still distinct at a glance, no unofficial logo guessing.
const SOURCE_ICONS = {
  linkedin: { kind: "svg", file: "linkedin", color: "#0A66C2" },
  indeed: { kind: "svg", file: "indeed", color: "#2164F3" },
  greenhouse: { kind: "svg", file: "greenhouse", color: "#24A47F" },
  occ: { kind: "letter", letter: "O", color: "#E03B2D" },
  computrabajo: { kind: "letter", letter: "C", color: "#0AA6A6" },
  lever: { kind: "letter", letter: "L", color: "#6B5CE0" },
  remoteok: { kind: "letter", letter: "K", color: "#E65100" },
  remotive: { kind: "letter", letter: "R", color: "#8A5CF6" },
  wwr: { kind: "letter", letter: "W", color: "#1B1F3B" },
  himalayas: { kind: "letter", letter: "H", color: "#E85D9E" },
};
const iconCache = {};

// phase -> last intervention message still pending for that phase.
let notices = {};

// One entry per job: { scored, isNew, action: 'applied'|'dismissed'|null, evalLabel: {label,reason}|null }
let allJobs = [];
let filters = { grade: "", source: "" };

// EATP-017: match-quality labeling — reason chips shown once Kevin marks a
// job "Mala", so the FP-by-reason report (eval/report.py) can point tuning
// at the right rubric layer (remote gate / field cap / English).
const EVAL_REASONS = [
  { value: "not_remote", label: "No remoto" },
  { value: "off_role", label: "Fuera de campo" },
  { value: "english", label: "Inglés" },
  { value: "other", label: "Otro" },
];

function showState(name) {
  states.forEach((el) => el.classList.toggle("active", el.dataset.state === name));
  document.body.dataset.state = name;
}

// Fades the current state out, then the target state in — used only for the
// one moment that deserves the flourish (done -> results). Every other
// transition (idle/working/error) uses the plain, instant `showState`.
function transitionToState(target) {
  const current = document.querySelector(".state.active");
  if (!current || current.dataset.state === target) {
    showState(target);
    return;
  }
  current.classList.add("fade-out");
  window.setTimeout(() => {
    current.classList.remove("fade-out", "active");
    const next = document.querySelector(`.state[data-state="${target}"]`);
    next.classList.add("active", "fade-in-start");
    document.body.dataset.state = target;
    void next.offsetHeight; // force a reflow so the browser registers the start state first
    requestAnimationFrame(() => next.classList.remove("fade-in-start"));
  }, 320);
}

function setProgress(percent, message) {
  const clamped = Math.max(0, Math.min(100, percent || 0));
  statusText.textContent = message || "";
  barFill.style.width = clamped + "%";
  barPct.textContent = Math.round(clamped) + "%";
}

function renderNotices() {
  const messages = Object.values(notices);
  if (messages.length === 0) {
    noticeBanner.hidden = true;
    return;
  }
  noticeText.textContent = messages[messages.length - 1];
  noticeBanner.hidden = false;
}

// Phases at/after these have moved past collect — any lingering per-source
// intervention notice is stale by then, since collect is fully done.
const PHASES_PAST_COLLECT = new Set(["gate", "prefilter", "ai", "persist"]);

function handleEvent(event) {
  if (event.status === "needs_intervention") {
    notices[event.phase] = event.message;
    renderNotices();
    return;
  }

  if (event.phase === "error") {
    notices = {};
    errorMessage.textContent = event.message || "Ocurrió un error inesperado.";
    showState("error");
    return;
  }

  if (event.phase === "persist" && event.status === "done") {
    notices = {};
    doneMessage.textContent = event.message || "Listo";
    showState("done");
    window.setTimeout(revealResults, DONE_HOLD_MS);
    return;
  }

  if (PHASES_PAST_COLLECT.has(event.phase)) {
    notices = {};
  }
  renderNotices();
  showState("working");
  setProgress(event.percent, event.message);
}

let eventSource = null;

function connectEvents() {
  if (eventSource) return;
  eventSource = new EventSource("/events");
  eventSource.onmessage = (raw) => {
    try {
      handleEvent(JSON.parse(raw.data));
    } catch {
      // A malformed event is skipped rather than breaking the whole stream.
    }
  };
}

async function startRun() {
  notices = {};
  renderNotices();
  showState("working");
  setProgress(0, "Iniciando…");
  connectEvents();
  await fetch("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

// ---------------------------------------------------------------------------
// Results dashboard (EATP-016)
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function gradeTone(grade) {
  return GRADE_TONE[grade] || "low";
}

function formatAge(daysOld) {
  if (daysOld === null || daysOld === undefined || daysOld >= 999) return "antigüedad desconocida";
  if (daysOld <= 0) return "hoy";
  if (daysOld === 1) return "ayer";
  return `hace ${daysOld} días`;
}

function formatDateTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
}

async function sourceIconHtml(source) {
  const spec = SOURCE_ICONS[source] || { kind: "letter", letter: (source || "?")[0].toUpperCase(), color: "#687083" };
  if (spec.kind === "letter") {
    return `<span class="source-ico" style="background:${spec.color}">${escapeHtml(spec.letter)}</span>`;
  }
  if (!(spec.file in iconCache)) {
    try {
      const res = await fetch(`/static/icons/${spec.file}.svg`);
      iconCache[spec.file] = await res.text();
    } catch {
      iconCache[spec.file] = null;
    }
  }
  const svg = iconCache[spec.file];
  if (!svg) return `<span class="source-ico" style="background:${spec.color}">${escapeHtml(source[0].toUpperCase())}</span>`;
  const inlined = svg.replace("<svg ", '<svg fill="#fff" ');
  return `<span class="source-ico" style="background:${spec.color}">${inlined}</span>`;
}

// ---- custom dropdowns (grade / source) ----

function closeAllDropdowns() {
  document.querySelectorAll(".dropdown.open").forEach((dd) => dd.classList.remove("open"));
}

document.querySelectorAll(".dropdown-btn").forEach((btn) => {
  btn.addEventListener("click", (event) => {
    const dropdown = btn.closest(".dropdown");
    const wasOpen = dropdown.classList.contains("open");
    closeAllDropdowns();
    dropdown.classList.toggle("open", !wasOpen);
    event.stopPropagation();
  });
});
document.addEventListener("click", closeAllDropdowns);

function wireDropdownSelection(menuEl, labelEl, key) {
  menuEl.addEventListener("click", (event) => {
    const item = event.target.closest(".dropdown-item");
    if (!item) return;
    menuEl.querySelectorAll(".dropdown-item").forEach((i) => i.classList.toggle("active", i === item));
    labelEl.textContent = item.textContent;
    filters[key] = item.dataset.value || "";
    applyFiltersAndRender();
  });
}
wireDropdownSelection(
  document.querySelector("#gradeDropdown .dropdown-menu"),
  document.getElementById("gradeDropdownLabel"),
  "grade"
);
wireDropdownSelection(
  document.getElementById("sourceDropdownMenu"),
  document.getElementById("sourceDropdownLabel"),
  "source"
);

function populateSourceDropdown() {
  const sources = [...new Set(allJobs.map((entry) => entry.scored.job.source))].sort();
  const menu = document.getElementById("sourceDropdownMenu");
  const label = document.getElementById("sourceDropdownLabel");
  menu.innerHTML = ['<button class="dropdown-item active" type="button" data-value="">Todas las fuentes</button>']
    .concat(sources.map((s) => `<button class="dropdown-item" type="button" data-value="${escapeHtml(s)}">${escapeHtml(s)}</button>`))
    .join("");
  if (!sources.includes(filters.source)) {
    filters.source = "";
    label.textContent = "Todas las fuentes";
  }
}

// ---- checkboxes: keep the custom checkmark in sync with the real input ----

function syncCheckbox(input) {
  input.closest(".filter-check").classList.toggle("checked", input.checked);
}
[remoteOnlyToggle, hideDismissedToggle].forEach((el) => {
  el.addEventListener("change", () => syncCheckbox(el));
});

// ---- sidebar ----

function renderSidebar(result) {
  if (!result) {
    sideStatusLine.textContent = "Sin corridas todavía";
    sideStatusLine.className = "status-line";
    sideStatusMeta.textContent = "";
    sideTotal.textContent = "0";
    sideTotalLabel.textContent = "";
    sideCatBars.innerHTML = "";
    sideSources.innerHTML = "";
    return;
  }

  const ok = result.status === "success";
  sideStatusLine.textContent = ok ? "✓ Corrida exitosa" : "✕ Corrida con errores";
  sideStatusLine.className = "status-line " + (ok ? "ok" : "err");

  const providers = Object.keys(result.ai_usage || {});
  const aiLine = providers.length
    ? `IA: <strong>${escapeHtml(providers.join(", "))}</strong> · ${result.counts?.ai_evaluated ?? 0} evaluadas`
    : "";
  sideStatusMeta.innerHTML = `${escapeHtml(formatDateTime(result.finished_at))}${aiLine ? "<br>" + aiLine : ""}`;

  const jobs = result.jobs || [];
  sideTotal.textContent = String(jobs.length);
  sideTotalLabel.textContent = result.counts?.collected ? `de ${result.counts.collected} recolectadas` : "";

  // Excelentes/Buenas/Regulares/Bajas (Kevin's taxonomy) map onto our real
  // grades; Evaluadas is a different metric (made it to AI scoring at all),
  // not a grade tier — shown here because it's the fifth row of his spec.
  const gradeCounts = { "A+": 0, A: 0, B: 0, C: 0, D: 0 };
  jobs.forEach((scored) => { gradeCounts[scored.grade] = (gradeCounts[scored.grade] || 0) + 1; });
  const categories = [
    { name: "Excelentes", count: gradeCounts["A+"], from: "var(--green)", to: "var(--mint)" },
    { name: "Buenas", count: gradeCounts.A, from: "#59D9A0", to: "var(--mint)" },
    { name: "Regulares", count: gradeCounts.B, from: "var(--yellow)", to: "#F4A94B" },
    { name: "Bajas", count: gradeCounts.C + gradeCounts.D, from: "var(--red)", to: "#F4A0C8" },
    { name: "Evaluadas", count: result.counts?.ai_evaluated ?? 0, from: "var(--lavender)", to: "var(--lavender-soft)" },
  ];
  const maxCount = Math.max(1, ...categories.map((c) => c.count));
  sideCatBars.innerHTML = categories.map((c) => `
    <div class="cat-row">
      <span class="cat-dot" style="background:${c.from}"></span>
      <span class="cat-name">${c.name}</span>
      <div class="cat-track"><div class="cat-fill" style="background:linear-gradient(90deg,${c.from},${c.to});width:${(c.count / maxCount) * 100}%"></div></div>
      <span class="cat-count">${c.count}</span>
    </div>`).join("");

  const perSource = {};
  jobs.forEach((scored) => { perSource[scored.job.source] = (perSource[scored.job.source] || 0) + 1; });
  const sortedSources = Object.entries(perSource).sort((a, b) => b[1] - a[1]);
  if (sortedSources.length === 0) {
    sideSources.innerHTML = '<p class="status-meta">Sin fuentes con resultados.</p>';
  } else {
    Promise.all(sortedSources.map(([name, count]) =>
      sourceIconHtml(name).then((icon) => `
        <div class="source-row">${icon}<span class="source-name">${escapeHtml(name)}</span><span class="source-count">${count}</span></div>`)
    )).then((rows) => { sideSources.innerHTML = rows.join(""); });
  }
}

// ---- cards ----

function renderCard({ scored, isNew, action }) {
  const job = scored.job;
  const badges = [`<span class="grade-pill tone-${gradeTone(scored.grade)}">${escapeHtml(scored.grade)}</span>`];
  if (job.remote_status === "remote") badges.push('<span class="badge badge-remote">Remoto</span>');
  if (isNew) badges.push('<span class="badge badge-new">Nuevo</span>');
  if (action === "applied") badges.push('<span class="badge badge-applied">Aplicada</span>');
  if (action === "dismissed") badges.push('<span class="badge badge-dismissed">Descartada</span>');

  return `
    <article class="job-card${action === "dismissed" ? " is-dismissed" : ""}" data-signature="${escapeHtml(job.signature)}">
      <div class="job-card-top">${badges.join("")}</div>
      <h3 class="job-title">${escapeHtml(job.title)}</h3>
      <p class="job-meta">${escapeHtml(job.company)} · ${escapeHtml(job.source)} · ${formatAge(job.days_old)}</p>
      <p class="job-summary">${escapeHtml(scored.summary) || "Sin resumen de IA todavía."}</p>
      <div class="job-actions">
        <button type="button" class="details-btn" data-open-detail>Ver detalles <span class="arrow">&#8594;</span></button>
      </div>
    </article>`;
}

function renderResultsMeta(result) {
  if (!result) {
    resultsMeta.textContent = "";
    return;
  }
  const total = (result.jobs || []).length;
  const collected = result.counts && result.counts.collected;
  const parts = [`${total} vacante${total === 1 ? "" : "s"}`];
  if (collected) parts.push(`de ${collected} recolectadas`);
  const when = formatDateTime(result.finished_at);
  if (when) parts.push(when);
  resultsMeta.textContent = parts.join(" · ");
}

function applyFiltersAndRender() {
  const search = searchInput.value.trim().toLowerCase();
  const remoteOnly = remoteOnlyToggle.checked;
  const hideDismissed = hideDismissedToggle.checked;

  const visible = allJobs.filter(({ scored, action }) => {
    const job = scored.job;
    if (filters.grade && scored.grade !== filters.grade) return false;
    if (filters.source && job.source !== filters.source) return false;
    if (remoteOnly && job.remote_status !== "remote") return false;
    if (hideDismissed && action === "dismissed") return false;
    if (search && !`${job.title} ${job.company}`.toLowerCase().includes(search)) return false;
    return true;
  });

  // Already best-first from the pipeline's ranking — preserve that order.
  resultsGrid.innerHTML = visible.map(renderCard).join("");
  resultsEmpty.hidden = visible.length > 0;
  resultsEmpty.textContent = allJobs.length === 0
    ? "Todavía no hay vacantes para mostrar."
    : "Ninguna vacante coincide con estos filtros.";
}

// ---- detail modal ----

function findJobEntry(signature) {
  return allJobs.find((entry) => entry.scored.job.signature === signature);
}

function renderEvalBlock(evalLabel) {
  const label = evalLabel && evalLabel.label;
  const reason = evalLabel && evalLabel.reason;
  const reasonChips = EVAL_REASONS.map((r) => `
    <button type="button" class="eval-chip${reason === r.value ? " is-active" : ""}" data-eval-reason="${r.value}">${r.label}</button>
  `).join("");

  return `
    <div class="eval-block">
      <strong>¿Es una buena vacante?</strong>
      <div class="eval-buttons">
        <button type="button" class="btn-full ghost${label === "good" ? " is-active" : ""}" data-eval-label="good">Buena</button>
        <button type="button" class="btn-full ghost${label === "bad" ? " is-active" : ""}" data-eval-label="bad">Mala</button>
      </div>
      <div class="eval-reasons"${label === "bad" ? "" : " hidden"}>${reasonChips}</div>
    </div>`;
}

function renderModal(signature) {
  const entry = findJobEntry(signature);
  if (!entry) return;
  const { scored, action, evalLabel } = entry;
  const job = scored.job;

  const pros = (scored.pros || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const cons = (scored.contras || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("");

  modalBody.innerHTML = `
    <div class="modal-head">
      <div>
        <span class="grade-pill tone-${gradeTone(scored.grade)}">${escapeHtml(scored.grade)}</span>
        <h2>${escapeHtml(job.title)}</h2>
        <p class="meta">${escapeHtml(job.company)} · ${escapeHtml(job.source)} · ${formatAge(job.days_old)}</p>
      </div>
      <button class="modal-close" type="button" id="modalCloseBtn">&#10005;</button>
    </div>
    <div class="stat-tiles">
      <div class="stat-tile"><div class="val">${scored.final_score}</div><p class="lbl">Puntaje final</p></div>
      <div class="stat-tile"><div class="val">${scored.prefilter_score}</div><p class="lbl">Filtro</p></div>
      <div class="stat-tile"><div class="val">${scored.ai_evaluated ? scored.ai_score : "—"}</div><p class="lbl">IA</p></div>
    </div>
    <div class="summary-box">
      <strong>Resumen de IA</strong>
      <p>${escapeHtml(scored.summary) || "Esta vacante no llegó a evaluación de IA."}</p>
    </div>
    <div class="pc-grid">
      <div class="pc-col pros"><h4>Pros</h4><ul>${pros || '<li class="empty">Sin datos</li>'}</ul></div>
      <div class="pc-col cons"><h4>Contras</h4><ul>${cons || '<li class="empty">Sin contras detectadas</li>'}</ul></div>
    </div>
    ${renderEvalBlock(evalLabel)}
    <div class="modal-footer">
      <a class="btn-full primary" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">Abrir vacante &#8594;</a>
      <button type="button" class="btn-full ghost${action === "applied" ? " is-active" : ""}" data-modal-action="applied">Apliqué</button>
      <button type="button" class="btn-full ghost${action === "dismissed" ? " is-active" : ""}" data-modal-action="dismissed">No me interesa</button>
    </div>`;
}

function openModal(signature) {
  renderModal(signature);
  overlay.classList.add("open");
  overlay.dataset.signature = signature;
}
function closeModal() {
  overlay.classList.remove("open");
  overlay.dataset.signature = "";
}

resultsGrid.addEventListener("click", (event) => {
  const card = event.target.closest(".job-card");
  if (!card) return;
  openModal(card.dataset.signature);
});

modalBody.addEventListener("click", (event) => {
  if (event.target.closest("#modalCloseBtn")) {
    closeModal();
    return;
  }
  const actionBtn = event.target.closest("[data-modal-action]");
  if (actionBtn) {
    trackAction(overlay.dataset.signature, actionBtn.dataset.modalAction).then(() => {
      renderModal(overlay.dataset.signature); // reflect the new state without closing
    });
    return;
  }

  const evalLabelBtn = event.target.closest("[data-eval-label]");
  if (evalLabelBtn) {
    submitEvalLabel(overlay.dataset.signature, evalLabelBtn.dataset.evalLabel, null);
    return;
  }

  const evalReasonBtn = event.target.closest("[data-eval-reason]");
  if (evalReasonBtn) {
    submitEvalLabel(overlay.dataset.signature, "bad", evalReasonBtn.dataset.evalReason);
  }
});
overlay.addEventListener("click", (event) => { if (event.target === overlay) closeModal(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });

async function trackAction(signature, action) {
  const entry = findJobEntry(signature);
  if (entry) entry.action = action; // optimistic — the UI should react immediately
  applyFiltersAndRender();
  await fetch("/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ signature, action }),
  });
}

// Clicking "Mala" submits immediately (reason: null) so one click is always
// enough to label (charter: "a dozen or two jobs is enough" — keep it
// lightweight); picking a reason chip afterward just refines that same
// label, it never re-asks Kevin to choose before he can mark a job bad.
async function submitEvalLabel(signature, label, reason) {
  const entry = findJobEntry(signature);
  if (entry) entry.evalLabel = { label, reason }; // optimistic
  renderModal(signature);
  await fetch("/eval/label", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ signature, label, reason }),
  });
}

async function loadResults() {
  const [res, evalRes] = await Promise.all([fetch("/results"), fetch("/eval/labels")]);
  const data = await res.json();
  const evalLabels = await evalRes.json();
  const result = data.result;
  const tracking = data.tracking || {};
  const newSignatures = new Set((result && result.new_signatures) || []);

  allJobs = ((result && result.jobs) || []).map((scored) => ({
    scored,
    isNew: newSignatures.has(scored.job.signature),
    action: tracking[scored.job.signature] || null,
    evalLabel: evalLabels[scored.job.signature] || null,
  }));

  populateSourceDropdown();
  renderResultsMeta(result);
  renderSidebar(result);
  applyFiltersAndRender();
}

async function revealResults() {
  await loadResults();
  transitionToState("results");
}

[searchInput, remoteOnlyToggle, hideDismissedToggle].forEach((el) => {
  el.addEventListener("input", applyFiltersAndRender);
  el.addEventListener("change", applyFiltersAndRender);
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function init() {
  syncCheckbox(remoteOnlyToggle);
  syncCheckbox(hideDismissedToggle);
  connectEvents();
  try {
    const res = await fetch("/status");
    const data = await res.json();
    if (data.running) {
      showState("working");
      setProgress(0, "Reanudando…");
      return;
    }
    if (data.last && data.last.status === "success") {
      await loadResults();
      showState("results");
      return;
    }
    if (data.last && data.last.status === "error") {
      errorMessage.textContent = data.last.message || "Ocurrió un error inesperado.";
      showState("error");
      return;
    }
  } catch {
    // No /status yet (first run ever) — fall through to idle.
  }
  showState("idle");
}

startBtn.addEventListener("click", startRun);
retryBtn.addEventListener("click", startRun);
sideRerunBtn.addEventListener("click", startRun);
sideRerunBtn.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); startRun(); }
});

// "Limpiar caché" (EATP-019, Kevin's call): wipes collected/gated/results/
// dedup-cache/history/health data for a clean test run. Deliberately does
// NOT touch his applied/dismissed marks, his quality labels, or the Chrome
// login session — /reset (server.py) enforces that, this is just the UI.
async function clearCache(button) {
  const ok = window.confirm(
    "¿Borrar los datos de corridas anteriores?\n\n" +
    "Se borran las vacantes recolectadas, los resultados y el caché de " +
    "duplicados. NO se toca tu sesión de Chrome ni las vacantes que ya " +
    "marcaste como \"Apliqué\" / \"No me interesa\"."
  );
  if (!ok) return;

  button.disabled = true;
  try {
    const res = await fetch("/reset", { method: "POST" });
    if (res.status === 409) {
      window.alert("Hay una corrida en curso — esperá a que termine para limpiar el caché.");
      return;
    }
    window.location.reload();
  } finally {
    button.disabled = false;
  }
}

clearCacheBtn.addEventListener("click", () => clearCache(clearCacheBtn));
sideClearCacheBtn.addEventListener("click", () => clearCache(sideClearCacheBtn));
topRerunBtn.addEventListener("click", startRun);

init();
