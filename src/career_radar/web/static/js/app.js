/* Career Radar — runner state machine (EATP-015).
 *
 * States: idle -> working -> (error | done). "working" also renders a
 * dismissible notice banner for needs_intervention events (e.g. LinkedIn
 * login) without leaving the working state, because the run itself doesn't
 * stop for those — the other sources keep going (see collectors/browser.py).
 */

const states = document.querySelectorAll(".state");
const startBtn = document.getElementById("startBtn");
const retryBtn = document.getElementById("retryBtn");
const statusText = document.getElementById("statusText");
const barFill = document.getElementById("barFill");
const barPct = document.getElementById("barPct");
const noticeBanner = document.getElementById("noticeBanner");
const noticeText = document.getElementById("noticeText");
const errorMessage = document.getElementById("errorMessage");
const doneMessage = document.getElementById("doneMessage");

// phase -> last intervention message still pending for that phase.
let notices = {};

function showState(name) {
  states.forEach((el) => el.classList.toggle("active", el.dataset.state === name));
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
      doneMessage.textContent = data.last.message || "Listo";
      showState("done");
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

init();
