"""Colector de LinkedIn (navegador para el listado + API guest para detalles).

El navegador lista los IDs de vacante; los detalles se bajan por HTTP con la
API pública (ver linkedin_api). Se conserva toda la lógica original: la
expansión del panel con scroll, la detección de salud de página (429), y la
coordinación de pausa global entre pestañas cuando LinkedIn limita el ritmo.

Cambios de costura:
- usa configuración y utilidades compartidas,
- LinkedIn ahora usa el PERFIL PERSISTENTE (te pide login menos veces),
- ante un login/authwall SUENA una alerta en vez de que tengas que vigilar,
- se eliminó código muerto (get_apply_url, pending_lock, SEARCH_WORKERS y el
  campo redundante apply_url).
"""

from __future__ import annotations

import os
import random
import re
import time
from queue import Queue
from threading import Event, Lock, Thread
from urllib.parse import quote

from jobmatch import config
from jobmatch.console import console
from jobmatch.models import Job
from jobmatch.storage import write_json
from jobmatch.collectors import browser, filters
from jobmatch.collectors.linkedin_api import RATE_LIMIT, get_jobs_details
from jobmatch.collectors.utils import (
    clean_text,
    detect_remote,
    is_duplicate,
    random_sleep,
)

SOURCE = "linkedin"

BASE_URL = "https://www.linkedin.com/jobs/search/"
LOCATION = "México"
MAX_PAGES_PER_TERM = 10

# Coordinación de pausa global entre pestañas cuando LinkedIn limita el ritmo.
global_pause = Event()
pause_lock = Lock()


def build_search_url(query: str, page: int = 1) -> str:
    start = (page - 1) * 25
    return (
        f"{BASE_URL}"
        f"?keywords={quote(query)}"
        f"&location={quote(LOCATION)}"
        f"&sortBy=DD"
        f"&f_TPR=r86400"  # últimas 24h
        f"&f_WT=2"        # remoto
        f"&f_JT=F"        # tiempo completo
        f"&start={start}"
    )


def build_linkedin_view_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


# ---------------------------------------------------------------------------
# Login manual (con notificación)
# ---------------------------------------------------------------------------
def is_login_page(page) -> bool:
    url = (page.url or "").lower()
    return any(marker in url for marker in ("/login", "/checkpoint", "/authwall"))


def wait_for_manual_login_if_needed(page, context_label: str) -> bool:
    if not is_login_page(page):
        return True

    browser.alert_manual_intervention(
        f"LinkedIn pide iniciar sesión ({context_label}). "
        f"Inicia sesión en el navegador y pulsa ENTER."
    )
    input()
    random_sleep(1.0, 2.0)

    if is_login_page(page):
        console.error("No se completó el inicio de sesión.")
        return False
    return True


# ---------------------------------------------------------------------------
# Lectura de la página de resultados
# ---------------------------------------------------------------------------
def get_total_results_text(page) -> str:
    selectors = [
        "css:div.jobs-search-results-list__subtitle",
        "css:div.jobs-search-two-pane__subtitle",
        "css:header div",
        "css:.scaffold-layout__header",
    ]
    for selector in selectors:
        try:
            ele = page.ele(selector, timeout=2)
            if ele:
                text = clean_text(ele.text)
                if "resultado" in text.lower():
                    return text
        except Exception:
            pass
    return ""


def parse_total_results_count(results_text: str) -> int:
    if not results_text:
        return 0
    cleaned = results_text.replace(".", "").replace(",", "")
    match = re.search(r"(\d+)", cleaned)
    return int(match.group(1)) if match else 0


def page_has_no_real_results(page) -> bool:
    try:
        html = clean_text(page.html).lower()
    except Exception:
        html = ""
    markers = [
        "no se han encontrado empleos para esta búsqueda",
        "no matching jobs found",
        "no jobs found for this search",
    ]
    return any(marker in html for marker in markers)


def check_page_health(page) -> bool:
    """False si la página muestra un 429 o un error de carga de filtros."""
    try:
        html = page.html.lower()
    except Exception:
        html = ""
    markers = [
        "http error 429",
        "esta página no funciona",
        "there was an error loading filters",
        "hubo un error al cargar los filtros",
        "error al cargar los filtros",
        "we couldn't load search filters",
    ]
    return not any(marker in html for marker in markers)


def is_recommendation_card(card_text: str) -> bool:
    text = clean_text(card_text).lower()
    markers = [
        "empleos que podrían interesarte",
        "principales empleos que te recomendamos",
        "jobs you may be interested in",
        "top job picks for you",
    ]
    return any(marker in text for marker in markers)


def find_results_panel(page):
    selectors = [
        "css:div.jobs-search-results-list",
        "css:div.scaffold-layout__list",
        "css:section.scaffold-layout__list",
    ]
    for selector in selectors:
        try:
            ele = page.ele(selector, timeout=2)
            if ele:
                return ele
        except Exception:
            pass
    return None


def load_cards_from_results_panel(results_panel) -> list:
    for selector in ("css:li[data-occludable-job-id]", "css:li[data-job-id]"):
        try:
            cards = results_panel.eles(selector)
            if cards:
                return cards
        except Exception:
            pass
    return []


def expand_results_panel(results_panel) -> None:
    previous_count = 0
    stable_rounds = 0

    while stable_rounds < 2:
        current_count = len(load_cards_from_results_panel(results_panel))

        if current_count <= previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            previous_count = current_count

        try:
            results_panel.scroll.down(1200)
        except Exception:
            pass

        time.sleep(0.15)


def open_search(page, query: str, page_number: int) -> bool:
    page.get(build_search_url(query, page_number))
    page.wait.doc_loaded()
    random_sleep(0.2, 0.5)
    return wait_for_manual_login_if_needed(page, f"búsqueda '{query}' página {page_number}")


class TabBlockedError(Exception):
    def __init__(self, query: str, page_number: int):
        super().__init__()
        self.query = query
        self.page_number = page_number


def collect_term_jobs(page, query: str, start_page: int = 1) -> list[dict]:
    found_jobs: list[dict] = []

    for page_number in range(start_page, MAX_PAGES_PER_TERM + 1):
        if not open_search(page, query, page_number):
            console.debug(f"[{query}] open_search() devolvió False")
            break

        page.wait.doc_loaded()

        if global_pause.is_set():
            raise TabBlockedError(query, page_number)

        results_panel = find_results_panel(page)

        if not check_page_health(page):
            raise TabBlockedError(query, page_number)

        random_sleep(0.2, 0.4)

        if global_pause.is_set():
            raise TabBlockedError(query, page_number)

        if page_has_no_real_results(page):
            break

        if not results_panel:
            console.debug(f"[{query}] results_panel = None")
            time.sleep(10)
            if not open_search(page, query, page_number):
                break
            if global_pause.is_set():
                raise TabBlockedError(query, page_number)
            results_panel = find_results_panel(page)
            if not results_panel:
                console.debug(f"[{query}] Retry failed")
                break

        total_results = parse_total_results_count(get_total_results_text(page))

        expand_results_panel(results_panel)

        raw_cards = load_cards_from_results_panel(results_panel)
        if not raw_cards:
            console.debug(f"[{query}] raw_cards vacío")
            break

        valid_cards = []
        seen_page_ids: set[str] = set()

        for item in raw_cards:
            try:
                if is_recommendation_card(clean_text(item.text)):
                    break

                job_id = item.attr("data-occludable-job-id") or item.attr("data-job-id")
                if not job_id:
                    continue

                job_id = str(job_id).strip()
                if not job_id.isdigit() or job_id in seen_page_ids:
                    continue

                seen_page_ids.add(job_id)
                valid_cards.append(item)
            except Exception:
                continue

        page_limit = len(valid_cards)
        if total_results > 0:
            remaining = total_results - ((page_number - 1) * 25)
            if remaining <= 0:
                break
            page_limit = min(page_limit, remaining)

        cards_to_process = valid_cards[:page_limit]

        jobs_found_in_page = 0
        for item in cards_to_process:
            try:
                job_id = str(item.attr("data-occludable-job-id") or item.attr("data-job-id")).strip()
                found_jobs.append({"job_id": job_id, "query": query})
                jobs_found_in_page += 1
            except Exception:
                continue

        if jobs_found_in_page == 0:
            console.debug(f"[{query}] Sin IDs nuevos")
            break

        if len(cards_to_process) < 25:
            break

    return found_jobs


# ---------------------------------------------------------------------------
# Detalles -> vacante final
# ---------------------------------------------------------------------------
def process_single_job(job_id: str, details: dict, all_jobs: list[Job], stats: dict) -> bool:
    title = details["title"]
    company = details["company"]
    description = details["description"]
    stats["details_found"] += 1

    if filters.is_excluded_company(company):
        stats["company"] += 1
        return False
    if filters.has_excluded_title(title):
        stats["title"] += 1
        return False
    if filters.fails_conditional_title_rules(title):
        stats["conditional"] += 1
        return False
    if filters.requires_advanced_english(title, description):
        stats["english"] += 1
        return False

    if not title:
        stats["missing_title"] += 1
        return False
    if not description:
        stats["missing_description"] += 1
        return False

    top_meta = (
        f"{details['location']} | {details['posted']} | "
        f"{details['employment_type']} | {details['seniority']}"
    )

    job = Job(
        source=SOURCE,
        job_id=job_id,
        title=title,
        company=company,
        description=description,
        remote=detect_remote(f"{top_meta}\n{description}\n{title}"),
        days_old=1,  # f_TPR=r86400 limita a las últimas 24h
        posted=details["posted"],
        url=build_linkedin_view_url(job_id),
    )

    if is_duplicate(job, all_jobs):
        stats["duplicate"] += 1
        return False

    all_jobs.append(job)
    stats["saved"] += 1
    return True


def process_job_details(pending_jobs: list[dict], all_jobs: list[Job]) -> dict[str, int]:
    saved_summary: dict[str, int] = {}

    console.phase("Processing details", "📄")

    stats = {
        "pending": len(pending_jobs), "details_found": 0, "details_missing": 0,
        "rate_limit": 0, "missing_title": 0, "missing_description": 0,
        "english": 0, "company": 0, "title": 0, "conditional": 0,
        "duplicate": 0, "saved": 0,
    }

    job_ids = [job["job_id"] for job in pending_jobs]
    details_map = get_jobs_details(job_ids, max_workers=5, progress_title="Downloading job details")

    retry_jobs = []
    for pending in pending_jobs:
        job_id = pending["job_id"]
        details = details_map.get(job_id)

        if details == RATE_LIMIT:
            stats["rate_limit"] += 1
            retry_jobs.append(pending)
            continue
        if details is None:
            console.warning(f"No fue posible obtener el detalle para {job_id}")
            stats["details_missing"] += 1
            continue

        if process_single_job(job_id, details, all_jobs, stats):
            saved_summary[pending["query"]] = saved_summary.get(pending["query"], 0) + 1

    if retry_jobs:
        console.step(f"⏳ Reintentando {len(retry_jobs)} vacantes limitadas en 5s...")
        time.sleep(5)

        retry_ids = [job["job_id"] for job in retry_jobs]
        retry_details = get_jobs_details(retry_ids, max_workers=5, progress_title="Retrying rate-limited jobs")

        for pending in retry_jobs:
            details = retry_details.get(pending["job_id"])
            if details in (None, RATE_LIMIT):
                continue
            if process_single_job(pending["job_id"], details, all_jobs, stats):
                saved_summary[pending["query"]] = saved_summary.get(pending["query"], 0) + 1

    return saved_summary


class SearchProcessor:
    """Recorre los términos de búsqueda en paralelo (4 pestañas), con
    coordinación de pausa global cuando LinkedIn limita el ritmo."""

    def __init__(self, page):
        self.page = page
        self.queue: Queue = Queue()
        self.results_lock = Lock()
        self.results: list[dict] = []
        self.search_summary: dict[str, int] = {}

    def _add_terms(self) -> None:
        for term in config.SEARCH_TERMS:
            self.queue.put(term)

    def _create_tabs(self) -> list:
        return [
            self.page,
            self.page.browser.new_tab(),
            self.page.browser.new_tab(),
            self.page.browser.new_tab(),
        ]

    def _search_worker(self, page) -> None:
        while True:
            while global_pause.is_set():
                time.sleep(0.5)

            try:
                query = self.queue.get_nowait()
            except Exception:
                break

            page_number = 1
            try:
                while True:
                    try:
                        found_jobs = collect_term_jobs(page, query, start_page=page_number)
                        with self.results_lock:
                            self.results.extend(found_jobs)
                            self.search_summary[query] = len(found_jobs)
                        random_sleep(1.0, 3.0)
                        break
                    except TabBlockedError as error:
                        is_coordinator = False
                        with pause_lock:
                            if not global_pause.is_set():
                                global_pause.set()
                                is_coordinator = True
                                console.warning("LinkedIn rate limit detected")

                        if is_coordinator:
                            wait_time = 40 + random.uniform(0, 5)
                            console.step(f"⏸ Pausando todas las búsquedas {wait_time:.0f}s...")
                            time.sleep(wait_time)
                            global_pause.clear()
                            console.step("▶ Reanudando búsquedas...")
                        else:
                            while global_pause.is_set():
                                time.sleep(0.5)

                        query = error.query
                        page_number = error.page_number
                        continue
            finally:
                self.queue.task_done()

    def collect(self) -> tuple[list[dict], dict[str, int]]:
        self._add_terms()
        tabs = self._create_tabs()

        threads = []
        for tab in tabs:
            thread = Thread(target=self._search_worker, args=(tab,))
            thread.start()
            threads.append(thread)
            time.sleep(2)

        for thread in threads:
            thread.join()

        unique_jobs = []
        seen: set[str] = set()
        for job in self.results:
            if job["job_id"] in seen:
                continue
            seen.add(job["job_id"])
            unique_jobs.append(job)

        return unique_jobs, self.search_summary


def collect() -> list[Job]:
    os.makedirs(config.DATA_DIR, exist_ok=True)

    console.header("LinkedIn Collector", "💼")
    console.phase("Searching jobs", "🔎")

    page = browser.build_page(use_profile=True)
    all_jobs: list[Job] = []

    try:
        pending_jobs, search_summary = SearchProcessor(page).collect()
        saved_summary = process_job_details(pending_jobs, all_jobs)

        console.phase("Summary", "📊")
        for term, found in search_summary.items():
            if found == 0:
                continue
            console.status(term, f"{found:>3} → {saved_summary.get(term, 0)}")
    except Exception as error:
        console.error(f"Unexpected error: {error}")
    finally:
        page.quit()

    return all_jobs


def run() -> None:
    jobs = collect()

    console.phase("Saving results", "💾")
    if jobs:
        write_json(config.source_file(SOURCE), [job.to_dict() for job in jobs])
        console.success(str(config.source_file(SOURCE)))
        console.completed("LinkedIn Collector")
    else:
        console.warning("No jobs were collected.")


if __name__ == "__main__":
    run()
