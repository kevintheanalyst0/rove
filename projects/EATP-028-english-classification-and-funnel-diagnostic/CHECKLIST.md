# EATP-028 — Checklist & time log

## Phases

- [x] **Phase 1 — Split criteria.** `criteria.toml`'s `[advanced_english]` renamed
      to `[english_requirement]`, split into `reject_phrases`/`reject_regex`
      (explicit C1/C2/native/bilingual) and `indeterminate_phrases`/
      `indeterminate_regex` (ambiguous — "English required", "professional
      English", "fluent", "dominio del inglés", etc.). `models.py` gets a new
      `EnglishRequirement` enum (`compatible`/`indeterminate`/`reject`);
      `Job.english_required: bool` replaced with `english_requirement` +
      `english_evidence: list[str]` (same shape as `remote_status`/
      `remote_evidence`). `criteria.py`: `AdvancedEnglish` →
      `EnglishRequirementCriteria`; `requires_advanced_english()` →
      `classify_english_requirement_with_evidence()`, mirroring
      `classify_remote_with_evidence`'s reject-overrides-indeterminate shape.
- [x] **Phase 2 — Wire through filters/scoring.** `quality/filters.py`: only
      `REJECT` hard-gates now; `INDETERMINATE` is kept, job carries the
      classification + evidence. `scoring/evaluate.py`: new `_initial_flags()`
      seeds `confirm_english` on every `ScoredJob` for an indeterminate job —
      both AI-evaluated (`_assemble`) and AI-cap-deferred (`build_deferred`)
      paths, so the flag never depends on the AI actually running.
      `scoring/validate.py`: the Layer-4 demotion re-check now only fires on
      `REJECT` — `INDETERMINATE` never auto-penalizes a high AI score
      (that was the entire point of this project).
- [x] **Phase 3 — Funnel diagnostic.** Added `RunResult.funnel` and
      `_Checkpoint.funnel`: `{source: {rejection_reason: count}}`, tallied in
      `pipeline.py::_gate_stage` from `gate_result.rejected` (reuses the exact
      reason strings `quality/filters.py` already produces — no new tracking
      invented). Wired through `_persist()` into the final `RunResult`.
- [x] **Phase 4 — UI.** `app.js::renderCard` shows a "Confirmar inglés" badge
      (new `.badge-confirm-english` CSS rule) when `scored.flags` includes
      `confirm_english`; `renderModal` shows the exact matched phrase(s) from
      `job.english_evidence` in a notice box (reused the existing `.notice`
      style already used for the intervention banner, no new component).
- [x] **Phase 5 — Search terms.** **Correction to the charter:** these live in
      `config.py`'s `SEARCH_TERMS`/`ENGLISH_SEARCH_TERMS`, not `criteria.toml`.
      Added "analista de inteligencia comercial" (Spanish) and 9 English terms
      (Power BI Developer, BI Developer, Data Visualization Analyst, Insights
      Analyst, Operations Data Analyst, Supply Chain Data Analyst, Business
      Systems Analyst, SAP Data Analyst, Automation Analyst, People Analytics)
      — "Reporting Analyst" was already there.
- [x] **Phase 6 — Tests & verify.** `test_criteria.py`: replaced the 3
      bool-based English tests with 7 new ones covering both tiers, including
      the 3 phrases Kevin/ChatGPT named as previously-misclassified
      ("professional English", "English required", "strong communication
      skills in English") — all land in `indeterminate`, not `reject`; also a
      reject-wins-over-indeterminate case. `test_filters.py`: gate test updated
      + new test proving ambiguous phrasing is kept, not dropped.
      `test_scoring.py`: `confirm_english` seeding (both AI paths) + a test
      proving `validate()` never demotes for indeterminate. `test_pipeline.py`:
      full-run test now asserts `result.funnel` contents; fixed `AdvancedEnglish`
      → `EnglishRequirementCriteria` in its synthetic `Criteria` builder (same
      fix needed in `test_scoring.py`). **385 tests passing** (377 baseline +
      8 net new).
- [x] **Phase 7 — Close.** Docs updated (`DATA-CONTRACTS.md`: `Job`/`RunResult`
      tables; `EVALUATION-RUBRIC.md`: English re-check description;
      `SCRAPING-GOTCHAS.md`: one current-facing function-name reference —
      left the two historical legacy-system mentions alone). `ROADMAP.md`,
      `CHANGELOG.md` updated. Committed.

## Time log

| Date | Phase(s) | Time |
|------|----------|------|
| 2026-08-21 | 1-7 (full project, single session) | ~30 min |

**Total: ~30 min**

## Session notes

Three-tier English classification replaces the old hard-reject bool, mirroring
the existing `RemoteStatus`/`remote_evidence` pattern for consistency
(`classify_english_requirement_with_evidence`). `confirm_english` flag is
seeded at `ScoredJob`-assembly time (not gated behind AI evaluation) so it
never depends on whether the job actually reached the AI or got deferred by
the cap. Funnel diagnostic reused `gate()`'s existing per-job rejection reason
strings — no new tracking mechanism needed, just tallying what already existed.
One correction to my own charter: search terms live in `config.py`, not
`criteria.toml`. 385 tests passing. Next recommended project: **EATP-029**
(cache observability).
