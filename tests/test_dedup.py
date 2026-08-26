"""Tests for cross-source fuzzy dedup (EATP-010).

Covers the exact failure legacy's `is_duplicate` had (SCRAPING-GOTCHAS.md
#4.3): a repost with a reworded title must still collapse to one, because
the decision is company + description only — title is never read.
"""

from __future__ import annotations

from rove.models import Job
from rove.quality.dedup import dedup

_DESCRIPTION = (
    "Buscamos un Analista de Datos remoto para construir dashboards en Power BI, "
    "escribir consultas SQL y apoyar al equipo de negocio con reportes semanales "
    "sobre ventas, retencion y crecimiento. Se valora experiencia con Python."
)


def _job(**overrides) -> Job:
    defaults = {
        "source": "occ",
        "source_job_id": "1",
        "title": "Analista de Datos",
        "company": "Acme Corp",
        "description": _DESCRIPTION,
        "url": "https://example.com/1",
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_near_identical_postings_at_the_same_company_collapse_to_one():
    a = _job(source="occ", source_job_id="1")
    b = _job(source="computrabajo", source_job_id="2")

    kept, dropped = dedup([a, b])

    assert kept == [a]
    assert dropped == [b]


def test_a_reworded_title_still_collapses_the_repost_title_is_never_required():
    # The exact failure mode legacy had: same company, near-identical
    # description, but a different headline. Must still dedup.
    a = _job(title="Analista de Datos", source_job_id="1")
    b = _job(title="Data Analyst Senior - Urgente", source_job_id="2")

    kept, dropped = dedup([a, b])

    assert len(kept) == 1
    assert len(dropped) == 1


def test_different_companies_with_identical_descriptions_never_collapse():
    # Company match is required first — a shared boilerplate description
    # (e.g. two staffing-mill postings) must not merge two real employers.
    a = _job(company="Acme Corp", source_job_id="1")
    b = _job(company="Other Corp", source_job_id="2")

    kept, dropped = dedup([a, b])

    assert len(kept) == 2
    assert dropped == []


def test_genuinely_different_roles_at_the_same_company_never_collapse():
    a = _job(
        title="Data Analyst",
        description="Analiza metricas de producto usando SQL y Power BI para el equipo de crecimiento.",
        source_job_id="1",
    )
    b = _job(
        title="Financial Analyst",
        description="Construye modelos financieros en Excel, prepara forecasts y apoya al CFO en reportes trimestrales.",
        source_job_id="2",
    )

    kept, dropped = dedup([a, b])

    assert len(kept) == 2
    assert dropped == []


def test_three_reposts_across_sources_collapse_to_the_first_seen():
    first = _job(source="occ", source_job_id="1")
    second = _job(source="computrabajo", source_job_id="2")
    third = _job(source="indeed", source_job_id="3")

    kept, dropped = dedup([first, second, third])

    assert kept == [first]
    assert {job.source for job in dropped} == {"computrabajo", "indeed"}


def test_empty_description_never_matches_anything():
    a = _job(description="", source_job_id="1")
    b = _job(description="", source_job_id="2")

    kept, dropped = dedup([a, b])

    assert len(kept) == 2
    assert dropped == []
