# EATP-012 — Multi-provider AI layer — Checklist & time log

> Keep updated live. Tick `[ ]` -> `[x]` as you go. Record time per phase.

## Phases
### Phase 1 — Contracts & parse
- [x] base.py Provider
- [x] parse.py repair
- [x] stable-id matching
- [x] parse/id tests

### Phase 2 — Providers
- [x] groq
- [x] gemini (flash + flash-lite)
- [x] openrouter

### Phase 3 — Router & fallback
- [x] order+fallback+usage tracking
- [x] mock fallback tests

### Phase 4 — Close
- [x] offline pytest
- [ ] optional approved smoke test — skipped: Kevin has no API key yet, not a blocker
- [x] ROADMAP + notes

## Time log
| Session date | Phase | Elapsed | Notes |
|--------------|-------|---------|-------|
| 2026-08-12 | Plan + all phases | ~45 min | Single session: plan, revised per Kevin's feedback (quality-first provider order, custom prompt, key acquisition steps), then full build |

**Total project time:** ~45 min (2026-08-12)

## Session notes

Built the full multi-provider AI layer: `ai/base.py` (Provider ABC + `AiResult`), `ai/parse.py`
(tolerant JSON repair + the ADR-006 stable-id match — covers reorder/omit/duplicate/invented-id),
`ai/prompts.py` (rewritten from the rubric, not ported from legacy), `ai/usage.py` (persisted
daily-quota tracker), `ai/router.py` (fallback chain + `build_default_router()`), and
`ai/providers/{groq,gemini,openrouter}.py`.

Kevin's explicit calls, both honored: (1) `AI_PROVIDER_ORDER` is quality-first
(`gemini_flash,groq,gemini_flash_lite,openrouter`), degrading only on an actual daily-quota
error — documented as an amendment in `AI-PROVIDERS.md` and `ADR-003`. (2) The prompt is a
fresh rewrite from `EVALUATION-RUBRIC.md` with explicit hard-score-caps, not the legacy prompt
verbatim. Malformed-JSON handling (P11) lives in `ai/parse.py`, confirmed in-scope per his question.

Design note for EATP-013: `AiResult` intentionally carries no `fit` — that's derived from
`final_score` the same way `grade` is, and belongs to the scoring/guards layer, not here.

43 new tests (parse, id-match, usage, router with a scripted mock provider, and provider
internals — retry/backoff, daily-quota vs transient error classification, `response_format`
fallback — using a fake SDK client). 259/259 total pass, no live AI calls made this session
(Kevin has no API key yet; `build_default_router()` is ready for EATP-014 once he adds one).
