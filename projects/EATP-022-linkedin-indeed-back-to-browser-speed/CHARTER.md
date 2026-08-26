# EATP-022 — LinkedIn & Indeed: close the speed gap with legacy

## Objective
Kevin ran the original legacy project directly (2026-08-15, `/mnt/d/Development/JobMatchEngine`)
to check a claim from EATP-019: computrabajo + indeed + linkedin + AI analysis finished in
~5 minutes with 62 real jobs. Our current system's equivalent (LinkedIn+Indeed alone) takes
~13-14 minutes. Kevin asked to close that gap for LinkedIn and Indeed specifically — OCC and
Computrabajo stay as-is (already fast, not in question).

## Problems solved
New (2026-08-15), directly from Kevin's side-by-side legacy comparison. Corrects a stale
finding from EATP-019 Phase 6 (see Diagnosis) and extends P13 (run speed).

## Diagnosis (live-verified 2026-08-15, don't re-derive)
- **LinkedIn's "AI job search" redesign has been reverted (or was a temporary A/B test) since
  EATP-019 Phase 6 (2026-08-13).** Live-tested just now against `https://www.linkedin.com/jobs/search/`
  using rove's own existing isolated profile (`data/browser_profile/`, not Kevin's
  personal Chrome) — the page stayed on `/jobs/search/` (no redirect to the broken
  `/jobs/search-results/` UI) and served the classic markup (`data-occludable-job-id` present,
  real job ids). **This was not a profile-trust issue — our own safe, isolated profile sees the
  working page today.** EATP-019's finding was accurate for its moment; it just went stale and
  nobody re-checked before EATP-019/020/021 built the whole guest-HTTP-endpoint workaround on
  top of it. Confirmed independently by Kevin's own legacy run pulling 28 real, fresh LinkedIn
  jobs (real titles/companies/recent post times) through the exact same kind of real-browser
  scraping.
- Legacy's `indeed.py` (`/mnt/d/Development/JobMatchEngine/jobmatch/collectors/indeed.py`):
  2 parallel **search** tabs (we run search single-tab sequential today) + 3 detail tabs
  (matches what EATP-021 already set), and much tighter pacing (`random_sleep(0.2, 0.4)` /
  `(0.8, 0.8)` between navigations) vs. our `browser.human_pause(1.5, 4.0)` default. Indeed
  itself was never "broken" like LinkedIn — just slower than it needs to be, and legacy's own
  captcha handling was a blocking `input()` anti-pattern we deliberately fixed in EATP-006/019/020
  and must NOT bring back — only the tab-count/pacing numbers are worth adopting.
- Real numbers to beat (EATP-021's last measurements): LinkedIn ~580s/88 jobs, Indeed
  ~214-380s/33-36 jobs (214s when no captcha hit, ~380s when one does).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules (always). |
| `legacy/jobmatch/collectors/linkedin.py` + `legacy/jobmatch/collectors/linkedin_api.py` | The real-browser search logic to port back (scrolling, card extraction, multi-tab). |
| `/mnt/d/Development/JobMatchEngine/jobmatch/collectors/indeed.py` | Legacy's actual tab-count/pacing numbers (the original project, not the copy under `legacy/` — same content, referenced live during diagnosis). |
| `src/rove/collectors/linkedin.py` + `linkedin_api.py` | Current HTTP-guest-endpoint implementation — being replaced for listing, detail-fetch stays. |
| `src/rove/collectors/indeed.py` | Current browser-based implementation — tab count/pacing being tuned, captcha UX staying as-is. |
| `src/rove/collectors/browser.py` | Shared browser launch/profile/pacing helpers. |
| `docs/adr/ADR-009-title-is-a-signal-not-a-verdict.md`, `docs/governance/SCRAPING-GOTCHAS.md` | Constraints that still apply regardless of which approach fetches the page. |
| `projects/EATP-019-post-launch-fixes/CHECKLIST.md` (Phase 6) | Why the guest-endpoint rewrite happened — read so the new LinkedIn code doesn't reintroduce solved problems (captcha/login-wall handling, account-ban avoidance). |

## Dependencies
- **Projects:** EATP-021 (done — this replaces the guest-endpoint approach it tuned).
- **Libraries:** none new — same DrissionPage/browser stack already in use for Indeed.

## Scope
**In:**
1. **LinkedIn**: bring back real-browser listing (multi-tab search + result-panel scrolling,
   adapted from `legacy/jobmatch/collectors/linkedin.py`), replacing the guest-HTTP listing
   phase. Detail-fetch stays on the fast, safe guest HTTP endpoint (`linkedin_api.py`, unchanged
   — it was never the bottleneck). Must keep: non-blocking captcha/login-wall event handling
   (never `input()`), the account-safety posture from EATP-005/019 (single logged-in profile,
   not Kevin's personal Chrome), title/English/remote gating happening downstream in
   `quality/filters.py` (not re-inlined into the collector). Must NOT reintroduce: the old
   ADR-009 violations, hardcoded `remote=True`, or any gate logic legacy had inline.
2. **Indeed**: parallelize search-id collection across 2 tabs (currently single-tab sequential);
   tighten `human_pause()` defaults or add a faster pacing tier specifically for Indeed's
   navigation, closer to legacy's 0.2-0.8s — tuned live, not copied blindly (our current 1.5-4s
   was a deliberate choice, revisit with evidence). Detail tabs stay at 3 (EATP-021). Captcha UX
   (non-blocking event + `intervention_resolved`) stays exactly as EATP-020/021 built it.
3. Verify live: real run timing for both, before/after, same rigor as EATP-020/021 (no guessing).

**Out:** OCC, Computrabajo, AI evaluation phase (Kevin confirmed these stay as-is); reverting
Indeed's captcha handling to legacy's blocking design; using Kevin's personal Chrome profile
(not needed — our own isolated profile already works).

## Deliverables
- `linkedin.py`: real-browser listing restored, HTTP detail-fetch kept, tests updated
  (mocked browser interactions, no live network in CI).
- `indeed.py`: 2-tab search + tuned pacing, tests updated.
- Live before/after timing for both.

## Key design decisions & constraints
- Don't blindly copy legacy — port the *site knowledge* (tab counts, pacing numbers, scrolling
  technique) into the current architecture's conventions (Job model, quality-gate boundary,
  event-bus progress/intervention reporting, testability with injected fakes). Same discipline
  CLAUDE.md golden rule 12 already states.
- If LinkedIn's classic UI breaks again in the future, the guest-HTTP-endpoint code being
  replaced here is preserved in git history — not lost, just not the active path.

## Definition of Done
- [ ] Deliverables above exist and work
- [ ] `pytest` green (fixtures, no live AI, no live browser in CI)
- [ ] No OOM/crash risk left
- [ ] Checklist ticked, time logged
- [ ] ROADMAP status → ✅
- [ ] Session notes written
- [ ] Committed to git (CLAUDE.md §10)

## Estimated time
~2-3h (LinkedIn's rewrite is the bulk of it; Indeed is a smaller tuning pass).

## Open questions for Kevin
- None outstanding — scope confirmed directly in conversation (OCC/Computrabajo untouched,
  LinkedIn+Indeed only, keep current captcha UX, verify live).
