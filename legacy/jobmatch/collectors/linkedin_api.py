"""Detalles de vacantes de LinkedIn vía su endpoint público 'guest'.

Es HTTP puro y concurrente (no necesita sesión ni navegador). El colector
de LinkedIn usa esto para bajar los detalles de cada vacante tras listar
los IDs con el navegador.
"""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from jobmatch import config
from jobmatch.console import console
from jobmatch.collectors.utils import clean_text

# Centinela para señalar que LinkedIn devolvió HTTP 429 en esa vacante.
RATE_LIMIT = "RATE_LIMIT"


def _get_soup(job_id: str):
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    time.sleep(random.uniform(0.8, 1.8))

    response = requests.get(url, headers=config.DEFAULT_HEADERS, timeout=30)

    if response.status_code == 429:
        return RATE_LIMIT
    if response.status_code != 200:
        return None
    return BeautifulSoup(response.text, "html.parser")


def _text(soup, selector: str) -> str:
    tag = soup.select_one(selector)
    return clean_text(tag.get_text()) if tag else ""


def get_job_details(job_id: str):
    soup = _get_soup(job_id)
    if soup == RATE_LIMIT:
        return RATE_LIMIT
    if soup is None:
        return None

    description = ""
    description_tag = soup.select_one(".show-more-less-html__markup")
    if description_tag:
        description = clean_text(description_tag.get_text(" ", strip=True))

    employment_type = ""
    seniority = ""
    for item in soup.select(".description__job-criteria-item"):
        header = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if not header or not value:
            continue
        key = clean_text(header.get_text()).lower()
        val = clean_text(value.get_text())
        if "employment" in key:
            employment_type = val
        elif "seniority" in key:
            seniority = val

    return {
        "job_id": job_id,
        "title": _text(soup, "h2.top-card-layout__title"),
        "company": _text(soup, ".topcard__org-name-link"),
        "location": _text(soup, ".topcard__flavor--bullet"),
        "posted": _text(soup, ".posted-time-ago__text"),
        "description": description,
        "employment_type": employment_type,
        "seniority": seniority,
    }


def get_jobs_details(
    job_ids: list[str],
    max_workers: int = 5,
    progress_title: str = "Downloading job details",
) -> dict[str, object]:
    results: dict[str, object] = {}
    total = len(job_ids)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(get_job_details, jid): jid for jid in job_ids}

        for future in as_completed(future_map):
            job_id = future_map[future]
            completed += 1
            console.progress(completed, total, progress_title)

            try:
                details = future.result()
            except Exception:
                continue

            if details == RATE_LIMIT:
                results[job_id] = RATE_LIMIT
            elif details is not None:
                results[job_id] = details

    return results
