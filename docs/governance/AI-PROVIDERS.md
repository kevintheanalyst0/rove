# AI Providers

Fixes P11 (malformed JSON) and P12 (Gemini free tier too small; 503 still charged;
want a free, cloud-hosted alternative). The design: a **provider-agnostic AI layer**
(EATP-012) with a **preference order and automatic fallback**, so a tiny quota on any
single provider never stalls a run. **Everything is cloud-hosted — nothing runs on
Kevin's machine.**

## The quota reality (verified, mid-2026 — re-check before relying on exact numbers)

Free tiers change often. As of mid-2026:

- **Google Gemini — 2.5 Flash:** free tier was **cut to ~20 requests/day** in late 2025.
  This is exactly Kevin's pain. **Do not** make 2.5 Flash the primary.
- **Google Gemini — 2.5 Flash-Lite:** far more generous free tier (**~1,000–1,500
  requests/day**, ~1M tokens/minute, 1M-token context). Native JSON-schema output. This
  is the *good* Gemini option and a strong fallback.
- **Groq:** genuinely free, **no credit card**, OpenAI-compatible endpoint, extremely
  fast (LPU, 300–800+ tok/s). Free limits are **per model, per organization**, typically
  **~30 req/min and ~1,000 req/day**, with per-model token/day caps (e.g. Llama-3.3-70B
  ~100K tokens/day; GPT-OSS-120B ~200K tokens/day). Great for short structured-JSON
  evaluations. **Recommended primary.**
- **OpenRouter:** aggregator with some `:free` models behind one key; good overflow.
- **Cerebras:** also fast/free-tier; optional extra fallback.

> A `503`/`429` still consumes a Gemini call, and daily caps are the real constraint.
> The whole point of the fallback layer is that hitting one cap just rolls to the next
> provider instead of pausing the run for a day.

## Chosen strategy

**Provider abstraction** (`ai/base.py`): a `Provider` exposes
`evaluate_batch(jobs, profile) -> list[AiResult]`, hiding SDK differences. Each concrete
provider (`groq.py`, `gemini.py`, `openrouter.py`, …) adapts its SDK/endpoint.

**Router with fallback** (`ai/router.py`): reads `AI_PROVIDER_ORDER` from `.env`
(default `gemini_flash,groq,gemini_flash_lite,openrouter` — see amendment below). For
each batch it uses the first provider that is configured **and** not over its tracked
quota; on quota/error it falls back to the next. It tracks per-provider daily usage
locally so it stops *before* wasting calls, and never retries a hard daily-quota error
against the same provider — a transient (non-daily) error only skips that provider for
the current batch, and it's tried again on the next one.

> **Amendment (Kevin, 2026-08-12):** the order below was originally chosen for
> speed/quota (Groq first). Kevin's explicit call for EATP-012: order by **quality**
> first, and only degrade once a provider's daily quota actually runs out — the north
> star is match quality (§1 mission), not raw throughput. Default order is now
> `gemini_flash, groq, gemini_flash_lite, openrouter`. Because the router falls back on
> the *real* error it receives rather than a hardcoded number, this doesn't depend on
> the exact published limits below staying accurate.

**Default primary: Gemini 2.5 Flash.** Best quality free-tier model available, native
structured output (`response_schema`), huge context — but a small daily cap (~20
req/day as of late 2025/mid-2026), so it's used first and exhausted quickly on a normal
run, then the router moves on.

**Default second: Groq.** Fast, free, no card, OpenAI-compatible, good at JSON. Use a
capable open model (e.g. `llama-3.3-70b-versatile` or `openai/gpt-oss-120b`). Keep
batches small enough to respect the per-day **token** cap, not just the request cap.

**Default third: Gemini 2.5 Flash-Lite** via `google-genai`, using native structured
output (response schema). Big daily allowance, big context — the workhorse fallback
once Flash and Groq are spent.

**Default last: OpenRouter's free models** (Llama 3.3, Qwen3, GPT-OSS, Gemma, …) — most
variable in quality and the smallest free daily cap, so it's the final overflow.

## Structured output + robust parsing (fixes P11)

- **Prefer provider-native structured output:** OpenAI-compatible `response_format`
  (JSON mode / JSON schema) on Groq/OpenRouter; `response_schema` on Gemini. This alone
  eliminates most malformed JSON.
- **Then a tolerant parse-and-repair fallback** (`ai/parse.py`): strip code fences,
  extract the first balanced JSON array/object, coerce types, clamp scores, and drop
  (never crash on) any item that can't be salvaged. Combined with per-item validation
  in the scoring layer (EATP-013, Layer 4), a bad response degrades gracefully instead
  of failing a run.

## Quota discipline (from CLAUDE.md §7 — restated because it's easy to forget)

- **Tests never call live AI.** Mock the `Provider`; feed recorded fixtures from
  `tests/fixtures/`. Build and verify the whole layer offline.
- The only live call during dev is **one tiny smoke test**, only after Kevin approves it
  in that session.
- Batch jobs to minimize call count; respect **token/day** caps, which bite before
  request/day caps on big models.

## What Kevin needs to provide

At minimum a **Groq API key** (free, no card, ~2 minutes at console.groq.com). Optionally
a Gemini key (he already has one) and/or an OpenRouter key. Put them in `.env`
(`GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`). The layer uses whatever is
present and falls back across them.
