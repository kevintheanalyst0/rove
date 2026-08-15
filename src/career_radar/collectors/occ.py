"""OCC Mundial collector — HTTP-only, no browser needed.

Lists job ids from the search page (a regex over the raw HTML is enough; OCC's
listing markup doesn't expose title/company before the detail fetch, so
there's nothing for BeautifulSoup to gain there), then fetches each listing's
own JSON detail endpoint for the real title/company/description.

Deliberately NOT ported from `legacy/jobmatch/collectors/occ.py` as-is (see
CLAUDE.md golden rule 12): the legacy version hardcoded `remote=True`, dropped
jobs past `MAX_DAYS_OLD` itself, ran the English check inline, and fuzzy-
deduped within its own job list — all of that now belongs to the centralized
quality layer (EATP-009/010; see docs/governance/SCRAPING-GOTCHAS.md §4/§7).
What's kept is the site knowledge: the detail JSON endpoint, its field
mapping, and (new) real end-of-results detection instead of a fixed 2-page
cap — adopted from Computrabajo's pagination technique.

EATP-020: Kevin reported this taking ~6 min vs. legacy's ~1.5 min, despite
both being plain HTTP with no concurrency. Root cause wasn't the site — it's
that this version added `gentle_pause()` (politeness/anti-detection, absent
in legacy) before *every single* detail fetch, one at a time; with 100+ jobs
that's minutes of pure deliberate waiting. Rather than drop the pause
(legacy's zero-pacing approach isn't something to copy back — no evidence it
was actually safer, just faster), detail-fetching is now parallelized across
a small worker pool (mirrors `linkedin.py`'s `_MAX_TERM_WORKERS` /
`linkedin_api.py`'s `fetch_job_details`) — same politeness per request, far
less total wall-clock time. OCC has no login/session to protect (unlike
Indeed), so there's no extra account-risk tradeoff to weigh here.

Live-verified (2026-08-15, all 9 `config.SEARCH_TERMS`): 79.0s for 134 jobs
— down from the ~6 min Kevin measured before this fix, and faster than
legacy's own ~1.5 min benchmark.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from bs4 import BeautifulSoup
from httpx import Client, HTTPError

from career_radar import config, criteria
from career_radar.collectors.http import (
    RetryableHTTPError,
    build_client,
    gentle_pause,
    get,
)
from career_radar.collectors.parsing import clean_text, parse_days_old_es
from career_radar.models import Job

SOURCE = "occ"

_ID_RE = re.compile(r"/empleo/oferta/(\d+)")
_MAX_PAGES_PER_TERM = 5
# Plain public HTTP, no login/session at stake — safe to fetch details with
# more concurrency than Indeed's browser-tab pool.
_DETAIL_WORKERS = 5
# get() exhausts its retries and reraises either of these — a request that
# never recovers means "skip this job/page", not "crash the collector".
_REQUEST_ERRORS = (HTTPError, RetryableHTTPError)


def _search_url(term: str, page: int) -> str:
    slug = quote(term)
    base = f"https://www.occ.com.mx/empleos/de-{slug}/tipo-home-office-remoto/"
    return base if page == 1 else f"{base}?page={page}"


def _detail_url(job_id: str) -> str:
    return f"https://oferta.occ.com.mx/offer/{job_id}/d/j?ipo=41&iapo=1"


class OCCCollector:
    """Collector protocol: `name` + `collect() -> Iterator[Job]`."""

    name = SOURCE

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or build_client()

    def _job_ids_for_term(self, term: str) -> Iterator[str]:
        """Paginate until a page brings no new ids — no fixed page cap."""
        seen: set[str] = set()
        for page in range(1, _MAX_PAGES_PER_TERM + 1):
            try:
                response = get(self._client, _search_url(term, page))
            except _REQUEST_ERRORS:
                break

            ids_on_page = list(dict.fromkeys(_ID_RE.findall(response.text)))
            new_ids = [job_id for job_id in ids_on_page if job_id not in seen]
            if not new_ids:
                break

            seen.update(new_ids)
            yield from new_ids
            gentle_pause()

    def _fetch_job(self, job_id: str) -> Job | None:
        gentle_pause()
        try:
            response = get(self._client, _detail_url(job_id))
        except _REQUEST_ERRORS:
            return None

        try:
            offer = response.json()["o"]
        except (ValueError, KeyError):
            return None

        title = clean_text(offer.get("t", "").replace("**", ""))
        company = clean_text(offer.get("cn")) or "Unknown"
        if not title:
            return None

        # Cheap, absolute-list-only pre-filter (ADR-009) — never conditional.
        if criteria.title_is_rejected(title, company):
            return None

        description = clean_text(
            BeautifulSoup(offer.get("ld", ""), "html.parser").get_text(" ")
        )
        days_old = parse_days_old_es(offer.get("dlur", ""))
        posted_at = (
            (datetime.now(UTC) - timedelta(days=days_old)).date() if days_old < 999 else None
        )
        url_path = offer.get("ur", "")

        return Job(
            source=SOURCE,
            source_job_id=job_id,
            title=title,
            company=company,
            description=description,
            url=f"https://www.occ.com.mx{url_path}",
            days_old=days_old,
            posted_at=posted_at,
        )

    def collect(self) -> Iterator[Job]:
        seen_ids: set[str] = set()
        ordered_ids: list[str] = []
        for term in config.SEARCH_TERMS:
            for job_id in self._job_ids_for_term(term):
                if job_id not in seen_ids:
                    seen_ids.add(job_id)
                    ordered_ids.append(job_id)

        if not ordered_ids:
            return

        worker_count = max(1, min(_DETAIL_WORKERS, len(ordered_ids)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(self._fetch_job, job_id) for job_id in ordered_ids]
            for future in as_completed(futures):
                job = future.result()
                if job is not None:
                    yield job
