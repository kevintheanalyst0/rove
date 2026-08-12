# ADR-009 — A job title is a signal, never a standalone verdict

- **Status:** Accepted
- **Date:** 2026-08-12
- **Context:** While building EATP-002 (candidate profile & criteria), the first pass
  ported the legacy pattern of hard-rejecting a job from its **title alone** —
  including an "expanded" version that rejected ambiguous title words (`administrator`,
  `engineer`, `developer`, `manager`, `security`, `financial analyst`, ...) unless a
  data/BI word also appeared in the title. Kevin flagged this as the **same root cause**
  as one of the legacy system's worst failures: a real vacancy titled **"Analista
  administrativo"** was genuinely excellent once you read the full description, but the
  old system scored it low from the title alone and it never even surfaced in the app —
  Kevin only found it by manually inspecting the cache in VS Code. The mirror failure is
  just as real: a posting titled **"Data Analyst"** can hide heavy Linux/frontend/
  DBA-admin requirements once you read the body, and a title-based free pass would let
  it through undetected. In his words: *"no podemos guiarnos tan solo con el título...
  es necesario analizar la vacante entera. El título es útil, pero tampoco es una
  sentencia definitiva."*
- **Decision:** Split title-based signals into two tiers, everywhere in the system:
  1. **Absolute categories** (`criteria.toml` → `excluded_title_keywords`) — a short,
     unambiguous list (designer/UX, sales, marketing, recruiting/HR, legal, health,
     education, government, call-center/customer-support, bookkeeper/payroll/accounts-
     payable, unpaid/contract-type, and similar) where **no description could change the
     verdict**. These, and only these, may hard-reject a job from its title before the
     description is ever read (`criteria.title_is_rejected()`).
  2. **Ambiguous / caution words** (`criteria.toml` → `title_caution_words`, exposed via
     `criteria.title_caution_flags()`) — words like `administrator`, `engineer`,
     `developer`, `manager`, `specialist`, `coordinator`, `operations`, `security`,
     `financial analyst`. These are **advisory only**. They must never block a job from
     reaching the stages that read its full text (the matcher in EATP-013, the AI deep-
     eval in EATP-012/013). A plain, unremarkable title is not proof of a bad job.

  Symmetrically, a title that *looks* like a perfect match (containing "Data Analyst",
  "Business Intelligence", etc.) is not a free pass either — Layer 3's hard caps
  (`EVALUATION-RUBRIC.md`: "primary responsibilities in an excluded field → cap low")
  exist precisely to catch a friendly title hiding an off-field job, and must stay keyed
  off the full description, never the title.

- **Consequences:**
  - **Collectors (EATP-003–008):** any request-saving optimization that pre-filters
    *before* fetching a job's full detail may only use the absolute list above. When in
    doubt, fetch the description — an extra HTTP request is cheap; silently burying a
    genuinely good job is not.
  - **Quality gates (EATP-009):** `title_is_rejected()` stays deterministic and cheap,
    but deliberately narrow. Caution-flagged jobs (ambiguous title, no rescue word) pass
    Layer 1 and continue to Layer 2/3 like any other job — the flag travels with the job
    as data (e.g. into `Job`/matcher input), it does not gate.
  - **Matcher pre-filter (EATP-013):** `title_caution_flags()` may inform the matcher's
    score (e.g. a small penalty, not a reject) precisely because the matcher scores
    against the **full job text**, not the title in isolation. The matcher's own REJECT
    power (P10) must still be justified by full-text evidence, not a title heuristic
    reused verbatim.
  - **AI rubric (EATP-012/013):** the prompt must make explicit that the title is
    context, not a conclusion — judge the daily responsibilities described in the body.
  - Risk accepted: a handful of truly off-field jobs with ambiguous titles reach the AI
    instead of being filtered for free — an acceptable cost against silently losing good
    matches (Kevin's stated priority: quality of the shortlist, never at the price of
    losing genuine fits to a rigid rule).
- **Alternatives considered:** Keep the rescue-word conditional reject from the first
  EATP-002 pass (rejected: still a title-only hard verdict, would have re-buried the
  exact "Analista administrativo" case). Drop title-based filtering entirely (rejected:
  the absolute categories — "Diseñador gráfico" and the like — are genuinely free
  information Kevin confirmed himself; discarding them wastes AI quota for zero benefit).
