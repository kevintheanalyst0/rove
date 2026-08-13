# EATP-015 — Web UI — backend + runner spinner — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Backend
- [x] FastAPI routes
- [x] background run task
- [x] SSE from event bus
- [x] status endpoint

### Phase 2 — Runner frontend
- [x] dots spinner
- [x] live status via SSE
- [x] calm error/paused/captcha states

### Phase 3 — Launch & close
- [x] one-click launch script
- [x] route/SSE tests
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Planificación + vista previa | ~30 min | Charter, vista previa interactiva del spinner (artifact) para validar el diseño antes de construir |
| 2026-08-12 17:43–17:56 | Fase 1-3 (build) | ~13 min | Backend, frontend, fuente, launch script, tests — incl. un bug real encontrado y corregido (ver notas) |
| 2026-08-12 17:57–18:18 | Prueba en vivo + rediseño | ~21 min | `scripts/run_web.sh` con corrida real de principio a fin (68 vacantes); rediseño a "Azul Ártico" (vidrio) a partir del feedback de Kevin, verificado con capturas de Playwright de los 4 estados |

**Total project time:** ~65 min

## Session notes
- Backend (`web/server.py`): `create_app()` factory (tests inject a private `EventBus` +
  fake `pipeline_run`, never the real pipeline). `POST /run` starts `pipeline.run()` on a
  background thread (one at a time, lock-guarded); `GET /events` streams the shared
  `EventBus` over SSE; `GET /status` reads `STATUS_FILE` + in-memory running flag.
- Frontend (`web/static/`): single-page app with a small CSS/JS state machine
  (`idle`/`working`/`error`/`done`) — explicit "Iniciar" button per Kevin, no auto-start.
  `needs_intervention` events (LinkedIn login) render as a dismissible banner *inside* the
  working state rather than a full state swap, since the run doesn't actually stop for
  those. Inter self-hosted (4 weights, vendored under `web/static/fonts/`, no CDN).
  Designed as the state machine EATP-016 extends with a `results` state — see both
  charters' "Key design decisions" for the runner→dashboard transition Kevin asked for.
- **Real bug found by the tests, not just a test artifact:** the original `/events`
  generator blocked a thread forever on `queue.get()` with no timeout — a client
  disconnecting mid-wait (normal during a long run) leaked that thread permanently, since
  a blocking call can't be cancelled from outside. Fixed with a polling timeout
  (`_EVENTS_POLL_SECONDS = 1.0`) so any leaked thread self-cleans within ~1s
  (CLAUDE.md golden rule 3). Verified end-to-end against a real uvicorn server (SSE
  genuinely streams incrementally, clean shutdown) since httpx's in-process ASGI
  transport — both `TestClient` and `AsyncClient` — fully drains a response body before
  returning it, which can't represent an intentionally infinite stream; the persisted
  test drives `_stream_events()` directly instead.
- `scripts/run_web.sh`: starts uvicorn, polls until it accepts connections, opens the
  URL via `explorer.exe` on WSL (falls back to `xdg-open`/`open`/Python `webbrowser`).
- 290/290 tests pass repo-wide; `ruff check` clean on the new files.
- **Palette changed mid-session:** Kevin tested `scripts/run_web.sh` live, disliked the
  flat violet/black look, and asked for something like Windows 7 Aero glass but modern
  (real blur/translucency + color, no bevels/gloss). Compared two directions (violet vs.
  blue) over a preview artifact; picked **"Azul Ártico"**. Rebuilt for real: frosted
  `.glass` panel (backdrop-filter blur+saturate, thin top highlight) floating over an
  animated blue/cyan blurred backdrop (`.backdrop`/`.blob`, drifts, frozen under
  `prefers-reduced-motion`). `docs/governance/DESIGN-SYSTEM.md` updated to match — its
  tokens and the "Glass surfaces" pattern are now the source of truth EATP-016 inherits
  for job cards. Verified visually with Playwright screenshots of all 4 states (not just
  code review) before calling it done.
- Also surfaced while watching that live run: Kevin now wants Indeed captchas to pause
  for manual resolution (like LinkedIn) instead of auto-retry-then-skip. Out of scope
  here (that's `collectors/indeed.py`, EATP-006) — logged in `ROADMAP.md` Backlog + memory
  for that session.
- **Closed on a real end-to-end run, not just fixtures:** `scripts/run_web.sh` → clicked
  "Iniciar" → full `thorough` run (all 10 sources, Indeed hit its captcha and was skipped
  per current behavior, LinkedIn ran clean) → `status: success`, **68 vacantes
  encontradas**, runner transitioned to "Listo" correctly.
