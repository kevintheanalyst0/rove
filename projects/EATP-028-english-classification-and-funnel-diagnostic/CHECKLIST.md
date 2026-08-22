# EATP-028 — Checklist & time log

## Phases

- [ ] **Phase 1 — Split criteria.** Divide `[advanced_english]` in `criteria.toml`
      into explicit-reject vs. indeterminate tiers; update `AdvancedEnglish` model
      and `requires_advanced_english()` to return a 3-way classification +
      matched phrase instead of a bool.
- [ ] **Phase 2 — Wire through filters/scoring.** Update `quality/filters.py` and
      `scoring/validate.py` (and `prefilter.py` if needed) to handle the
      indeterminate path without dropping the job.
- [ ] **Phase 3 — Funnel diagnostic.** Add per-stage/per-source counters through
      the pipeline and surface them in the run result.
- [ ] **Phase 4 — UI.** "Confirmar inglés" tag + matched-phrase display.
- [ ] **Phase 5 — Search terms.** Add the expanded term list to `criteria.toml`.
- [ ] **Phase 6 — Tests & verify.** Cases for the previously-misclassified
      phrases; full pipeline run; `pytest` green.
- [ ] **Phase 7 — Close.** Update `ROADMAP.md`, `CHANGELOG.md`, commit.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| | | |

**Total: TBD**

## Session notes

(filled in at close)
