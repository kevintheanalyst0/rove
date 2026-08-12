# Evaluation Rubric

How a vacancy is judged, in three layers. Fixes P4/P6/P7/P10. Read together with
`CANDIDATE-PROFILE.md` (the values) and `DATA-CONTRACTS.md` (the shapes).

## Layer 1 — Hard filters (deterministic, in code) — EATP-009 (filters) + EATP-010 (cache)

Applied to every `Job`. A failure here means **reject** (the AI never sees it). No AI
judgment, no ambiguity.

1. **Exclusion lists — ADR-009: title is a signal, never a standalone verdict.** Only a
   short, **absolute** set of title/company keywords (designer, recruiter, sales, legal,
   health, education, call-center, bookkeeper/payroll, …) may hard-reject a job from its
   title alone — categories where no description could change the verdict. Ambiguous
   words (DBA/administrator, engineer, developer, backend/frontend, manager,
   specialist, …) are **advisory only** (`criteria.title_caution_flags()`): they flag a
   job for the matcher/AI to weigh against the **full** description, they never block it
   from being read. A real vacancy titled "Analista administrativo" was genuinely
   excellent and the legacy system buried it by judging the title alone — see ADR-009
   for the full story and consequences across collectors/matcher/AI.
2. **Advanced English required** → reject (phrases + C1/C2/IELTS/TOEFL regex).
3. **Remote hard-gate (ADR-002).** `remote_status` must be `remote`. Compute it as:
   - positive remote signals present (remoto/100% remoto/home office/fully remote/…), **AND**
   - **no** anti-remote signals (híbrido, presencial, "X días en oficina/casa",
     "onsite", a specific-city on-site requirement) — a hybrid phrase **overrides** a
     remote phrase.
   - ambiguous → `unknown` → not shown by default (surfaced separately as "remoto
     incierto" for Kevin to eyeball if he wants).
   - **Exception:** rare on-site like "~1 día al mes" counts as remote-ok.
4. **Staleness.** Older than the recency window → reject.
5. **Content-signature cache (ADR-001).** Seen-and-scored within N days → skip.

## Layer 2 — Matcher pre-filter (cheap rules, with REJECT power) — EATP-013

The legacy matcher only *ranked*; now it also *rejects* and *caps*. Purpose: keep AI
budget for plausible jobs (P10, P12, P14).

- Compute a fast rule score from role keywords in the title, data/BI skills in the
  description, remote confirmation, and recency (weights ported from legacy `config`,
  then tuned). Score against the **full job** (title + description) — a title-only
  score is exactly the rigidity ADR-009 rules out. `title_caution_flags()` may inform
  the score (e.g. a small penalty when unconfirmed by the description), never reject on
  their own.
- **Reject** below a floor score (clearly off-role, evidenced by more than just the title).
- **Cap** the number that proceed to AI (e.g. top N by score) so a huge scrape can't
  blow the AI quota. N is configurable; default favors quality.
- Everything that proceeds is *plausible*; the AI's job is fine judgment, not triage.

## Layer 3 — AI deep-evaluation — EATP-012/013

The AI scores each surviving job 0–100 with the profile + rubric, returning structured
`{ ai_score, fit, pros, contras, summary }` in **Spanish** (tech names stay in English).

### Scoring philosophy (goes into the prompt)

- Estimate Kevin's probability of being **hired and succeeding**.
- Judge by **daily responsibilities**, not by counting matching tools.
- A simpler role Kevin can do now **scores higher** than a superior role needing several
  unknown skills. **Overqualification is a plus.**
- Specialization ≠ incompatibility. Different tool, same job = still a match.
- **Never** invent cons, infer missing tech, or penalize junior/simple stacks/Excel.

### Hard caps the AI must honor (belt-and-suspenders with Layer 1)

- Not-remote or advanced-English-required → cap score low even if responsibilities fit.
- Primary responsibilities in an excluded field (DBA, Linux/infra, dev, finance,
  design, sales, …) → cap low.

### Score → grade (the ONE mapping)

`>=90 A+ · 80–89 A · 70–79 B · 55–69 C · <55 D` — used by matcher, AI, and UI alike.
This is the fix for "B grade with No cons": the grade always equals the number.

## Layer 4 — Post-validation guards (deterministic) — EATP-013

Run on every AI result before it's shown. These catch the exact defects Kevin saw:

- **Malformed JSON / missing fields** → repair (coerce types, clamp score 0–100) or
  drop the item (never crash the run) — pairs with the robust parser in EATP-012 (P11).
- **Contradiction strip:** remove any `contra` that is immediately cancelled by a
  positive clause, or that names a missing tech the posting didn't require, or that
  mentions seniority/overqualification. Empty `contras` is then fine.
- **Remote re-check:** if the guard's remote signal disagrees with a high AI score,
  demote and flag `remote_uncertain` (a job can't be A-grade and non-remote).
- **English re-check:** if advanced-English signals exist, cap and flag
  `english_required`.
- **Grade recompute:** always recompute `grade` from `final_score`; never trust a grade
  the AI wrote.

## Why this fixes Kevin's cases

- *Finance intern / process-engineering director scoring 90* → Layer 1 exclusion +
  Layer 2 reject + Layer 3 field-cap stop them well before the UI.
- *"B with No cons"* → single grade mapping + guard-recomputed grade.
- *Hybrid shown as remote:false but surfaced anyway* → remote is a hard gate, and
  `remote:false` can never be shown by default.
- *Capgemini daily repost* → content-signature cache in Layer 1.
