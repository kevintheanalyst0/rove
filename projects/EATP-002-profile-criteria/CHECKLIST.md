# EATP-002 — Candidate profile & evaluation criteria — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Profile
- [x] profile file
- [x] profile.py loader

### Phase 2 — Criteria
- [x] criteria file (exclusions, english, remote signals, weights, floors, on-site tolerance)
- [x] criteria.py loader

### Phase 3 — Tests & close
- [x] test_criteria.py on fixtures
- [x] pytest green
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Phases 1-3 | ~6 min | profile.toml/criteria.toml + loaders + classify_remote + 19 new tests. |

**Total project time:** ~6 min (08:25-08:31, 2026-08-12)

## Session notes
- Kevin confirmed on-site tolerance default: up to ~1 day/month still counts as remote
  (`max_onsite_days_per_month = 1` in `criteria.toml`); more frequent = hybrid/reject.
- **Correction round 1 (Kevin)**: the legacy system was too rigid about what counted as a
  good match. Ambiguous title words get a rescue-word exception rather than a blanket
  keyword ban.
- **Correction round 2 (Kevin, same session, post-close)**: even the rescue-word mechanism
  was still a **title-only hard reject**, and that's exactly what buried a genuinely great
  legacy vacancy titled "Analista administrativo" — Kevin only found it by manually
  checking the cache in VS Code. Mirror risk: a "Data Analyst" title can hide a
  Linux/frontend/DBA-heavy job. Fix applied: `title_is_rejected()` now hard-rejects on
  ONLY the small `excluded_title_keywords` categories where no description could change
  the verdict (designer, sales, marketing, recruiting, legal, health, education, ...).
  The old `conditional_title_rules` mechanism was renamed to `title_caution_words` /
  `title_caution_flags()` and is now **advisory only** — ambiguous words
  (administrator/engineer/developer/manager/security/financial analyst/...) flag a job for
  the matcher (EATP-013, which reads full text) to weigh, but never block it from being
  read. Both corrections are saved to memory for EATP-009/013.
- Used TOML (stdlib `tomllib`) instead of YAML — no new dependency needed, per charter's
  preference.
- `classify_remote()` distinguishes `HYBRID` (partial: weekly on-site, monthly beyond
  tolerance, or an explicit "híbrido" phrase) from `ONSITE` (bare "presencial"/"onsite"
  phrase, no remote component) — both still fail the remote hard-gate in EATP-009, but
  the distinction is preserved for UI auditability per `DATA-CONTRACTS.md`.
- `title_is_rejected`/`requires_advanced_english`/`classify_remote`/`title_caution_flags`
  are pure functions on text — EATP-009 wires them into the actual collect->gate pipeline
  against real `Job`s; EATP-013's matcher/AI is where full-description judgment (including
  caution flags and the "friendly title hiding an off-field job" case) actually lives.
- 54/54 tests green (34 from EATP-001 + 20 new), `ruff check` clean. Next: EATP-003
  (collector framework & plumbing).
