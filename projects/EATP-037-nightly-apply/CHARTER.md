# EATP-037 — Nightly browser-driven apply (Claude in Chrome)

> Status: **planned, nothing built.** Written 2026-11-22 from a planning conversation
> with Kevin so the design is not lost. Every item under "Unverified" below must be
> spiked before anything else is built.

## Objective
While Kevin sleeps, run Claude (headless `claude -p`, driving Kevin's **real,
signed-in Chrome** through the Claude in Chrome extension) on Kevin's PC and let it
apply to vacancies the way a person would:

1. **Rove's inbox** — vacancies Rove found but cannot auto-apply to (EATP-034/035
   only fill Greenhouse and Lever): OCC, Computrabajo and similar.
2. **A separate manual search** outside Rove — company career sites and job boards.

Anything it cannot finish goes to a review list inside Rove for Kevin. The run ends
with a summary pushed to Kevin's phone and the PC going back to sleep. A real browser
is used on purpose: headless/automated browsers are what bot protection stops.

Why now: Kevin needs a job urgently (admin scope widened in EATP-036) and applying by
hand is the bottleneck.

## Problems solved
New (not in the original P/R list): applications outside Greenhouse/Lever are manual;
Rove has no place to park vacancies that need Kevin (captcha, account, unknown question).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `docs/adr/ADR-011-auto-apply-draft-and-sweep.md` | Existing auto-apply design; do not duplicate it. |
| `src/rove/apply/store.py` | How applications are stored/deduplicated. |
| `src/rove/inbox/` | Where the inbox vacancies come from. |
| `src/rove/web/` | Where the review lists and the kill switch UI will live. |
| `docs/governance/CANDIDATE-PROFILE.md`, `criteria.toml`, `profile.toml` | What counts as a fit (and the EATP-036 exclusions). |
| Vigilante repo `docs/DESPERTAR-PC.md` (`kevintheanalyst0/vigilante-pc`) | The PC wake-up capability this depends on. |

## Dependencies
- **Projects:** EATP-034 and EATP-035 ✅ (done).
- **Other repo:** `vigilante-pc` — a wake-from-hibernation capability that does not
  exist yet (see its `docs/DESPERTAR-PC.md`).
- **Tools:** Pulse's usage endpoint for the quota guard; Claude in Chrome extension.

## Scope
**In:**
- Review lists in Rove: **skipped vacancies** and **pending questions**.
- Kill switch + settings stored in Rove (see below).
- A per-vacancy progress file written during the run.
- A PC-side wrapper script (plain code, zero tokens) that does preflight, batching,
  cleanup, summary and hibernate.
- The playbook prompt Claude follows, and the Windows scheduled task.
- A file of Kevin-written answers (`data/applicant_answers.toml`, gitignored).

**Out (do NOT build):**
- LinkedIn and Indeed automation, including email alerts: Kevin checks them by hand.
- Solving or bypassing captchas / anti-bot checks, ever.
- Typing passwords, creating site-specific accounts, entering verification codes.
- Editing Kevin's CV.

## Hard rules for the run
1. **Captcha or anti-bot check → skip the vacancy and log it** (`captcha`). Never solve it.
2. **No passwords, no site-specific account creation, no verification codes.** Those
   vacancies are logged (`account_required`). The only sign-in allowed is clicking
   "Continue with Google" and then Kevin's account in the chooser (explicit permission
   from Kevin, 2026-11-22). Stop and log if Google asks for a password or 2-step
   verification, or if the consent screen asks for more than basic profile/email.
3. **CV used verbatim**, never edited. Files: `D:\Descargas\CV´s\` (`CV_Kevin_Castillo_EN`
   and `Kevin_Castillo_CV_ES`, `.pdf` and `.docx`). The two PDFs are byte-identical to
   the ones in Kevin's Notion (SHA-256 compared 2026-11-22). Use the version in the
   vacancy's language. "Fill with resume" autofill is fine.
4. **Answers come only from the CV and `data/applicant_answers.toml`**, which Kevin
   writes himself. Direct factual questions — current employment status, availability /
   notice period, reasons for leaving, salary expectation, work authorization, English
   level — are answered **only** from that file, never inferred from the CV. If the
   answer is missing: log a pending question, skip the vacancy, do not invent.
   **"Are you currently employed / working?"** is answered only with the sentence Kevin
   confirmed is true on 2026-11-22: "I currently work independently on data analysis
   projects" (Spanish version in the answers file). Claude never names an employer, never
   writes "Audi" or any company as the current one, and never answers with a bare "yes".
   **Reason for leaving, notice period, employment gap and the name of any current employer
   are never answered by Claude** — Kevin handles those himself, face to face in interviews.
   If a form requires one of them, the vacancy goes to the skipped list
   (`employment_question`) for Kevin to answer. Approved values live in
   `data/applicant_answers.toml` (local to Kevin's PC checkout, gitignored): salary
   expectation 15,000 MXN/month, authorized to work in Mexico, English B2 (deliberately not
   C1: Kevin is out of practice and it would show), 4 years of experience (since 2022). If a
   form needs another currency or a yearly figure, log a pending question.
5. **Language follows the form**, Spanish or English, never mixed.
6. **Exclusions:** call center / customer support, sales, marketing, accounting/payroll,
   HR (EATP-036 list stays). Otherwise Kevin wants breadth, not selectivity: temporary
   contracts are fine, admin/procurement/logistics/data roles are all fair game.
7. **Skip companies that mass-post dozens of vacancies** (Kevin's rule: usually
   data-harvesting traps).
8. **A vacancy counts as applied only after the confirmation page is seen.** Never
   submit a half-filled form. On resume, check the store first so nothing is sent twice.

## Quota guard
- Read usage from `GET https://api.anthropic.com/api/oauth/usage` with the token the
  local `claude` CLI already caches (same call Pulse makes; Notion's laptop page
  documents it). Never print the token and never trigger a token refresh (that would
  spend a model call).
- Before **each batch**: stop **starting** new vacancies when the 5-hour session
  reaches **90 %** (finish the current one), and do not run at all when the weekly
  figure is above the **weekly cap (default 70 %, configurable)**.
- If usage cannot be read: **do not run**, notify Kevin (fail closed).
- Verified read, 2026-11-22 6:28 p. m. Mexico time: session 45 %, weekly 45 %; weekly
  reset Tue 2026-11-24 21:00 UTC (3:00 p. m. Mexico). Kevin's own framing: one or two
  5-hour windows per night is fine; weekly quota is routinely under-used.

## Kill switch (stored in Rove, read by the PC wrapper over Tailscale)
`enabled`, `skip_tonight` (clears itself after one night), `pause_until` (date) and
`weekly_cap_pct`. Visible and editable from the Rove dashboard on Kevin's phone.
**Fail closed:** if the wrapper cannot read it, it does not run and it notifies Kevin.

## Run structure
- Each batch is a separate `claude -p` session (fresh context, cheaper, failures don't
  chain). The wrapper decides between batches using the quota guard.
- Progress is written **per vacancy** (never only at the end). If tokens run out or the
  session dies, the in-flight vacancy stays `pending`, its tab is abandoned unsent, and a
  later run retries it.
- **Cleanup is done by the wrapper, not by Claude** (Claude may be out of tokens): close
  the Chrome window/tab group opened for the run, build the summary from the progress
  file, push it to Kevin's phone through Home Assistant, then hibernate.
- A second scheduled run later the same night picks up where the first stopped.

## Review lists in Rove
- **Skipped vacancies:** url, title, company, source, reason (`captcha`,
  `account_required`, `workday_or_similar`, `pending_question`, `mass_poster`, …), time.
- **Pending questions:** question text, vacancy, language. When Kevin answers, the answer
  is appended to `data/applicant_answers.toml` and the vacancy is requeued.

## PC wake-up
Provided by the Vigilante project (separate repo). Plan, verified findings and risks:
`docs/DESPERTAR-PC.md` there. Key fact as of 2026-11-22: **hibernation is not enabled
on Kevin's laptop** and waking from hibernation has never been tested.

## Known limitations
- Workday-style tenants need a per-company account with a password. Not automated; they
  land on the skipped list. Kevin believes many vacancies will be Workday — **measure the
  real share after the first nights** before deciding. **Kevin's decision (2026-11-22):** try it
  for a few days; if many vacancies turn out to be Workday he creates the accounts by hand,
  and if there are few he applies to them himself when he has time.
- Greenhouse boards often carry a reCAPTCHA on submit (EATP-034 sampled 8/8). With a real
  Chrome it may pass; if a checkbox appears, rule 1 applies.
- **OCC blocked Rove's automated browser** (Notion Rove page, 2026-08-31/09-01: HTTP 403
  "scraping abuse" before the page even loaded, harsher than Greenhouse's reCAPTCHA). That
  was a Playwright-style browser on the VM; Kevin's real signed-in Chrome is a different
  situation but **untested for OCC** — spike 5 decides whether the inbox half of this
  project is viable at all. Computrabajo and OCC did not block the Mexican IP itself
  (2026-08-26 spike).

## Unverified (spike first, in this order)
1. Whether `claude -p` can drive Chrome through the extension unattended (permission mode).
2. Whether Chrome stays usable with the Windows screen locked after waking.
3. Enabling hibernation and waking from it with a timer (Vigilante project).
4. That the usage endpoint keeps working (it is not a public API) — keep fixed per-run
   caps as a fallback.
5. OCC/Computrabajo application flows: captcha? account? — test with one vacancy, no submit.

## Deliverables
- Review lists + kill switch in Rove (API + dashboard), with tests (fixtures, no live AI).
- Wrapper script, playbook prompt, scheduled task, install notes.
- Updated docs: ROADMAP, CHANGELOG, this charter, Notion pages (Rove, Vigilante).

## Definition of Done
- [ ] Spikes 1–5 answered and recorded here
- [ ] Review lists and kill switch work from the phone
- [ ] Dry run (no submit), then a supervised real run, then an unattended night
- [ ] `pytest` green (fixtures, no live AI)
- [ ] No OOM/crash risk left
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10); Notion and the Vigilante repo in sync

## Estimated time
Not estimated yet. Expect several sessions: spikes, then Rove side, then the PC runner.

## Open questions for Kevin
- Answered 2026-11-22: salary, work authorization, English level, years of experience (stored in
  `data/applicant_answers.toml`). Employment-status questions are deliberately left to Kevin.
- Still open: whether the answers file should also be readable from the VM (where Rove's review
  lists will live) or only from the PC runner.
