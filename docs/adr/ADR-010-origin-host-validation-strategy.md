# ADR-010 — Origin/Host validation strategy for the local server

- **Status:** Proposed (EATP-026 confirms/implements)
- **Date:** 2026-08-19
- **Context:** The web server binds only to `127.0.0.1` (`scripts/run_web.sh`), but that
  does **not** stop a malicious page open in the same browser from reaching it. Any tab
  can issue a simple cross-origin `POST` to `http://127.0.0.1:8000/run` (or `/cancel`,
  `/reset`, `/track`, `/eval/label`) with no CORS preflight, because the server currently
  has no `CORSMiddleware`, no `TrustedHostMiddleware`, and no explicit `Host`/`Origin`
  check at all (verified against `src/career_radar/web/server.py` during the Security
  Hardening audit, 2026-08-19). Several of these routes have real side effects: `/run`
  starts a scrape, `/cancel` kills the running automation browser mid-flight, `/reset`
  discards run state. This is a CSRF/DNS-rebinding-class gap — flagged by the AI during
  the audit as more urgent than the neutral wording of Kevin's original checklist item
  ("validar Host/Origin") suggests, precisely because of those destructive side effects.
- **Decision:** Validate both the `Host` **and** `Origin` headers on every mutating
  request (`/run`, `/cancel`, `/reset`, `/track`, `/eval/label`) against an explicit
  allowlist matching only what the local frontend actually uses (`127.0.0.1:<port>` and
  `localhost:<port>`, port from `CAREER_RADAR_PORT`/default `8000`). Reject with `403`
  otherwise. An explicit per-request check (or a small dependency) is preferred over
  Starlette's generic `TrustedHostMiddleware` alone, because `TrustedHostMiddleware`
  only checks `Host`, not `Origin` — and `Origin` is what actually distinguishes "this
  browser tab is talking to the server it thinks it is" from a cross-origin request, since
  `Host` is always `127.0.0.1` regardless of which page issued the request.
- **Consequences:**
  - Any future legitimate non-localhost use of the server (e.g. exposing it on the LAN)
    requires deliberately widening this allowlist — a conscious decision, not a silent
    gap re-opening itself.
  - `GET`-only read endpoints (`/status`, `/results`, `/eval/labels`, `/events`) may be
    validated the same way for a single source of truth (CLAUDE.md's "one source of
    truth" rule), even though they carry lower risk, rather than maintaining two
    different rules for what counts as a mutating route.
  - EATP-026 must confirm the allowlist matches exactly what `app.js`/the frontend HTML
    actually sends as `Origin` before shipping — a mismatch would lock Kevin out of his
    own UI.
- **Alternatives considered:**
  - **Rely on `127.0.0.1` binding alone** — rejected: doesn't stop same-machine
    cross-origin requests from another tab.
  - **Full auth/token system** — rejected as disproportionate for a personal,
    localhost-only tool, per the Security Hardening initiative's proportionality
    principle (Notion, "criterio general": reduce relevant risk, not "impossible to
    attack"). Revisit only if Kevin exposes this server beyond localhost.
  - **`TrustedHostMiddleware` only** — rejected: doesn't check `Origin`, so it would not
    actually block the cross-origin-POST scenario that motivates this ADR.
