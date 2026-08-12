# ADR-006 — Stable-id round-trip for AI evaluation (not positional)

- **Status:** Accepted
- **Context (proactive — Kevin didn't list this):** The legacy AI step labels jobs in
  the prompt as `VACANTE_1`, `VACANTE_2`, … and matches the AI's results back **by
  position/order**. If the model reorders, merges, drops, or duplicates an item — which
  LLMs do occasionally — the wrong analysis silently attaches to the wrong job. Kevin
  would have no way to notice; a job could show pros/contras that belong to a different
  posting. This is a correctness bug, not just a robustness one.
- **Decision:** Give each job a **short stable id** (its content signature / hash) that
  travels in the prompt, and **match results back by id, never by position.** Detect any
  missing/extra/duplicate id and treat those items as *unanalyzed* (fall back to the
  matcher score) rather than guessing. This is enforced in the AI layer (EATP-012) and
  the scoring pipeline (EATP-013), and covered by tests that simulate reordering/omission.
- **Consequences:** Analyses can never be mis-attributed; a partially-bad AI response
  degrades gracefully. Slightly larger prompts (an id per job) — negligible.
- **Alternatives considered:** Keep positional mapping (rejected: the bug). Force strict
  ordering via prompt only (rejected: not reliable enough to bet correctness on).
