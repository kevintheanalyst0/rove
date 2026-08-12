"""Esquema único de datos.

Sustituye los diccionarios sueltos que cada colector construía a mano
(con claves y formas ligeramente distintas). Ahora hay una sola forma
para una vacante y una sola forma para su resultado analizado.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Job:
    """Una vacante normalizada, común a todas las fuentes."""

    source: str
    job_id: str
    title: str
    company: str = "Unknown"
    description: str = ""
    remote: bool = False
    days_old: int = 999
    posted: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        # days_old puede llegar como None desde algún scraper; se normaliza
        # a 999 para que el matcher nunca reciba None (evita un TypeError).
        days_old = data.get("days_old")
        return cls(
            source=data.get("source", ""),
            job_id=data.get("job_id", ""),
            title=data.get("title", ""),
            company=data.get("company") or "Unknown",
            description=data.get("description", ""),
            remote=bool(data.get("remote", False)),
            days_old=999 if days_old is None else days_old,
            posted=data.get("posted", ""),
            url=data.get("url", ""),
        )


@dataclass
class AnalyzedJob:
    """Resultado de una vacante tras el matcher y (opcionalmente) la IA.

    El campo `final_score` es, por decisión de diseño, el score de Gemini
    cuando la vacante pasó por la IA, y el score del matcher cuando no.
    """

    job_id: str
    title: str
    company: str
    url: str
    matcher_score: int
    ai_analyzed: bool
    gemini_score: int | None = None
    final_score: int = 0
    summary: str = ""
    pros: list[str] = field(default_factory=list)
    contras: list[str] = field(default_factory=list)
    job: dict[str, Any] = field(default_factory=dict)  # vacante original completa

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalyzedJob":
        return cls(
            job_id=data.get("job_id", ""),
            title=data.get("title", ""),
            company=data.get("company", ""),
            url=data.get("url", ""),
            matcher_score=data.get("matcher_score", 0),
            ai_analyzed=data.get("ai_analyzed", False),
            gemini_score=data.get("gemini_score"),
            final_score=data.get("final_score", 0),
            summary=data.get("summary", ""),
            pros=data.get("pros") or [],
            contras=data.get("contras") or [],
            job=data.get("job") or {},
        )
