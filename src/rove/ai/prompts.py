"""The batch evaluation prompt (EVALUATION-RUBRIC.md, Layer 3).

Rewritten from `legacy/jobmatch/pipeline/prompts.py`, not ported verbatim
(Kevin, 2026-08-12): the rubric's hard caps are stated here as an explicit
score ceiling rather than the legacy's softer "strongly penalize" wording,
and each job is identified by its stable `signature` (ADR-006) instead of a
positional label. Final wording is tunable in EATP-013; this is a working
default, not a placeholder.
"""

from __future__ import annotations

from rove.models import Job
from rove.profile import Profile

_TEMPLATE = """\
You are an expert recruiter evaluating job postings for ONE specific candidate.
Analyze each job independently, on its own merits.

CANDIDATE PROFILE

Name: {name}
Current role: {current_role}
Background: {background}
English level: {english_level}
Based in: {location} — open to: {open_to_remote_scope}
Target roles: {target_roles}
Key skills: {skills}

Career goal:
{career_goal}

Priorities:
{priority_statement}

EVALUATION PHILOSOPHY

- Estimate the candidate's probability of being HIRED and SUCCEEDING in the role.
- Judge primarily by the DAILY RESPONSIBILITIES, not by counting matching technologies.
- A simpler role the candidate can do immediately scores HIGHER than a technically
  superior role requiring several unknown skills. Overqualification is a plus, never
  a con.
- Specialization is NOT incompatibility: similar responsibilities using a different
  tool are still a strong match.
- NEVER invent disadvantages, infer missing technologies, or penalize a junior role,
  a simple stack, or Excel/Access as the main tools.

HARD CAPS — apply even if daily responsibilities otherwise fit well; cap the score
below 30 regardless of anything else:

- The role is not genuinely remote (hybrid or onsite).
- Advanced English is mandatory for the role.
- The primary responsibilities belong to an excluded field: Accounting/Finance/
  Treasury/Payroll/Tax, Software Development/Backend/Frontend/DevOps, Linux/
  Infrastructure/Networking/Cybersecurity, Technical/Customer Support, Sales,
  Marketing, Design, Legal, or Human Resources/Recruiting.
- The role is temporary or contract-based rather than a standard hire.

SCORE GUIDE

95-100 = Ideal match. 85-94 = Strong match. 70-84 = Good match.
50-69 = Moderate match. 30-49 = Weak match. 0-29 = Poor match / hard-capped.

JOBS TO EVALUATE

Each job below has a unique "id" — an opaque string, not a sequence number. You MUST
return that EXACT id back, unchanged. Never omit, merge, split, reorder, or invent
a job or its id; return exactly one result per job given.
{jobs}

OUTPUT

Return ONLY valid JSON, no markdown, no explanation outside the JSON. Exactly this
shape:

{{
  "results": [
    {{
      "id": "<the exact id you were given>",
      "score": 0,
      "pros": ["..."],
      "contras": ["..."],
      "summary": "..."
    }}
  ]
}}

Rules:
- One result object per job given, using its exact id.
- "score" is an integer 0-100.
- "pros": explain WHY the role fits — responsibilities and business impact, not a
  restatement of the title or tech stack.
- "contras": ONLY real incompatibilities; empty array is fine and expected when there
  are none. Never list a missing technology unless the posting explicitly requires it.
  Never mention seniority, "overqualified", or repeat the title.
- "summary": the main reason for the score, in one or two sentences.
- Write "summary", "pros", and "contras" in natural, professional SPANISH. Keep
  technology/product names in their original form (Power BI, SQL, Python, Excel,
  Azure, etc.). Do not mix languages within a field.
"""

_JOB_TEMPLATE = """
[id: {signature}]
TITLE: {title}
DESCRIPTION:
{description}
---"""


def _render_jobs(jobs: list[Job]) -> str:
    return "".join(
        _JOB_TEMPLATE.format(
            signature=job.signature,
            title=job.title,
            description=job.description or "(no description provided)",
        )
        for job in jobs
    )


def build_prompt(jobs: list[Job], profile: Profile) -> str:
    """Render the full evaluation prompt for one batch of jobs."""
    return _TEMPLATE.format(
        name=profile.name,
        current_role=profile.current_role,
        background=profile.background,
        english_level=profile.english_level,
        location=profile.location,
        open_to_remote_scope=profile.open_to_remote_scope,
        target_roles=", ".join(profile.target_roles),
        skills=", ".join(
            [*profile.skills.bi_and_analytics, *profile.skills.data_and_automation]
        ),
        career_goal=profile.career_goal.strip(),
        priority_statement=profile.priority.statement.strip(),
        jobs=_render_jobs(jobs),
    )
