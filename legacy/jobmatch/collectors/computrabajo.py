"""Colector de Computrabajo (HTTP puro, sin navegador).

Lógica idéntica a la original: se recorren las tarjetas de cada página de
búsqueda y se pide la descripción a la API de Computrabajo. Mejora de
velocidad: los filtros de título/empresa se aplican sobre la tarjeta ANTES
de pedir el detalle, así se ahorran peticiones (menos tiempo, menos 429).
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from jobmatch import config
from jobmatch.console import console
from jobmatch.models import Job
from jobmatch.storage import write_json
from jobmatch.collectors import filters
from jobmatch.collectors.utils import is_duplicate, make_session, parse_days_old_es

SOURCE = "computrabajo"

# Marcador de "fin de resultados reales" en el HTML de Computrabajo.
_END_MARKER = '<div class="tc mbB pt30 pb30">'


def _search_url(term: str, page: int) -> str:
    base = f"https://mx.computrabajo.com/trabajo-de-{term}-en-remoto"
    return base if page == 1 else f"{base}?p={page}"


def _fetch_description(session: requests.Session, job_id: str) -> str:
    api_url = f"https://oferta.computrabajo.com/offer/{job_id}/d/j?ipo=2&iapo=1"

    try:
        response = session.get(api_url, timeout=10)
    except requests.RequestException as error:
        console.debug(f"Skipped job {job_id}: {error}")
        return ""

    if response.status_code != 200:
        return ""

    try:
        return response.json()["o"]["ld"]
    except (ValueError, KeyError):
        return ""


def collect() -> list[Job]:
    console.header("Computrabajo Collector", "💼")
    console.phase("Searching jobs", "🔎")

    session = make_session()
    jobs: list[Job] = []
    seen_ids: set[str] = set()
    summary: dict[str, int] = {}

    for term in config.SEARCH_TERMS:
        before = len(jobs)
        page = 1

        while True:
            try:
                response = session.get(_search_url(term, page), timeout=10)
            except requests.RequestException as error:
                console.error(f"Search failed: {error}")
                break

            html = response.text
            marker_found = _END_MARKER in html
            if marker_found:
                html = html.split(_END_MARKER)[0]

            cards = BeautifulSoup(html, "html.parser").select("article.box_offer")
            if not cards:
                break

            for card in cards:
                title_element = card.select_one("a.js-o-link.fc_base")
                if not title_element:
                    continue

                job_id = card.get("data-id")
                if not job_id or job_id in seen_ids:
                    continue

                date_element = card.select_one("p.fs13.fc_aux.mt15")
                posted_text = date_element.get_text(strip=True) if date_element else ""
                days_old = parse_days_old_es(posted_text)
                if days_old > config.MAX_DAYS_OLD:
                    continue

                seen_ids.add(job_id)

                title = title_element.get_text(strip=True)
                company_element = card.select_one("a.fc_base.t_ellipsis")
                company = company_element.get_text(strip=True) if company_element else "Unknown"

                # Filtro temprano: descartar sin pedir el detalle (ahorra una petición).
                if filters.title_is_rejected(title, company):
                    continue

                description = _fetch_description(session, job_id)

                if filters.requires_advanced_english(title, description):
                    continue

                job = Job(
                    source=SOURCE,
                    job_id=f"CT_{job_id}",
                    title=title,
                    company=company,
                    description=description,
                    remote=True,
                    days_old=days_old,
                    posted=posted_text,
                    url="https://mx.computrabajo.com" + title_element.get("href"),
                )

                if is_duplicate(job, jobs):
                    continue

                jobs.append(job)

            if marker_found:
                break
            page += 1

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
    console.completed("Computrabajo Collector")


if __name__ == "__main__":
    run()
