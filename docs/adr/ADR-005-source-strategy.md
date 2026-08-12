# ADR-005 — Source strategy: keep & optimize Indeed, AND add high-signal boards

- **Status:** Accepted (revised)
- **Context:** Only 4 crowded consumer boards are used; Indeed throws captchas (P5);
  results are junky (P6) and Kevin feels good jobs are missed (P2/P3/P15). Kevin wants
  Indeed **kept and optimized**, not dropped — and also wants broader, higher-quality
  coverage.
- **Decision:** Two moves, not a trade-off.
  1. **Keep Indeed as a first-class source and optimize it** (EATP-006): stealthier
     browser, human-like pacing, reliable JSON-LD parsing, and captcha handling that is
     event-based and isolated (pauses only Indeed, never blocks the run or the terminal).
  2. **Add Tier-1 sources** with API-friendly feeds (EATP-007/008): remote-first boards
     (Remotive, RemoteOK, We Work Remotely, Himalayas) and ATS + LatAm boards
     (Greenhouse, Lever, Ashby/Workable, Get on Board, Torre). These are clean,
     captcha-free, and less picked-over — where the good remote jobs Kevin is missing
     often live.
- **Consequences:** Higher quality and broader reach without giving up Indeed's
  coverage. More collectors to maintain, but each new feed is simple JSON and Indeed is
  hardened rather than abandoned. A run's success never depends on any single source
  (source-health, EATP-011, flags a broken one).
- **Alternatives considered:** Drop Indeed and lean only on Tier-1 (rejected: Kevin wants
  it kept). Scrape the same 4 harder (rejected: more captcha, same junk, same
  competition).
