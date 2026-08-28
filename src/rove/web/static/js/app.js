/* Rove — runner + results dashboard (EATP-015/016, v3 redesign).
 *
 * States: idle -> working -> (error | done -> results). "working" also
 * renders a dismissible notice banner for needs_intervention events (e.g. a
 * captcha on a browser-driven source) without leaving the working state,
 * because the run itself doesn't stop for those. No live source fires this
 * today (Indeed, the only one that did, was removed in EATP-033) — kept for
 * whichever future browser-driven source needs it. "done" holds briefly on
 * the checkmark, then fades
 * into "results" — one more state in this same machine, not a second page.
 *
 * EATP-020: on load, `init()` always lands on "idle" (unless a run is
 * genuinely in progress) instead of auto-jumping into last run's results —
 * Kevin wants to see and choose every time, never have the launcher decide
 * for him. "idle" shows "Ver dashboard de la última corrida" only when a
 * previous successful run actually exists.
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
const startFreshBtn = document.getElementById("startFreshBtn");
const viewLastBtn = document.getElementById("viewLastBtn");
const retryBtn = document.getElementById("retryBtn");
const freshRetryBtn = document.getElementById("freshRetryBtn");
const sideRerunBtn = document.getElementById("sideRerunBtn");
const topRerunBtn = document.getElementById("topRerunBtn");
const statusText = document.getElementById("statusText");
const barFill = document.getElementById("barFill");
const barPct = document.getElementById("barPct");
const noticeBanner = document.getElementById("noticeBanner");
const noticeText = document.getElementById("noticeText");
const cancelBtn = document.getElementById("cancelBtn");
const discardBtn = document.getElementById("discardBtn");
const errorMessage = document.getElementById("errorMessage");
const doneMessage = document.getElementById("doneMessage");

const resultsMeta = document.getElementById("resultsMeta");
const resultsGrid = document.getElementById("resultsGrid");
const resultsEmpty = document.getElementById("resultsEmpty");
const searchInput = document.getElementById("searchInput");

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
const sideViewCacheBtn = document.getElementById("sideViewCacheBtn");

// How long the "Listo" checkmark holds before fading into the dashboard.
const DONE_HOLD_MS = 1100;

// Grade -> pill color tier (the letter itself stays precise; only the tint groups).
const GRADE_TONE = { "A+": "good", A: "good", B: "mid", C: "low", D: "low" };

// Known platforms get their real brand mark (CC0 "Simple Icons", vendored in
// web/static/icons/); anything else falls back to a colored monogram —
// still distinct at a glance, no unofficial logo guessing.
const SOURCE_ICONS = {
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

// One entry per job accumulated in the inbox (EATP-031):
// { scored, bucket: 'hoy'|'ayer'|'esta_semana'|'mas_viejo', evalLabel: {label,reason}|null }
// An entry only ever exists here while it's unresolved — once Kevin applies
// or dismisses it, /inbox stops returning it at all.
const BUCKET_ORDER = ["hoy", "ayer", "esta_semana", "mas_viejo"];
const BUCKET_LABELS = { hoy: "Hoy", ayer: "Ayer", esta_semana: "Esta semana", mas_viejo: "Más viejo" };
let allJobs = [];
// Last run's /results payload, kept only for the sidebar's "last run"
// diagnostics line — re-used by trackAction so re-rendering the sidebar
// after a mark doesn't need a fresh network round-trip.
let lastResult = null;
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

// EATP-024: set the moment "Pausar"/"Cancelar" is clicked. The pipeline can
// take a while to actually stop (a captcha/login wait's poll loop, or up to
// ~3 min in the worst case mid-AI-retry — see cancellation.py), and it keeps
// publishing perfectly normal "working" progress events the whole time.
// Before this flag, those events reached `setProgress` same as any other and
// silently overwrote the "Cancelando…" message with the run's regular
// status text within a second or two — Kevin's exact report ("Pausar
// doesn't visibly do anything"): it did react, just for a moment too short
// to notice. Once set, every routine progress event is ignored until the
// run actually ends (the "error"/cancelled event below, which always clears
// it), so the message stays on screen for the whole wait instead of
// flickering back to normal.
let cancelling = false;

function handleEvent(event) {
  if (event.status === "needs_intervention") {
    notices[event.phase] = event.message;
    renderNotices();
    return;
  }

  // EATP-020: pairs with `needs_intervention` — published the moment the
  // collector confirms the captcha/login block is actually gone, so the
  // banner doesn't stay stuck until the next pipeline phase (which could be
  // minutes away, or after Kevin's already stopped watching).
  if (event.status === "intervention_resolved") {
    delete notices[event.phase];
    renderNotices();
    return;
  }

  if (event.phase === "error") {
    cancelling = false;
    notices = {};
    errorMessage.textContent = event.message || "Ocurrió un error inesperado.";
    showState("error");
    return;
  }

  if (event.phase === "persist" && event.status === "done") {
    cancelling = false;
    notices = {};
    doneMessage.textContent = event.message || "Listo";
    showState("done");
    window.setTimeout(revealResults, DONE_HOLD_MS);
    return;
  }

  if (cancelling) return;

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

async function startRun(resume = true) {
  // Kevin's call (2026-08-16): "Iniciar"/"Reanudar" always silently resumed
  // a leftover checkpoint, with no way to choose a clean run instead — the
  // "Empezar de nuevo" buttons pass resume=false, which pipeline.run()
  // already supported end to end (discards the checkpoint via
  // _clear_run_artifacts), just never reachable from the UI.
  cancelling = false;
  notices = {};
  renderNotices();
  showState("working");
  setProgress(0, resume ? "Iniciando…" : "Iniciando corrida limpia…");
  cancelBtn.disabled = false;
  discardBtn.disabled = false;
  connectEvents();
  await fetch("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume }),
  });
}

// Shared by "Pausar" (discard=false) and "Cancelar" (discard=true, EATP-024)
// — same stop mechanism server-side, the only difference is whether the
// checkpoint survives for the next "Iniciar" to resume into. The actual
// stop can take a few seconds to a few minutes (a captcha/login wait's poll
// loop, or a stuck/slow browser or AI call getting force-killed
// server-side) — the "error" event server.py's /cancel eventually triggers
// is what actually moves the UI out of "working"; this just gives immediate
// feedback that the click registered, and `cancelling` (see `handleEvent`)
// keeps that feedback visible for the whole wait instead of letting normal
// progress events overwrite it.
async function stopRun(discard) {
  cancelling = true;
  cancelBtn.disabled = true;
  discardBtn.disabled = true;
  statusText.textContent = discard ? "Cancelando (descartando avance)…" : "Cancelando…";
  await fetch("/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ discard }),
  });
}

async function cancelRun() {
  await stopRun(false);
}

async function discardRun() {
  await stopRun(true);
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

// ---- sidebar ----

function renderSidebar(inboxJobs, result) {
  if (!result) {
    sideStatusLine.textContent = "Sin corridas todavía";
    sideStatusLine.className = "status-line";
    sideStatusMeta.textContent = "";
  } else {
    const ok = result.status === "success";
    sideStatusLine.textContent = ok ? "✓ Corrida exitosa" : "✕ Corrida con errores";
    sideStatusLine.className = "status-line " + (ok ? "ok" : "err");

    const providers = Object.keys(result.ai_usage || {});
    const aiLine = providers.length
      ? `IA: <strong>${escapeHtml(providers.join(", "))}</strong> · ${result.counts?.ai_evaluated ?? 0} evaluadas en la última corrida`
      : "";
    sideStatusMeta.innerHTML = `${escapeHtml(formatDateTime(result.finished_at))}${aiLine ? "<br>" + aiLine : ""}`;
  }

  // EATP-031: everything below describes the accumulated inbox, not just
  // the last run — the number Kevin sees here must match what's in the grid.
  const jobs = inboxJobs.map((entry) => entry.scored);
  sideTotal.textContent = String(jobs.length);
  sideTotalLabel.textContent = "pendientes en tu bandeja";

  // Excelentes/Buenas/Regulares/Bajas (Kevin's taxonomy) map onto our real
  // grades; Evaluadas is a different metric (made it to AI scoring at all),
  // not a grade tier — shown here because it's the fifth row of his spec.
  const gradeCounts = { "A+": 0, A: 0, B: 0, C: 0, D: 0 };
  jobs.forEach((scored) => { gradeCounts[scored.grade] = (gradeCounts[scored.grade] || 0) + 1; });
  const evaluatedCount = jobs.filter((scored) => scored.ai_evaluated).length;
  const categories = [
    { name: "Excelentes", count: gradeCounts["A+"], from: "var(--green)", to: "var(--mint)" },
    { name: "Buenas", count: gradeCounts.A, from: "#59D9A0", to: "var(--mint)" },
    { name: "Regulares", count: gradeCounts.B, from: "var(--yellow)", to: "#F4A94B" },
    { name: "Bajas", count: gradeCounts.C + gradeCounts.D, from: "var(--red)", to: "#F4A0C8" },
    { name: "Evaluadas", count: evaluatedCount, from: "var(--lavender)", to: "var(--lavender-soft)" },
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

function renderCard({ scored }) {
  const job = scored.job;
  const badges = [`<span class="grade-pill tone-${gradeTone(scored.grade)}">${escapeHtml(scored.grade)}</span>`];
  if (job.remote_status === "remote") badges.push('<span class="badge badge-remote">Remoto</span>');
  if ((scored.flags || []).includes("confirm_english")) {
    badges.push('<span class="badge badge-confirm-english">Confirmar inglés</span>');
  }

  return `
    <article class="job-card" data-signature="${escapeHtml(job.signature)}">
      <div class="job-card-top">${badges.join("")}</div>
      <h3 class="job-title">${escapeHtml(job.title)}</h3>
      <p class="job-meta">${escapeHtml(job.company)} · ${escapeHtml(job.source)} · ${formatAge(job.days_old)}</p>
      <p class="job-summary">${escapeHtml(scored.summary) || "Sin resumen de IA todavía."}</p>
      <div class="job-actions">
        <button type="button" class="details-btn" data-open-detail>Ver detalles <span class="arrow">&#8594;</span></button>
      </div>
    </article>`;
}

function renderResultsMeta(inboxData, result) {
  // EATP-031: the headline number is the accumulated inbox total — how
  // many jobs are actually pending Kevin's decision, across every run he
  // hasn't caught up on yet. The last-run timestamp is still useful context
  // (when did this last refresh), so it stays as a secondary detail.
  const total = (inboxData && inboxData.total) || 0;
  const parts = [`${total} pendiente${total === 1 ? "" : "s"}`];
  const when = result && formatDateTime(result.finished_at);
  if (when) parts.push(`última corrida: ${when}`);
  resultsMeta.textContent = parts.join(" · ");
}

function applyFiltersAndRender() {
  const search = searchInput.value.trim().toLowerCase();

  const visible = allJobs.filter(({ scored }) => {
    const job = scored.job;
    if (filters.grade && scored.grade !== filters.grade) return false;
    // D is hidden unless Kevin explicitly picks it from the grade dropdown —
    // by definition a "bad match" grade, not worth cluttering the default
    // view with (EATP-020, Kevin's call).
    if (!filters.grade && scored.grade === "D") return false;
    if (filters.source && job.source !== filters.source) return false;
    if (search && !`${job.title} ${job.company}`.toLowerCase().includes(search)) return false;
    return true;
  });

  // EATP-031: section header per day-bucket (Hoy/Ayer/...), best-score-first
  // within each — /inbox already returns entries in that order.
  resultsGrid.innerHTML = BUCKET_ORDER.map((bucket) => {
    const items = visible.filter((entry) => entry.bucket === bucket);
    if (items.length === 0) return "";
    return `<h2 class="inbox-bucket-header">${BUCKET_LABELS[bucket]}</h2>` + items.map(renderCard).join("");
  }).join("");
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
  const { scored, evalLabel } = entry;
  const job = scored.job;

  const pros = (scored.pros || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const cons = (scored.contras || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("");

  // EATP-028/P27: an ambiguous English mention ("English required", "fluent")
  // keeps the job visible instead of dropping it — but Kevin still needs to
  // see exactly which phrase triggered it, to judge for himself.
  const confirmEnglish = (scored.flags || []).includes("confirm_english");
  const englishNotice = confirmEnglish
    ? `<div class="notice" style="margin-bottom:14px;">
         <span class="notice-icon">&#9888;</span>
         <p class="notice-text"><strong>Confirmar inglés:</strong> la vacante menciona inglés sin
           especificar el nivel — "${escapeHtml((job.english_evidence || []).join('", "'))}"</p>
       </div>`
    : "";

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
    ${englishNotice}
    <div class="pc-grid">
      <div class="pc-col pros"><h4>Pros</h4><ul>${pros || '<li class="empty">Sin datos</li>'}</ul></div>
      <div class="pc-col cons"><h4>Contras</h4><ul>${cons || '<li class="empty">Sin contras detectadas</li>'}</ul></div>
    </div>
    ${renderEvalBlock(evalLabel)}
    <div class="modal-footer">
      <a class="btn-full primary" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">Abrir vacante &#8594;</a>
      <button type="button" class="btn-full ghost" data-modal-action="applied">Apliqué</button>
      <button type="button" class="btn-full ghost" data-modal-action="dismissed">No me interesa</button>
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

// "Ver cacheadas" (EATP-029/P29): read-only view of the signature cache, in
// the same overlay/modal used for job details — different content, same
// close mechanics (#modalCloseBtn). Its own reset only clears this cache,
// never the broader "Limpiar caché" data (results/raw/history/health).
function renderCacheList(records) {
  if (!records.length) {
    return '<p class="empty">No hay vacantes cacheadas todavía.</p>';
  }
  return `<ul class="cache-list">${records.map((r) => `
    <li class="cache-row">
      <div class="cache-row-main">
        <strong>${escapeHtml(r.title || "(sin título)")}</strong>
        <span class="job-meta">${escapeHtml(r.company || "—")} · ${escapeHtml(r.source || "—")}</span>
      </div>
      <div class="cache-row-dates">
        <span>Visto: ${escapeHtml(r.first_seen)} → ${escapeHtml(r.last_seen)}</span>
      </div>
    </li>`).join("")}</ul>`;
}

async function renderCacheModal() {
  modalBody.innerHTML = `
    <div class="modal-head">
      <div><h2>Vacantes cacheadas</h2><p class="meta">Ocultas de corridas nuevas por hasta 30 días.</p></div>
      <button class="modal-close" type="button" id="modalCloseBtn">&#10005;</button>
    </div>
    <div id="cacheListBody"><p class="empty">Cargando...</p></div>
    <div class="modal-footer">
      <button type="button" class="btn-full ghost" data-cache-reset>Olvidar todas las cacheadas</button>
    </div>`;

  const res = await fetch("/cache");
  const data = await res.json();
  document.getElementById("cacheListBody").innerHTML = renderCacheList(data.records || []);
}

async function openCacheModal() {
  overlay.classList.add("open");
  overlay.dataset.signature = "";
  await renderCacheModal();
}

async function resetCache(button) {
  const ok = window.confirm(
    "¿Olvidar todas las vacantes cacheadas?\n\n" +
    "La próxima corrida podría volver a mostrar vacantes que ya viste. " +
    "Esto NO borra resultados, historial ni tus marcas de \"Apliqué\" / " +
    "\"No me interesa\" — solo el caché de duplicados."
  );
  if (!ok) return;

  button.disabled = true;
  try {
    const res = await fetch("/cache/reset", { method: "POST" });
    if (res.status === 409) {
      window.alert("Hay una corrida en curso — esperá a que termine.");
      return;
    }
    await renderCacheModal();
  } finally {
    button.disabled = false;
  }
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
  const cacheResetBtn = event.target.closest("[data-cache-reset]");
  if (cacheResetBtn) {
    resetCache(cacheResetBtn);
    return;
  }
  const actionBtn = event.target.closest("[data-modal-action]");
  if (actionBtn) {
    trackAction(overlay.dataset.signature, actionBtn.dataset.modalAction);
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
  // EATP-031: once Kevin applies or dismisses a job, /inbox stops returning
  // it entirely — so it drops out of the list here too, optimistically, and
  // the modal closes since there's nothing left to show for it. The sidebar
  // total/grade breakdown is derived from this same allJobs array, so it
  // has to be re-rendered here too — otherwise it goes stale the moment a
  // job disappears from the grid below it.
  allJobs = allJobs.filter((entry) => entry.scored.job.signature !== signature);
  applyFiltersAndRender();
  renderResultsMeta({ total: allJobs.length }, lastResult);
  renderSidebar(allJobs, lastResult);
  closeModal();
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

async function loadInbox() {
  // EATP-031: the job list itself comes from the accumulated inbox, not the
  // last run — /results stays around only for the sidebar's "last run"
  // diagnostics (date, AI providers, funnel counts).
  const [inboxRes, resultsRes, evalRes] = await Promise.all([
    fetch("/inbox"), fetch("/results"), fetch("/eval/labels"),
  ]);
  const inboxData = await inboxRes.json();
  const resultsData = await resultsRes.json();
  const evalLabels = await evalRes.json();
  const result = resultsData.result;
  lastResult = result;
  const buckets = inboxData.buckets || {};

  allJobs = BUCKET_ORDER.flatMap((bucket) =>
    (buckets[bucket] || []).map((item) => ({
      scored: item.scored,
      bucket,
      evalLabel: evalLabels[item.signature] || null,
    }))
  );

  populateSourceDropdown();
  renderResultsMeta(inboxData, result);
  renderSidebar(allJobs, result);
  applyFiltersAndRender();
}

async function revealResults() {
  await loadInbox();
  transitionToState("results");
}

searchInput.addEventListener("input", applyFiltersAndRender);

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
    viewLastBtn.hidden = !(data.last && data.last.status === "success");
    // A checkpoint means a run stopped mid-way (paused/crashed) — offer the
    // choice instead of "Iniciar" silently resuming it every time.
    startBtn.textContent = data.has_checkpoint ? "Reanudar búsqueda →" : "Iniciar búsqueda →";
    startFreshBtn.hidden = !data.has_checkpoint;
  } catch {
    // No /status yet (first run ever) — fall through to idle.
  }
  showState("idle");
}

startBtn.addEventListener("click", () => startRun(true));
startFreshBtn.addEventListener("click", () => startRun(false));
freshRetryBtn.addEventListener("click", () => startRun(false));
cancelBtn.addEventListener("click", cancelRun);
discardBtn.addEventListener("click", discardRun);
viewLastBtn.addEventListener("click", revealResults);
retryBtn.addEventListener("click", () => startRun(true));
sideRerunBtn.addEventListener("click", () => startRun(true));
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
sideViewCacheBtn.addEventListener("click", openCacheModal);
topRerunBtn.addEventListener("click", () => startRun(true));

init();
