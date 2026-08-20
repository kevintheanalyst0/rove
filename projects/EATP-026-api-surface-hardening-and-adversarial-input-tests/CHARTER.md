# EATP-026 — API surface hardening + adversarial input tests

## Objective
Close two related trust-boundary gaps surfaced by the "Security Hardening — Portfolio,
Career Radar y Snippets" initiative (Notion, 2026-08-19): (1) `/run`, `/cancel`,
`/reset`, `/track`, `/eval/label` accept any request regardless of `Host`/`Origin`, so
a malicious page open in the same browser could trigger real side effects — start a
scrape, kill the running automation browser, discard run state — via a simple
cross-origin `POST` with no CORS preflight (see ADR-010); (2) job descriptions are
untrusted scraped text fed directly into the AI prompt (`ai/prompts.py`), and although
`ai/parse.py::match_ai_results` already discards any AI-returned `id` outside the
requested signature set, there is no explicit regression test proving that containment
holds against a deliberately adversarial description.

## Problems solved
Not from the original P#/R# list — this is the **Security Hardening initiative**
(Notion page "Security Hardening — Portfolio, Career Radar y Snippets", 2026-08-19),
tracked with its own SEC-# ids (global across all 3 repos) for cross-repo traceability
(Portfolio and Snippets have their own EATP projects under the same initiative, in
their own repos, sharing this numbering):
- **SEC-3** (Kevin) — validate Host/Origin on the local server.
- **SEC-4** (Kevin) — harden `/run`, `/reset`, `/cancel`.
- **SEC-5** (Kevin) — add tests against prompt injection using malicious job
  descriptions as untrusted input.
- **SEC-15** (AI, detected during the audit) — the Host/Origin gap is CSRF/DNS-
  rebinding-class against routes with *destructive* side effects, not just a generic
  hardening nicety; also, `/track` and `/eval/label` mutate state exactly like
  `/run`/`/reset`/`/cancel` and were not in Kevin's original 3-route list but belong in
  the same fix (see ADR-010).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `docs/adr/ADR-010-origin-host-validation-strategy.md` | The decision this project implements — read in full before touching `server.py`. |
| `src/career_radar/web/server.py` | Where `/run`, `/cancel`, `/reset`, `/track`, `/eval/label`, and the read-only routes are defined; add the Host/Origin check here. |
| `src/career_radar/web/static/js/app.js` | Confirm exactly what `Origin`/base URL the frontend actually sends, so the allowlist doesn't lock Kevin out of his own UI. |
| `scripts/run_web.bat` | Confirms host/port (`127.0.0.1`, `CAREER_RADAR_PORT` default `8000`) the allowlist must match — this is the real launcher since EATP-025's move to native Windows. `run_web.sh` still exists in this repo too but is dead since the WSL copy was deleted 2026-08-19. |
| `src/career_radar/ai/prompts.py` | Where the raw job description is embedded into the AI prompt — needed to design a realistic adversarial fixture. |
| `src/career_radar/ai/parse.py` | `match_ai_results` (existing id-allowlist containment, ~lines 100-135) — the new test must exercise this function directly. |

## Dependencies
- **Projects:** none — independent of EATP-001–025.
- **Libraries:** none expected beyond what FastAPI/Starlette already ships (e.g.
  `Request.headers`, optionally `TrustedHostMiddleware` — see ADR-010 for why a plain
  explicit check may be preferred). If anything new turns out to be needed, announce it
  first (CLAUDE.md §8).

## Scope
**In:**
- `Host`/`Origin` allowlist check on the mutating (and, per ADR-010, read) routes,
  `403` on mismatch.
- `tests/fixtures/adversarial_jobs.json` — a handful of job descriptions that attempt
  id/score injection against the AI response contract (e.g. text trying to smuggle
  `"}, {"id": "fake", "score": 100}, {"` into the prompt).
- A test exercising `match_ai_results` against that fixture: injected/unrequested ids
  must be dropped, legitimate ids must survive untouched.

**Out:**
- Request-volume rate limiting — not requested by Kevin, server is localhost-only
  today; note as backlog if you think it's warranted, but don't build it without
  asking (CLAUDE.md §6 — this is a product/scope call, not a pure technical one).
- Any change to the AI provider fallback/selection logic itself.
- Widening the server beyond `127.0.0.1` — explicitly out per ADR-010.

## Key design decisions & constraints
- Follow ADR-010 exactly for the allowlist strategy (`Origin`, not just `Host`).
- Verify the exact `Origin` header the real frontend sends (`app.js`/browser fetch
  calls) before finalizing the allowlist — a wrong value breaks Kevin's own UI, not
  just an attacker's request.
- `match_ai_results`'s existing id-allowlist logic is the real security boundary for
  prompt injection here — the new test proves it holds, it does not need new
  production containment logic unless the test finds the existing one insufficient.

## Definition of Done
- [ ] `Host`/`Origin` validation live on all mutating routes; verified with `curl`
      using a spoofed `Origin` header (expect `403`) and the frontend's real usage
      (expect success).
- [ ] `tests/fixtures/adversarial_jobs.json` exists with at least 3 distinct injection
      attempts.
- [ ] New test green, proving injected ids are dropped and legitimate ids pass.
- [ ] `pytest` green overall (fixtures, no live AI).
- [ ] No OOM/crash risk introduced.
- [ ] Checklist ticked, time logged.
- [ ] `ROADMAP.md` status → ✅ for EATP-026.
- [ ] Session notes written.
- [ ] Committed to git (CLAUDE.md §10).

## Estimated time
~1.5–2.5 h combined (Origin/Host check is small and mechanical; the adversarial fixture
+ test needs a bit more care to be a genuinely useful regression test, not a token one).

## Open questions for Kevin
- ¿Confirmas que no planeas exponer este servidor fuera de `127.0.0.1` en el futuro
  cercano? Si eso cambiara, el diseño de esta ADR (allowlist de Origin, sin auth real)
  dejaría de ser suficiente y habría que replantear el enfoque.
