"""Colector de OCC Mundial (HTTP puro, sin navegador).

Lógica de scraping idéntica a la original: se listan los IDs de oferta
desde las páginas de búsqueda y se piden los detalles a la API de OCC.
Lo que cambia es que usa las utilidades y filtros compartidos.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from jobmatch import config
from jobmatch.console import console
from jobmatch.models import Job
from jobmatch.storage import write_json
from jobmatch.collectors import filters
from jobmatch.collectors.utils import is_duplicate, make_session, parse_days_old_es

SOURCE = "occ"


def _search_url(term: str, page: int) -> str:
    base = f"https://www.occ.com.mx/empleos/de-{term}/tipo-home-office-remoto/"
    return base if page == 1 else f"{base}?page={page}"


def _fetch_offer(session: requests.Session, job_id: str, existing: list[Job]) -> Job | None:
    detail_url = f"https://oferta.occ.com.mx/offer/{job_id}/d/j?ipo=41&iapo=1"

    try:
        response = session.get(detail_url, timeout=20)
    except requests.RequestException as error:
        console.debug(f"Failed {job_id}: {error}")
        return None

    if response.status_code != 200:
        return None

    try:
        offer = response.json()["o"]
    except (ValueError, KeyError) as error:
        console.debug(f"JSON error {job_id}: {error}")
        return None

    if offer.get("iwt", 0) != 2:  # no es remoto
        return None

    days_old = parse_days_old_es(offer.get("dlur", ""))
    if days_old > config.MAX_DAYS_OLD:
        return None

    title = offer.get("t", "").replace("**", "").strip()
    company = offer.get("cn") or "Unknown"

    if filters.title_is_rejected(title, company):
        return None

    description = BeautifulSoup(offer.get("ld", ""), "html.parser").get_text(" ", strip=True)

    if filters.requires_advanced_english(title, description):
        return None

    job = Job(
        source=SOURCE,
        job_id=f"OCC_{offer.get('eoi', job_id)}",
        title=title,
        company=company,
        description=description,
        remote=True,
        days_old=days_old,
        posted=offer.get("st", ""),
        url="https://www.occ.com.mx" + offer.get("ur", ""),
    )

    if is_duplicate(job, existing):
        return None

    return job


def collect() -> list[Job]:
    console.header("OCC Collector", "💼")
    console.phase("Searching jobs", "🔎")

    session = make_session()
    jobs: list[Job] = []
    seen_ids: set[str] = set()
    summary: dict[str, int] = {}

    for term in config.SEARCH_TERMS:
        before = len(jobs)

        for page in (1, 2):
            try:
                response = session.get(_search_url(term, page), timeout=20)
            except requests.RequestException as error:
                console.error(f"Search failed: {error}")
                break

            if response.status_code != 200:
                console.error(f"HTTP {response.status_code}")
                break

            job_ids = list(dict.fromkeys(re.findall(r"/empleo/oferta/(\d+)", response.text)))
            if not job_ids:
                break

            for job_id in job_ids:
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                job = _fetch_offer(session, job_id, jobs)
                if job is not None:
                    jobs.append(job)

        summary[term] = len(jobs) - before

    for term, count in summary.items():
        if count:
            console.status(term, f"{count} jobs")

    return jobs


def run() -> None:
    jobs = collect()

    console.phase("Saving results", "💾")
    write_json(config.source_file(SOURCE), [job.to_dict() for job in jobs])
    console.success(str(config.source_file(SOURCE)))
    console.completed("OCC Collector")


if __name__ == "__main__":
    run()
