# EATP-026 — Checklist & time log

> Keep this updated live. Tick `[ ]` → `[x]` as you go. Record time per phase.

## Phases

### Phase 1 — Origin/Host validation
- [x] Confirm exact `Origin`/`Host` values the real frontend sends (`app.js`, browser
      fetch calls) against `127.0.0.1:<port>` / `localhost:<port>`. — all `fetch()`
      calls in `app.js` use relative URLs; launcher always opens
      `http://127.0.0.1:8000/`.
- [x] Implement the allowlist check per ADR-010 on `/run`, `/cancel`, `/reset`,
      `/track`, `/eval/label`. **Scope refined from the charter**: deliberately NOT
      applied to GET routes — the browser's default same-origin policy (no
      `Access-Control-Allow-Origin` header is ever set here) already blocks a
      cross-origin page from reading their JSON response, so an extra check there
      would guard against something already blocked. Discussed and approved by Kevin
      in the planning step.
- [x] `curl`-verify: spoofed `Origin` → `403` (confirmed); real frontend usage →
      `200`/`409` as normal (confirmed, both via `TestClient` and a real `uvicorn`
      process on a throwaway port); no-`Origin` request → allowed (confirmed); spoofed
      `Host` → `403` (confirmed); `GET /status` unaffected by a hostile `Origin`
      (confirmed, still `200`).

### Phase 2 — Adversarial prompt-injection test
- [x] Write `tests/fixtures/adversarial_jobs.json` (3 distinct injection attempts:
      extra fabricated result, duplicate-id score inflation, malformed wrapper with
      injected markup).
- [x] Write tests exercising `ai/parse.py::match_ai_results` against the fixture
      (`test_adversarial_injection_is_contained`, parametrized) plus two direct unit
      tests that were missing from the suite entirely
      (`test_match_ai_results_drops_id_not_in_requested_jobs`,
      `test_match_ai_results_drops_ambiguous_duplicate_entirely`).
- [x] Confirm injected/unrequested ids are dropped, legitimate ids survive — all
      3 parametrized cases pass.
- [x] Side effect of Phase 1: `TestClient` in `test_web_server.py`/
      `test_web_dashboard.py` needed `base_url="http://127.0.0.1:8000"` so its default
      `Host: testserver` didn't trip the new origin check — fixed in the two shared
      `_make_client()` helpers, not per-test.

### Phase 3 — Verify & close
- [x] `pytest` green — 400 passed (was 381 before this project; +19 new tests).
- [x] `ruff check` on all touched files: 2 pre-existing issues in `server.py`
      unrelated to this change (confirmed via `git stash` diff — same 2 findings on
      `main` before EATP-026), nothing new introduced.
- [x] Update ROADMAP status + total time
- [x] Write session notes below
- [x] Commit to git (CLAUDE.md §10) — one commit, clear message

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-19 | 1 — Origin/Host validation | ~30 min | Includes real-uvicorn curl verification, not just TestClient. |
| 2026-08-19 | 2 — Adversarial fixture + tests | ~35 min | Also added 2 unit tests for match_ai_results paths (unrequested id, duplicate id) that had no direct coverage before. |
| 2026-08-19 | 3 — Verify & close | ~15 min | Full suite + ruff on touched files. |

**Total project time:** ~1h20

## Session notes
Origin/Host validation landed on the 5 mutating POST routes only
(`/run`,`/cancel`,`/reset`,`/track`,`/eval/label`) — deliberately narrower than
ADR-010's "may extend to GET too": the browser's own same-origin policy already blocks
a cross-origin page from reading a GET's JSON response with no CORS headers set, so
extending the check there would guard against something already blocked. Discussed
with Kevin during planning; he approved this refinement.

`match_ai_results`'s existing signature-allowlist (ADR-006) held against all 3
adversarial cases with zero production changes needed — the containment was already
correct, this project only proved it and locked it in with tests + a reusable
`tests/fixtures/adversarial_jobs.json`.

One environment gotcha worth remembering for future web-server work: `TestClient`'s
default `Host: testserver` will now trip `_verify_same_origin` unless `base_url` is
set to `http://127.0.0.1:8000` — already fixed in both `_make_client()` helpers, so
new tests using them don't need to think about it.

