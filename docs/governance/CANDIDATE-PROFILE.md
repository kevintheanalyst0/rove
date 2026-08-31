# Candidate Profile — Kevin Castillo

The source of truth for **who Kevin is** and **what "a good job for Kevin" means.**
EATP-002 turns this into `profile.yaml` + `criteria.yaml`. Both the pre-filter and the
AI rubric read from here. Keep this human-readable; keep the machine version in sync.

## Snapshot

- **Name:** Kevin Castillo · Puebla, MX (open to remote anywhere in MX/LatAm).
- **Current:** Process & Systems Planner / SAP MM Key User at Audi México.
- **Background:** Industrial Engineering (data analysis & process optimization),
  Instituto Tecnológico de Morelia.
- **Identity:** BI & automation professional — delivers end-to-end data solutions,
  from daily-used BI dashboards to a self-built 27-project analytics platform.

## Skills

**BI & Analytics:** Power BI · DAX · Power Query · Tableau · KPI design · executive
reporting · data modeling.
**Data & Automation:** SQL · Python · dbt · PostgreSQL · SAP MM/HANA · Power Automate ·
Power Apps · VBA · Microsoft Fabric.

## Target roles (any of these, or close cousins)

Data Analyst · Analista de Datos · Business Intelligence Analyst · Analista BI ·
Reporting Analyst · Analista de Reportes · Business Analyst · Analista de Negocios ·
Power BI Analyst · Analytics Specialist · Business Systems Analyst · Analista Funcional.

## THE PRIORITY (read this before tuning anything)

Kevin **urgently** needs a remote job of this type. Therefore:

- **Salary is not a priority.** Do not rank by comp.
- **Seniority is not a priority.** Junior/mid is fine. **Being overqualified is a
  positive, never a con.** Never mention "overqualified", "senior", or "junior" as a
  con.
- **A partial skill match is fine.** If Kevin meets ~50% of requirements and can learn
  the rest, that's a **good** match — as long as the role is genuinely his kind of work.
- **A simpler role he can do today beats a fancier role needing several unknown skills.**

## HARD dealbreakers (reject or heavily penalize — these are what Kevin cares about)

1. **Not remote.** Hybrid or onsite = reject. *Exception:* rare on-site (e.g. ~1
   day/month) is acceptable → treat as remote-ok. "2 días oficina / 3 casa" = reject.
2. **Advanced English required.** Kevin is B2. Reject roles demanding advanced/fluent/
   native/bilingual English, C1/C2, IELTS/TOEFL, interviews-in-English, CV-in-English.
   *B1/B2 "intermediate English" is fine.*
3. **Role is not actually his field.** Reject roles that are really about something
   else: graphic design, pure software engineering (backend/frontend/DevOps),
   **database administration (DBA)**, **Linux/sysadmin/infra**, networking, cybersecurity,
   QA automation, accounting/finance/treasury/payroll/tax/AP/AR as the *primary* job,
   sales, marketing, recruiting/HR, customer support, legal, clinical/health, teaching.
4. **Heavy Linux / server administration** as a core responsibility → reject.
5. **Temporary / contract-only / unpaid** → strong penalty.

## Nuance the AI/rules must respect

- **Specialization ≠ incompatibility.** A BI role in a domain Kevin hasn't worked in is
  still a strong match if the *daily work* is BI/reporting/analysis.
- **Judge by daily responsibilities, not by counting matching tools.** "Different tool,
  same job" is still a match (e.g. Looker/Qlik instead of Power BI).
- **Do not invent missing requirements or infer missing tech.** Only penalize a missing
  skill if the posting **explicitly** makes it mandatory.
- **Excel/Access as the main tool is fine**, never a con.
- **Not mentioning Power BI/SQL/Python/Tableau is fine**, never a con by itself.
- **A job title is a signal, never a verdict (ADR-009).** Judge the *full posting*, not
  the title. A real example: "Analista administrativo" was a genuinely excellent match
  that the legacy system buried because the title alone looked unremarkable — Kevin only
  found it by manually checking the cache. The mirror risk is just as real: a "Data
  Analyst" title can hide heavy Linux/frontend/DBA-admin work once you read the body.
  Only a short list of absolute categories (designer, sales, recruiting, legal, health,
  education, …) may be rejected on title alone, because no description would change
  that verdict — everything else must be judged on the full text.

## Language

- Kevin works in Spanish; search the Spanish/LatAm market first.
- English proficiency: **B2** (intermediate-high). Roles in English content are OK only
  if they don't *require* advanced English (see dealbreaker #2).

## Application data (EATP-034 — auto-apply only, never read by scoring)

Machine twin: `profile.toml`'s `[application]` table.

- **Phone:** +52 443 169 2514 · **Email:** castillok54@gmail.com
- **LinkedIn:** https://www.linkedin.com/in/kevin-castillo-844005244/
- **Portfolio:** https://kevincastilloportfolio.netlify.app/
- **GitHub:** https://github.com/kevintheanalyst0
- **Availability:** Immediate, no notice period.
- **Work authorization:** Mexican citizen, authorized to work in Mexico without
  a visa; open to remote roles for companies anywhere, always working
  physically from Mexico — never needs relocation sponsorship. **Real
  refinement from EATP-034's live smoke test (2026-08-31):** a US company's
  real "are you authorized to work in [country]?" question is genuinely
  ambiguous (Mexico-based-remote vs. that country's own work visa) — the
  full disambiguation rule now lives in `profile.toml`'s
  `work_authorization` field itself, since it needs to reach the AI prompt
  verbatim, not just this human-readable summary.
- **Relocation:** Remote-only; tolerates at most ~1 office day/month (same
  bar as dealbreaker #1 above) — not open to full relocation or hybrid.
- **Salary expectation questions — Kevin's own deliberate practice:** when a
  form only accepts a bare number (no currency/text option), always answer
  `1000` — a non-committal placeholder, never his real minimum. If free text
  is allowed and an answer is required, say salary is flexible/open to
  discussion. **Never state a real salary figure in any application.**

## One-line goal (for prompts)

> "Find genuinely remote Data Analyst / BI / Business Analyst roles where Kevin can start
> contributing now. Prioritize real fit and true remote over prestige, seniority, salary,
> or tool-for-tool matching. Overqualification is a plus. Reject non-remote, advanced-
> English-required, and out-of-field (DBA/Linux/dev/finance/design/etc.) roles."
