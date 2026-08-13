/* Career Radar — runner + results dashboard (EATP-015/016).
 *
 * States: idle -> working -> (error | done -> results). "working" also
 * renders a dismissible notice banner for needs_intervention events (e.g.
 * LinkedIn login) without leaving the working state, because the run itself
 * doesn't stop for those — the other sources keep going (see
 * collectors/browser.py). "done" holds briefly on the checkmark, then fades
 * into "results" — the transition Kevin asked for while planning EATP-015,
 * built as one more state in this same state machine rather than a second
 * page (see EATP-016 CHARTER.md "Key design decisions").
 */

const mainEl = document.querySelector("main");
const states = document.querySelectorAll(".state");
const startBtn = document.getElementById("startBtn");
const retryBtn = document.getElementById("retryBtn");
const rerunBtn = document.getElementById("rerunBtn");
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
const gradeFilter = document.getElementById("gradeFilter");
const sourceFilter = document.getElementById("sourceFilter");
const remoteOnlyToggle = document.getElementById("remoteOnlyToggle");
const hideDismissedToggle = document.getElementById("hideDismissedToggle");

// How long the "Listo" checkmark holds before fading into the dashboard.
const DONE_HOLD_MS = 1100;

// phase -> last intervention message still pending for that phase.
let notices = {};

// One entry per job: { scored: <ScoredJob>, isNew: bool, action: 'applied'|'dismissed'|null }
let allJobs = [];

function showState(name) {
  states.forEach((el) => el.classList.toggle("active", el.dataset.state === name));
  mainEl.classList.toggle("wide", name === "results");
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
    mainEl.classList.toggle("wide", target === "results");
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

function gradeClass(grade) {
  return "grade-" + String(grade).toLowerCase().replace("+", "-plus");
}

function formatAge(daysOld) {
  if (daysOld === null || daysOld === undefined || daysOld >= 999) return "antigüedad desconocida";
  if (daysOld <= 0) return "hoy";
  if (daysOld === 1) return "ayer";
  return `hace ${daysOld} días`;
}

function renderCard({ scored, isNew, action }) {
  const job = scored.job;
  const pros = (scored.pros || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const contras = (scored.contras || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("");
  const expander = pros || contras
    ? `<details class="job-expander">
        <summary>Pros y contras</summary>
        ${pros ? `<ul class="job-pros">${pros}</ul>` : ""}
        ${contras ? `<ul class="job-contras">${contras}</ul>` : ""}
      </details>`
    : "";

  const badges = [`<span class="grade-pill ${gradeClass(scored.grade)}">${escapeHtml(scored.grade)}</span>`];
  if (job.remote_status === "remote") badges.push('<span class="badge badge-remote">Remoto</span>');
  if (isNew) badges.push('<span class="badge badge-new">Nuevo</span>');
  if (action === "applied") badges.push('<span class="badge badge-applied">Aplicada</span>');
  if (action === "dismissed") badges.push('<span class="badge badge-dismissed">Descartada</span>');

  return `
    <article class="job-card${action === "dismissed" ? " is-dismissed" : ""}" data-signature="${escapeHtml(job.signature)}">
      <div class="job-card-top">${badges.join("")}</div>
      <h3 class="job-title">${escapeHtml(job.title)}</h3>
      <p class="job-meta">${escapeHtml(job.company)} · ${escapeHtml(job.source)} · ${formatAge(job.days_old)}</p>
      ${scored.summary ? `<p class="job-summary">${escapeHtml(scored.summary)}</p>` : ""}
      ${expander}
      <div class="job-actions">
        <a class="btn btn-small" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">Abrir vacante</a>
        <button type="button" class="btn-ghost btn-small${action === "applied" ? " is-active" : ""}" data-action="applied">Apliqué</button>
        <button type="button" class="btn-ghost btn-small${action === "dismissed" ? " is-active" : ""}" data-action="dismissed">No me interesa</button>
      </div>
    </article>`;
}

function populateSourceFilter() {
  const sources = [...new Set(allJobs.map((entry) => entry.scored.job.source))].sort();
  const current = sourceFilter.value;
  sourceFilter.innerHTML = ['<option value="">Todas las fuentes</option>']
    .concat(sources.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`))
    .join("");
  sourceFilter.value = sources.includes(current) ? current : "";
}

function renderResultsMeta(result) {
  if (!result) {
    resultsMeta.textContent = "";
    return;
  }
  const total = (result.jobs || []).length;
  const collected = result.counts && result.counts.collected;
  const finishedAt = result.finished_at ? new Date(result.finished_at) : null;
  const parts = [`${total} vacante${total === 1 ? "" : "s"}`];
  if (collected) parts.push(`de ${collected} recolectadas`);
  if (finishedAt) parts.push(finishedAt.toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" }));
  resultsMeta.textContent = parts.join(" · ");
}

function applyFiltersAndRender() {
  const search = searchInput.value.trim().toLowerCase();
  const grade = gradeFilter.value;
  const source = sourceFilter.value;
  const remoteOnly = remoteOnlyToggle.checked;
  const hideDismissed = hideDismissedToggle.checked;

  const visible = allJobs.filter(({ scored, action }) => {
    const job = scored.job;
    if (grade && scored.grade !== grade) return false;
    if (source && job.source !== source) return false;
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

async function trackAction(signature, action) {
  const entry = allJobs.find((item) => item.scored.job.signature === signature);
  if (entry) entry.action = action; // optimistic — the buttons should react immediately
  applyFiltersAndRender();
  await fetch("/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ signature, action }),
  });
}

async function loadResults() {
  const res = await fetch("/results");
  const data = await res.json();
  const result = data.result;
  const tracking = data.tracking || {};
  const newSignatures = new Set((result && result.new_signatures) || []);

  allJobs = ((result && result.jobs) || []).map((scored) => ({
    scored,
    isNew: newSignatures.has(scored.job.signature),
    action: tracking[scored.job.signature] || null,
  }));

  populateSourceFilter();
  renderResultsMeta(result);
  applyFiltersAndRender();
}

async function revealResults() {
  await loadResults();
  transitionToState("results");
}

resultsGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const card = button.closest(".job-card");
  if (!card) return;
  trackAction(card.dataset.signature, button.dataset.action);
});

[searchInput, gradeFilter, sourceFilter, remoteOnlyToggle, hideDismissedToggle].forEach((el) => {
  el.addEventListener("input", applyFiltersAndRender);
  el.addEventListener("change", applyFiltersAndRender);
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function init() {
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
rerunBtn.addEventListener("click", startRun);

init();
