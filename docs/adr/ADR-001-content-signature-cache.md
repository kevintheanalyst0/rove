# ADR-001 — Content-signature cache (not site job-ids)

- **Status:** Accepted
- **Context:** The legacy permanent cache keys on each site's `job_id`. Indeed (and,
  historically, LinkedIn before its removal in EATP-027) mints a **new id daily** for
  the same reposted vacancy, so the cache never recognizes
  it and jobs like Capgemini "FBS Analyst" reappear every day (P9).
- **Decision:** Key the cache and cross-source dedup on a **content signature**:
  `sha1(normalize(company) | normalize(title) | normalize(description)[:400])`, where
  `normalize` lowercases, strips accents/punctuation, collapses whitespace, and removes
  volatile tokens (dates, "hoy", req-ids, city-of-the-day). Store `first_seen`,
  `last_seen`, and the last `final_score`. Skip re-showing/re-scoring a signature seen
  within N days (configurable).
- **Consequences:** Daily reposts are recognized regardless of volatile ids; AI budget
  isn't wasted re-scoring the same posting; the same job from two sources dedups to one.
  Risk: a genuinely-updated posting that changes its description enough gets a new
  signature — acceptable (it's effectively a new opportunity). Tune the description
  prefix length and the "seen within N days" window in EATP-003.
- **Alternatives considered:** Keep site-id keying (rejected: root cause of P9). URL-based
  keying (rejected: URLs also churn and differ across sources).
- **Update (EATP-029, P29):** the cache was invisible — Kevin had no way to tell "the
  market was slow" from "the cache is hiding a lot", and no way to inspect or reset it
  without wiping unrelated data via `reset_all_run_data()`. Added `title`/`company`/
  `source` to each record, purely for display in a new "Ver cacheadas" view, plus a
  narrow `SignatureCache.reset()` exposed via its own `/cache/reset` route. Neither
  change touches this ADR's decision: suppression still keys on `signature` alone, the
  window is still configurable and untouched, and the per-run funnel diagnostic
  (EATP-028) already tallies `cached_recently` rejections by source for free.
