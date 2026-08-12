"""Matcher: puntuación por reglas.

Es un pre-filtro barato: calcula un score rápido para cada vacante y así
solo las mejores gastan cuota de la IA. Los pesos viven en `config`.
"""

from __future__ import annotations

from jobmatch import config
from jobmatch.models import Job


def _grade(score: int) -> str:
    if score >= 100:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def calculate_match(job: Job) -> dict:
    raw_score = 0
    title = (job.title or "").lower()
    description = (job.description or "").lower()

    matched_roles = [role for role in config.ROLE_WEIGHTS if role in title]
    for role in matched_roles:
        raw_score += config.ROLE_WEIGHTS[role]

    matched_skills = [skill for skill in config.SKILL_WEIGHTS if skill.lower() in description]
    for skill in matched_skills:
        raw_score += config.SKILL_WEIGHTS[skill]

    if job.remote:
        raw_score += config.REMOTE_BONUS

    for max_days, bonus in config.RECENCY_BONUS:
        if job.days_old <= max_days:
            raw_score += bonus
            break

    score = min(raw_score, 100)

    return {
        "raw_score": raw_score,
        "score": score,
        "grade": _grade(score),
        "matched_roles": matched_roles,
        "matched_skills": matched_skills,
        "reason": (
            f"Matched {len(matched_roles)} role indicators "
            f"and {len(matched_skills)} relevant skills."
        ),
    }
