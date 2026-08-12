# ADR-002 — Remote is a hard gate, not a soft boolean

- **Status:** Accepted
- **Context:** Legacy `remote` is a bool from keyword detection; OCC/Computrabajo hardcode
  it True; nothing filters the final output. Result: 57/123 jobs in the last real run had
  `remote:false` yet were shown, and hybrid roles ("2 días en oficina") slipped through
  (P8). Remote-only is one of Kevin's hardest requirements.
- **Decision:** Replace the bool with a `remote_status` enum
  (`remote | hybrid | onsite | unknown`) computed from **positive remote signals AND the
  absence of anti-remote signals** — a hybrid/onsite phrase **overrides** a remote phrase.
  Store `remote_evidence` (the phrases that decided it) for auditability. The pipeline
  **rejects** non-remote jobs and, by default, shows only `remote_status == remote`.
  Ambiguous → `unknown`, surfaced separately as "remoto incierto", never counted as remote.
  Exception: rare on-site (e.g. "~1 día al mes") maps to remote-ok.
- **Consequences:** No more non-remote jobs masquerading as remote. Some borderline jobs
  land in `unknown` and are hidden by default — acceptable, and Kevin can opt to review
  them. Requires a small curated list of anti-remote phrases (ES + EN).
- **Alternatives considered:** Trust the source's remote filter (rejected: unreliable,
  and OCC/Computrabajo hardcode it). Keep bool + add a final filter (rejected: loses the
  hybrid-vs-onsite-vs-unknown distinction Kevin cares about).
