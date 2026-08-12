# ADR-008 — Source health & self-check

- **Status:** Accepted
- **Context (proactive — Kevin didn't list this):** Scrapers break constantly (layout
  changes, IP blocks, captcha walls). Today a broken source just yields nothing and the
  run looks "successful" with fewer jobs — nobody notices a whole source went dark. For a
  system meant to run largely unattended (R12), silent failure is dangerous: Kevin would
  assume "no good jobs this week" when really a source was down.
- **Decision (EATP-011):** Track per-source yield and classify each source
  `ok | low | zero | error` against **its own rolling baseline** from run history, with a
  short human reason. Surface it calmly in the RunResult and UI
  ("Indeed no devolvió resultados — posible bloqueo"). A broken source never crashes the
  run; it's flagged, and the rest proceeds.
- **Consequences:** Kevin can trust "few results" means "few results", not "a source
  broke". Enables timely fixes. Minimal cost (a small classifier over data the run
  already produces).
- **Alternatives considered:** No monitoring (rejected: silent failure). Hard thresholds
  (rejected: a source's normal volume varies; baseline-relative is fairer).
