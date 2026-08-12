"""Colector de Indeed (navegador, Chromium vía DrissionPage).

Indeed necesita navegador porque bloquea las peticiones directas y usa
captcha. La lógica de scraping (extracción de IDs, JSON-LD, el sistema de
pestañas con hilos) es la misma de siempre; lo que cambia:
- usa configuración y utilidades compartidas,
- el perfil de Chrome es configurable (config / .env),
- aplica los filtros de calidad comunes,
- ante un captcha ahora SUENA una alerta en vez de que tengas que vigilar.
"""

from __future__ import annotations

import re
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Lock, Thread

from jobmatch import config
from jobmatch.console import console
from jobmatch.models import Job
from jobmatch.storage import write_json
from jobmatch.collectors import browser, filters
from jobmatch.collectors.utils import detect_remote, random_sleep

SOURCE = "indeed"

BASE_URL = "https://mx.indeed.com/jobs"
PAGE_SIZE = 10  # Indeed pagina de 10 en 10
MAX_PAGES_PER_TERM = 20  # tope de seguridad por término

# Coordinación de captcha entre hilos: solo un hilo pide la resolución
# manual; los demás esperan a que termine.
captcha_lock = Lock()
captcha_event = Event()
captcha_event.set()


def build_search_url(query: str, start: int = 0) -> str:
    # attr(DSQF7) es el filtro de remoto; start controla la paginación.
    return (
        f"{BASE_URL}"
        f"?q={query}"
        f"&fromage=14"
        f"&sc=0kf%3Aattr%28DSQF7%29%3B"
        f"&start={start}"
    )


def is_search_no_results(html_lower: str) -> bool:
    markers = [
        "no ha producido ningún resultado",
        "no matching jobs found",
        "no results found",
    ]
    return any(marker in html_lower for marker in markers)


def is_captcha_page(page) -> bool:
    html_lower = (page.html or "").lower()
    title_lower = (page.title or "").lower()
    markers = ["security check", "verifica que eres humano", "captcha"]
    return any(m in html_lower or m in title_lower for m in markers)


def resolve_captcha_if_needed(page, context_label: str) -> bool:
    if not is_captcha_page(page):
        return True

    acquired = captcha_lock.acquire(blocking=False)
    if acquired:
        try:
            captcha_event.clear()
            browser.alert_manual_intervention(
                f"CAPTCHA de Indeed detectado ({context_label}). "
                f"Resuélvelo en todas las pestañas abiertas y pulsa ENTER."
            )
            input()
            random_sleep(1.0, 1.5)
        finally:
            captcha_event.set()
            captcha_lock.release()
    else:
        captcha_event.wait()

    if is_captcha_page(page):
        console.error("El CAPTCHA no se pudo resolver.")
        return False
    return True


def extract_job_ids_from_search_page(page) -> list[str]:
    cards = page.eles("css:[data-testid='slider_item']")

    ordered_ids: list[str] = []
    seen: set[str] = set()

    for card in cards:
        try:
            link = card.ele("css:a[data-jk]", timeout=0)
            if not link:
                continue

            job_id = link.attr("data-jk")
            match = re.search(r'id="jobTitle-([a-f0-9]+)"', link.html or "")
            if match:
                job_id = match.group(1)

            if not job_id:
                continue

            job_id = job_id.strip()
            if job_id not in seen:
                seen.add(job_id)
                ordered_ids.append(job_id)
        except Exception:
            continue

    return ordered_ids


def get_job_ids(page, query: str) -> list[str]:
    all_ids: list[str] = []
    seen_ids: set[str] = set()
    seen_page_signatures: set[tuple[str, ...]] = set()

    page_number = 1
    start = 0

    while page_number <= MAX_PAGES_PER_TERM:
        page.get(build_search_url(query, start))

        try:
            page.wait.ele_loaded("css:[data-testid='slider_item']", timeout=5)
        except Exception:
            pass

        random_sleep(0.2, 0.4)

        if not resolve_captcha_if_needed(page, f"búsqueda '{query}' página {page_number}"):
            break

        html_lower = (page.html or "").lower()
        if is_search_no_results(html_lower):
            break

        page_job_ids = extract_job_ids_from_search_page(page)
        if not page_job_ids:
            break

        signature = tuple(page_job_ids)
        if signature in seen_page_signatures:
            break
        seen_page_signatures.add(signature)

        new_ids = 0
        for job_id in page_job_ids:
            if job_id not in seen_ids:
                seen_ids.add(job_id)
                all_ids.append(job_id)
                new_ids += 1

        if new_ids == 0:
            break
        if len(page_job_ids) < PAGE_SIZE:
            break

        page_number += 1
        start += PAGE_SIZE

    return all_ids


def extract_company_from_html(html: str) -> str:
    if not html:
        return ""

    patterns = [
        r'"hiringOrganization"\s*:\s*\{\s*"@type"\s*:\s*"Organization"\s*,\s*"name"\s*:\s*"([^"]+)"',
        r'"hiringOrganization"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fallback: meta og:description (menos fiable).
    company_pos = html.find('property="og:description"')
    if company_pos != -1:
        start = html.rfind('content="', 0, company_pos)
        if start != -1:
            start += len('content="')
            end = html.find('"', start)
            if end != -1:
                return html[start:end].strip()

    return ""


def extract_posted_from_html(html: str) -> tuple[str | None, int | None]:
    if not html:
        return None, None

    match = re.search(r'"datePublished"\s*:\s*(\d+)', html)
    if not match:
        return None, None

    try:
        posted_date = datetime.fromtimestamp(int(match.group(1)) / 1000)
        posted = posted_date.strftime("%Y-%m-%d")
        days_old = (datetime.now() - posted_date).days
        return posted, days_old
    except (ValueError, OSError, OverflowError):
        return None, None


def get_job_details(page, job_id: str) -> Job | None:
    url = f"https://mx.indeed.com/viewjob?jk={job_id}"
    page.get(url)

    if not resolve_captcha_if_needed(page, f"detalle {job_id}"):
        return None

    try:
        page.wait.ele_loaded("#jobDescriptionText", timeout=5)
    except Exception:
        pass

    random_sleep(0.2, 0.4)

    html = page.html or ""
    page_title = (page.title or "").strip()
    if not page_title or "No se encontró" in page_title:
        return None

    title = page_title.replace(" - Indeed.com", "").strip()
    if " - " in title:
        title = title.split(" - ")[0].strip()

    posted, days_old = extract_posted_from_html(html)
    if days_old is not None and days_old > 14:
        return None

    company = extract_company_from_html(html).strip()

    description = ""
    try:
        desc_ele = page.ele("#jobDescriptionText")
        if desc_ele:
            description = desc_ele.text.strip()
    except Exception:
        pass

    if not title or not description:
        return None

    # Filtros de calidad comunes.
    if filters.title_is_rejected(title, company):
        return None
    if filters.requires_advanced_english(title, description):
        return None

    return Job(
        source=SOURCE,
        job_id=job_id,
        title=title,
        company=company,
        description=description,
        remote=detect_remote(f"{title}\n{description}"),
        days_old=999 if days_old is None else days_old,
        posted=posted or "",
        url=url,
    )


def _process_details(detail_tabs, job_ids: list[str], jobs: list[Job], seen_ids: set[str]) -> None:
    """Descarga los detalles en paralelo usando varias pestañas."""
    job_queue: Queue = Queue()
    for job_id in job_ids:
        if job_id not in seen_ids:
            job_queue.put(job_id)

    results_lock = Lock()

    def worker(tab) -> None:
        while True:
            try:
                job_id = job_queue.get_nowait()
            except Empty:
                break

            try:
                job = get_job_details(tab, job_id)
                if job:
                    with results_lock:
                        if job_id not in seen_ids:
                            jobs.append(job)
                            seen_ids.add(job_id)
            except Exception as error:
                console.debug(f"Error en detalle {job_id}: {error}")
            finally:
                job_queue.task_done()

    threads = []
    for tab in detail_tabs:
        thread = Thread(target=worker, args=(tab,))
        thread.start()
        threads.append(thread)
        random_sleep(0.8, 0.8)  # evita que ambas pestañas naveguen a la vez

    for thread in threads:
        thread.join()


class _SearchProcessor:
    """Recorre los términos de búsqueda en paralelo (dos pestañas)."""

    def __init__(self, page):
        self.page = page
        self.queue: Queue = Queue()
        self.results: list[str] = []
        self.results_lock = Lock()
        self.summary: dict[str, int] = {}
        self.empty: list[str] = []
        self.summary_lock = Lock()

    def collect(self) -> list[str]:
        for term in config.SEARCH_TERMS:
            self.queue.put(term)

        def worker(tab) -> None:
            while True:
                try:
                    term = self.queue.get_nowait()
                except Empty:
                    break

                try:
                    job_ids = get_job_ids(tab, term)
                    with self.summary_lock:
                        if job_ids:
                            self.summary[term] = len(job_ids)
                        else:
                            self.empty.append(term)
                    with self.results_lock:
                        self.results.extend(job_ids)
                finally:
                    self.queue.task_done()

        search_tabs = [self.page, self.page.browser.new_tab()]

        threads = []
        for tab in search_tabs:
            thread = Thread(target=worker, args=(tab,))
            thread.start()
            threads.append(thread)
            random_sleep(0.8, 0.8)

        for thread in threads:
            thread.join()

        return list(dict.fromkeys(self.results))


def collect() -> list[Job]:
    console.header("Indeed Collector", "💼")
    # Antes de correr: cierra cualquier Chrome que use este perfil, o Chrome
    # no dejará que el script lo use al mismo tiempo.
    page = browser.build_page(use_profile=True)

    detail_tabs = [page.new_tab(), page.new_tab(), page.new_tab()]
    jobs: list[Job] = []
    seen_ids: set[str] = set()

    try:
        console.phase("Searching jobs", "🔎")
        processor = _SearchProcessor(page)
        job_ids = processor.collect()

        for term in processor.empty:
            console.warning(f"No results found for '{term}'")
        if processor.empty:
            console.blank()
        for term, count in processor.summary.items():
            console.status(term, f"{count} jobs")

        console.phase("Processing details", "📄")
        _process_details(detail_tabs, job_ids, jobs, seen_ids)
    finally:
        page.quit()

    return jobs


def run() -> None:
    jobs = collect()

    console.phase("Saving results", "💾")
    write_json(config.source_file(SOURCE), [job.to_dict() for job in jobs])
    console.success(str(config.source_file(SOURCE)))
    console.completed("Indeed Collector")


if __name__ == "__main__":
    run()
