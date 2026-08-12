# EATP-015 — Web UI — backend + runner spinner

**Complexity:** Medium

## Objective
Replace the terminal with a clean local web page: a FastAPI backend and a single-page frontend showing the Windows-style ring of moving dots plus one line of live Spanish status while a run works. This is the 'it's working…' experience Kevin sees.

## Problems solved
R11 (no terminal; spinner + status), R12 (one-click run).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules. |
| `docs/governance/DESIGN-SYSTEM.md` | Tokens + the dots-spinner spec + live status. |
| `docs/adr/ADR-004-web-ui-over-terminal.md` | Why FastAPI + SSE, not Streamlit. |
| `src/career_radar/pipeline.py` | The run() the server triggers (EATP-014). |
| `src/career_radar/events.py` | Progress events to stream via SSE (EATP-001). |
| `legacy/assets/style.css` | Reference: Kevin's dark/violet look. |

## Dependencies
- **Projects:** EATP-014.
- **Libraries:** fastapi, uvicorn[standard].

## Scope
**In:**
- web/server.py: FastAPI — serve the SPA, POST /run (background task), GET /events (SSE of progress), GET /status.
- web/static/: the runner state — the dots spinner + live status text subscribed to /events, plus calm error/paused/captcha states (incl. an Indeed-captcha prompt surfaced from the collector events).
- Self-hosted Inter font + assets (works offline; no runtime CDN).
- A one-click launch script that starts uvicorn and opens the browser (no terminal interaction).
- Smoke tests: routes respond; SSE emits events during a mock run.

**Out:**
- The results dashboard + tracking (016).
- Scheduling/notifications (018).

## Deliverables
- src/career_radar/web/server.py + web/static (runner)
- launch script
- route/SSE smoke tests

## Key design decisions & constraints
- SSE for live status (simple, instant, no terminal); fallback to polling status.json if needed.
- Manual interventions (Indeed captcha / LinkedIn login) appear as calm in-page prompts, never terminal input().
- No browser storage APIs; keep state server-side/in-memory.

## Definition of Done
- [ ] All deliverables exist and work
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left unaddressed
- [ ] Checklist fully ticked, time log finalized
- [ ] ROADMAP status -> Done (date + total time)
- [ ] Session notes written

## Estimated time
1 session (~2.5-3 h).

## Open questions for Kevin
- Want a thin progress bar during the AI stage (it has a known total), or just the spinner + text?
