# ADR-003 — Multi-provider AI layer with fallback (cloud-only)

- **Status:** Accepted
- **Context:** Gemini 2.5 Flash free tier was cut to ~20 requests/day (late 2025); a 503
  still consumes a call (P12). Malformed JSON occasionally breaks parsing (P11). Kevin
  wants a free alternative that does **not** run on his machine.
- **Decision:** A provider-agnostic AI layer (EATP-006) with a preference order and
  automatic fallback (`AI_PROVIDER_ORDER`, default `groq,gemini_flash_lite,openrouter,
  gemini_flash`). **Groq** is the default primary (free, no card, OpenAI-compatible, fast,
  ~1,000 req/day); **Gemini 2.5 Flash-Lite** is the first fallback (~1,000–1,500 req/day,
  huge TPM, native JSON schema). Enforce provider-native structured output; add a tolerant
  parse-and-repair fallback. Track per-provider daily usage locally to stop before wasting
  calls. All providers are cloud-hosted.
- **Consequences:** A single provider's cap no longer stalls a run for a day. Robust JSON.
  Slight complexity (adapters + router) — contained in `ai/`. Kevin must add at least a
  Groq key.
- **Alternatives considered:** Stay Gemini-only (rejected: 20/day is unusable). Local
  models/Ollama (rejected: Kevin removed them; must not run on his machine). Paid tiers
  (rejected: Kevin wants free).
