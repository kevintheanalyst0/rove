# Design System — Web UI

For EATP-015 (runner) and EATP-016 (dashboard). Matches Kevin's established aesthetic: **dark theme, violet accent, Inter,
clean and minimal.** The UI has two states: the **runner** (working spinner + live
status) and the **results dashboard**.

## Tokens

```css
:root {
  /* Accent */
  --violet:        #6D3BF5;   /* primary accent (Kevin's signature) */
  --violet-soft:   #8A63F7;
  --violet-dim:    rgba(109, 59, 245, 0.14);

  /* Dark surfaces */
  --bg:            #0E0E12;   /* app background */
  --surface:       #16161D;   /* cards */
  --surface-2:     #1E1E27;   /* elevated / hover */
  --border:        #2A2A35;

  /* Text */
  --text:          #ECECF1;
  --text-muted:    #A0A0AE;
  --text-faint:    #6C6C7A;

  /* Grades */
  --grade-a:       #35C56A;   /* A+/A */
  --grade-b:       #C9B23A;   /* B */
  --grade-c:       #C97F3A;   /* C */
  --grade-d:       #8A8A96;   /* D */

  /* Status */
  --ok:            #35C56A;
  --warn:          #E0B341;
  --err:           #E5484D;

  --radius:        14px;
  --radius-sm:     9px;
  --shadow:        0 8px 30px rgba(0,0,0,0.35);
  --font:          'Inter', system-ui, -apple-system, sans-serif;
}
```

Typography: **Inter** (self-host the woff2 in `web/static/fonts/` — do not depend on a
CDN at runtime so it works offline). Weights 400/500/600/700. Generous line-height,
tight headings.

## The runner (Windows-style working spinner) — the P/R11 requirement

Kevin explicitly wants: no terminal; instead a web page with a **Windows-style ring of
moving dots** and a single line of status text telling him what stage it's in. This is
the primary UX during a run.

Requirements:
- A **circular spinner made of ~8 dots** that rotate/fade in sequence (the Windows boot
  look), centered, in violet.
- Below it, **one line of live status text** driven by the orchestrator's event bus,
  e.g. *"Buscando en Remotive…"*, *"Evaluando 24 vacantes con IA…"*,
  *"Filtrando remotas…"*. Spanish, present-tense, human.
- Optionally a thin progress bar for the AI stage (it has a known total).
- **No logs, no terminal output** on screen. Errors show as a calm message, not a stack
  trace.

Reference spinner (pure CSS, no JS animation library needed):

```html
<div class="cr-spinner" aria-label="Trabajando">
  <span></span><span></span><span></span><span></span>
  <span></span><span></span><span></span><span></span>
</div>
<p class="cr-status">Iniciando…</p>
```
```css
.cr-spinner { position: relative; width: 52px; height: 52px; margin: 0 auto; }
.cr-spinner span {
  position: absolute; top: 0; left: 50%; width: 6px; height: 6px; margin-left: -3px;
  border-radius: 50%; background: var(--violet);
  transform-origin: 3px 26px; opacity: 0;
  animation: cr-dot 1s linear infinite;
}
.cr-spinner span:nth-child(1){ transform: rotate(0deg);   animation-delay: 0.00s; }
.cr-spinner span:nth-child(2){ transform: rotate(45deg);  animation-delay: 0.12s; }
.cr-spinner span:nth-child(3){ transform: rotate(90deg);  animation-delay: 0.24s; }
.cr-spinner span:nth-child(4){ transform: rotate(135deg); animation-delay: 0.36s; }
.cr-spinner span:nth-child(5){ transform: rotate(180deg); animation-delay: 0.48s; }
.cr-spinner span:nth-child(6){ transform: rotate(225deg); animation-delay: 0.60s; }
.cr-spinner span:nth-child(7){ transform: rotate(270deg); animation-delay: 0.72s; }
.cr-spinner span:nth-child(8){ transform: rotate(315deg); animation-delay: 0.84s; }
@keyframes cr-dot { 0%{opacity:1} 100%{opacity:0.15} }
.cr-status { text-align:center; color: var(--text-muted); font: 500 14px var(--font); }
```

Live updates: the frontend subscribes to run progress via **Server-Sent Events**
(`/events`) or short polling of `status.json`. SSE is preferred (no terminal, instant
status). The status text comes straight from the orchestrator's event bus (EATP-001/014).

## The results dashboard

- A **grid of job cards**, best first. Each card: title, company, a **grade pill**
  (A+/A/B/C/D colored by token), true-remote badge, source, age, one-line summary, and
  an expander for pros/contras + apply button (opens the URL).
- **Filters:** grade, source, remote-only (on by default), search box.
- **Header:** last-run time, counts (collected → shown), AI provider used, a **Run**
  button that kicks off a run and flips the page to the runner state.
- Empty/paused/error states are calm and in Spanish.

Keep it single-viewport-friendly and uncluttered — Kevin's taste is minimal with
purposeful violet accents, not decoration for its own sake.
