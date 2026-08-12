# ADR-007 — Run history + applied/dismissed tracking

- **Status:** Accepted
- **Context (proactive — Kevin didn't list this):** The legacy system overwrites its
  output each run and has no memory of past runs or of Kevin's actions. So he re-sees the
  same jobs every time, can't tell what's **new since the last run**, and can't mark a job
  **applied** or **not interested** to stop it reappearing. For a sustained job hunt this
  is a real usability gap — the tool is effectively single-use each run.
- **Decision:**
  - **Run history** (EATP-010): append each run's shown jobs (by signature + timestamp)
    to `data/history/*.jsonl`, so the UI can compute a **NEW** badge for postings unseen
    in prior runs, and so source-health can compare against each source's own baseline.
  - **Tracking** (EATP-016): let Kevin mark **Apliqué** / **No me interesa**, persisted in
    `data/tracking.jsonl`. Dismissed signatures are **hidden from future runs** (fed back
    into the pipeline's skip logic); applied jobs are marked. Remote-only + hide-dismissed
    are the default view.
- **Consequences:** The tool becomes usable over a multi-week hunt: less noise, clear
  "what's new", no re-reviewing rejected jobs. Small extra state files (gitignored).
- **Alternatives considered:** Stay stateless (rejected: re-sees everything, the P15
  "nothing good ever shows" feeling is partly just re-seeing old jobs). Browser
  localStorage (rejected: not supported in this stack; server-side is simpler + durable).
