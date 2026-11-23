"""Kevin's approved answers, rendered for the runner's prompt (EATP-037).

Two sources: `data/applicant_answers.toml` (his own words, written once; local
to his PC checkout, gitignored) and the answers he dictates from his phone,
which Rove keeps on the VM (`learned_answers`). Claude answers *only* from these
plus the CV; anything else becomes a pending question. Topics Kevin keeps for
himself are listed so the model knows never to answer them.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from rove import config


def load_applicant_answers(path: Path | None = None) -> dict[str, Any]:
    """The parsed TOML, or `{}` if the file is missing or unreadable (the runner
    then simply has fewer approved answers — it never invents any)."""
    path = path or config.NIGHTLY_ANSWERS_FILE
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def render_for_prompt(applicant: dict[str, Any], learned: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    answers = applicant.get("answers", {})
    if isinstance(answers, dict) and answers:
        lines.append("Respuestas aprobadas por Kevin (úsalas tal cual, en el idioma del formulario):")
        for key, value in answers.items():
            lines.append(f"- {key}: {value}")
    if learned:
        lines.append("")
        lines.append("Respuestas que Kevin dictó antes (reutilízalas si la pregunta es la misma):")
        for item in learned:
            lines.append(f"- [{item.get('language', 'es')}] {item.get('question', '')} -> {item.get('answer', '')}")
    never = applicant.get("never_answered_by_claude", {})
    topics = never.get("topics", []) if isinstance(never, dict) else []
    if topics:
        lines.append("")
        lines.append("NUNCA contestes por Kevin (déjalas para él, salta la vacante): " + ", ".join(map(str, topics)))
    return "\n".join(lines) if lines else "(Kevin todavía no aprobó respuestas: no contestes preguntas abiertas.)"
