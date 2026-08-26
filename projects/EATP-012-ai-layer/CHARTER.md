# EATP-012 — Multi-provider AI layer

**Complexity:** Medium

## Objective
A provider-agnostic AI layer with automatic fallback so a tiny free quota never stalls a run, robust structured-output parsing so malformed JSON stops breaking things, and — critically — a STABLE-ID round-trip so a job's analysis can never be mis-attributed. Cloud-only. Default primary Groq; fallback Gemini Flash-Lite.

## Problems solved
P11 (malformed JSON), P12 (Gemini 20/day; 503 charged; free cloud alt), and proactive P17 (positional VACANTE_N mapping is unsafe).

## Context to load  (read ONLY these this session)
| File | Why |
|------|-----|
| `CLAUDE.md` | Operating rules — esp. 7 quota discipline. |
| `docs/governance/AI-PROVIDERS.md` | Providers, free tiers, fallback order, structured output. |
| `docs/adr/ADR-003-ai-provider-strategy.md` | Decision + defaults. |
| `docs/adr/ADR-006-stable-id-ai-roundtrip.md` | Why ids, not positions. |
| `docs/governance/EVALUATION-RUBRIC.md` | What the AI must output (Layer 3). |
| `legacy/jobmatch/pipeline/ai.py` | Reference: Gemini calls, retry, extract_json, and the POSITIONAL VACANTE_N bug to fix. |
| `legacy/jobmatch/pipeline/prompts.py` | Reference: the batch prompt to adapt. |

## Dependencies
- **Projects:** EATP-001, EATP-002.
- **Libraries:** groq, google-genai, openai (OpenAI-compatible), tenacity.

## Scope
**In:**
- ai/base.py: Provider protocol (evaluate_batch(jobs, profile) -> list[AiResult]).
- ai/providers/{groq,gemini,openrouter}.py: enforce provider-native structured output where possible.
- ai/router.py: AI_PROVIDER_ORDER, first-available-under-quota, fallback on quota/error, per-provider daily usage tracking persisted in data/, never re-hit a daily-exhausted provider.
- ai/parse.py: tolerant parse-and-repair (strip fences, extract balanced JSON, coerce/clamp, drop unsalvageable — never crash).
- STABLE-ID round-trip: each job carries a short stable id (e.g. its signature/hash) in the prompt; results are matched back BY ID, not position; any missing/extra/duplicate id is detected and handled (P17).
- Tests with a MOCK provider + fixtures: fallback triggers on simulated 429/daily-quota; malformed responses repaired/dropped; id-mismatch (reorder/omit) is caught, never mis-attributed. NO live calls.

**Out:**
- Scoring orchestration + guards (013).
- Prompt final wording lives with the rubric (013) but a working default ships here.

## Deliverables
- src/rove/ai/{base,router,parse}.py + ai/providers/*.py
- tests/test_ai_router.py, test_ai_parse.py, test_ai_idmatch.py (mocked)

## Key design decisions & constraints
- Prefer OpenAI-compatible endpoint for Groq/OpenRouter (one client, response_format JSON); Gemini uses google-genai response schema.
- Local daily-usage tracking persists in data/ so restarts remember quota spent.
- Batch size respects TOKEN/day caps (they bite before request/day on big models).
- Match results by id; on any id mismatch, treat those items as unanalyzed rather than guessing.
- Live smoke test ONLY with Kevin's explicit OK in-session; otherwise fully offline.

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
- Which provider keys will you have? Minimum: a free Groq key (~2 min, no card). Gemini optional (you already have one).
