# Design System — Web UI

For EATP-015 (runner) and EATP-016 (dashboard). Matches Kevin's established aesthetic:
**"Azul Ártico" — frosted glass over an animated blue/cyan backdrop, Inter, clean and
minimal.** Superseded the original flat violet-on-black look after Kevin saw it live in
EATP-015 and asked for something with the *feel* of Windows 7 Aero glass — real blur and
translucency, more color — without looking dated (no bevels, no glossy skeuomorphic
buttons, no gradient title bars). Confirmed 2026-08-12 from a two-direction preview
(violet vs. blue); blue won. The UI has two states: the **runner** (working spinner +
live status) and the **results dashboard**.

## Tokens

```css
:root {
  /* Backdrop — the animated color the glass sits over */
  --bg-a:          #071A33;
  --bg-b:          #030B18;
  --blob-1:        #2E6BFF;
  --blob-2:        #22D3EE;
  --blob-3:        #0EA5A0;

  /* Accent (gradient, not a flat color — used for buttons, spinner, progress) */
  --accent-1:      #38BDF8;
  --accent-2:      #22D3EE;

  /* Glass surface */
  --glass-tint:    rgba(20, 60, 100, 0.32);
  --glass-border:  rgba(255, 255, 255, 0.20);

  /* Text */
  --text:          #F5F6FA;
  --text-muted:    rgba(245, 246, 250, 0.70);
  --text-faint:    rgba(245, 246, 250, 0.46);

  /* Grades — semantic, not brand color; unchanged by the glass rework */
  --grade-a:       #35C56A;   /* A+/A */
  --grade-b:       #C9B23A;   /* B */
  --grade-c:       #C97F3A;   /* C */
  --grade-d:       #8A8A96;   /* D */

  /* Status */
  --ok:            #3ED598;
  --warn:          #FFC857;
  --err:           #FF6B6B;

  --radius:        26px;
  --radius-sm:     14px;
  --font:          'Inter', system-ui, -apple-system, sans-serif;
}
```

Typography: **Inter** (self-host the woff2 in `web/static/fonts/` — do not depend on a
CDN at runtime so it works offline). Weights 400/500/600/700. Generous line-height,
tight headings.

## Glass surfaces — the core visual pattern

Every panel (runner card, dashboard job cards in EATP-016) is a **frosted glass** surface
floating over the animated backdrop, not a flat `--surface` fill:

```css
.glass {
  background: var(--glass-tint);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  box-shadow:
    0 24px 60px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.35),  /* thin top highlight = the "glass" read */
    inset 0 0 60px rgba(255, 255, 255, 0.03);
}
```

The backdrop itself is a dark radial gradient (`--bg-a` -> `--bg-b`) with 2-3 large,
heavily blurred, slowly drifting circles (`filter: blur(70px)`, ~16s ease-in-out
alternate) in `--blob-1/2/3` — this is what the glass panel is translucent *against*;
without it the blur has nothing colorful to pick up and just looks like dim grey glass.
Freeze the drift under `prefers-reduced-motion: reduce`. Buttons and the progress bar
use the `--accent-1 -> --accent-2` gradient, not a flat color, to stay consistent with
the same "glass with color behind it" idea. See `src/rove/web/static/css/style.css`
(EATP-015) for the reference implementation.

## The runner (Windows-style working spinner) — the P/R11 requirement

Kevin explicitly wants: no terminal; instead a web page with a **Windows-style ring of
moving dots** and a single line of status text telling him what stage it's in. This is
the primary UX during a run.

Requirements:
- A **circular spinner made of ~8 dots** that rotate/fade in sequence (the Windows boot
  look), centered, in the `--accent-1 -> --accent-2` gradient, sitting inside the glass
  panel (see "Glass surfaces" above) — not directly on the flat background.
- Below it, **one line of live status text** driven by the orchestrator's event bus,
  e.g. *"Buscando en Remotive…"*, *"Evaluando 24 vacantes con IA…"*,
  *"Filtrando remotas…"*. Spanish, present-tense, human.
- A thin progress bar for the AI stage (confirmed with Kevin over the EATP-015 preview —
  he liked ring + text + bar together, not the ring alone).
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
.cr-spinner { position: relative; width: 54px; height: 54px; margin: 0 auto; }
.cr-spinner span {
  position: absolute; top: 0; left: 50%; width: 7px; height: 7px; margin-left: -3.5px;
  border-radius: 50%; background: linear-gradient(120deg, var(--accent-1), var(--accent-2));
  transform-origin: 3.5px 27px; opacity: 0;
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
.cr-status { text-align:center; color: var(--text); font: 500 14.5px var(--font); }
```

Live updates: the frontend subscribes to run progress via **Server-Sent Events**
(`/events`) or short polling of `status.json`. SSE is preferred (no terminal, instant
status). The status text comes straight from the orchestrator's event bus (EATP-001/014).

A `needs_intervention` event (captcha/login) renders as a calm banner *inside* the
working glass panel rather than swapping to a whole different state — the run doesn't
actually stop for one source while it waits, so the UI shouldn't look like it did.

## The results dashboard

- A **grid of job cards**, best first, each card its own glass panel over the same
  animated backdrop. Card contents: title, company, a **grade pill** (A+/A/B/C/D colored
  by token — grade colors stay semantic, unchanged by the glass rework), true-remote
  badge, source, age, one-line summary, and an expander for pros/contras + apply button
  (opens the URL).
- **Filters:** grade, source, remote-only (on by default), search box.
- **Header:** last-run time, counts (collected → shown), AI provider used, a **Run**
  button that kicks off a run and flips the page to the runner state.
- Empty/paused/error states are calm and in Spanish.

Keep it single-viewport-friendly and uncluttered — Kevin's taste is minimal with
purposeful violet accents, not decoration for its own sake.
