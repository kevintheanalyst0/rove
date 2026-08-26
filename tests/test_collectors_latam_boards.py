"""Tests for the LatAm job-board collectors (EATP-030): Hireline, WeRemoto,
RemotoJob. All three are sitemap/category-discovered + JSON-LD detail pages —
see each module's docstring for the live viability spike that confirmed this
shape (2026-08-21). LaPieza and Glassdoor are NOT covered here: neither
shipped this session (see ROADMAP.md Backlog) — LaPieza is a client-rendered
SPA with no discoverable API (the same dead end as Get on Board, EATP-008),
and Glassdoor returned a 403 anti-bot wall on the very first request.

No live network calls — every source is served through a mocked httpx
transport built from real page structure confirmed live while building these
collectors.
"""

from __future__ import annotations

import json

import httpx
import pytest

from rove import cancellation, config
from rove.collectors.base import Collector, CollectorRegistry, CollectorStatus
from rove.collectors.hireline import HirelineCollector
from rove.collectors.parsing import extract_job_posting_ld_json, slug_to_text
from rove.collectors.remotojob import RemotoJobCollector
from rove.collectors.weremoto import WeremotoCollector
from rove.models import RemoteStatus


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("rove.collectors.http.time.sleep", lambda seconds: None)
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def _search_terms(monkeypatch):
    monkeypatch.setattr(config, "SEARCH_TERMS", ["analista de datos"])
    monkeypatch.setattr(config, "ENGLISH_SEARCH_TERMS", ["data analyst"])


def _sitemap_xml(urls: list[str]) -> str:
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'


def _job_posting_page(
    title: str,
    company: str,
    description: str,
    *,
    date_posted: str = "2026-08-10",
    raw_newline_in_description: bool = False,
) -> str:
    """A page with the real-world decoy blocks (WebSite/Organization) BEFORE
    the JobPosting block, same order confirmed live on Hireline/RemotoJob —
    proves `extract_job_posting_ld_json` doesn't just grab the first script."""
    posting = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": title,
        "description": description,
        "hiringOrganization": {"@type": "Organization", "name": company},
        "datePosted": date_posted,
    }
    posting_json = json.dumps(posting, ensure_ascii=False)
    if raw_newline_in_description:
        # The exact RemotoJob gotcha: a literal newline inside the string
        # value, which breaks strict json.loads (confirmed live).
        posting_json = posting_json.replace("Buscamos", "Buscamos\n")
    return f"""<html><head>
        <script type="application/ld+json">{{"@type": "WebSite", "url": "https://example.com"}}</script>
        <script type="application/ld+json">{{"@type": "Organization", "name": "{company}"}}</script>
        <script type="application/ld+json">{posting_json}</script>
    </head><body></body></html>"""


# ---------------------------------------------------------------------------
# Shared helper — extract_job_posting_ld_json / slug_to_text
# ---------------------------------------------------------------------------


def test_extract_job_posting_picks_the_right_block_among_decoys():
    html = _job_posting_page("Data Analyst", "Acme", "Buscamos analista de datos con SQL.")
    posting = extract_job_posting_ld_json(html)
    assert posting is not None
    assert posting["title"] == "Data Analyst"


def test_extract_job_posting_tolerates_a_raw_newline_strict_json_would_reject():
    html = _job_posting_page(
        "Data Analyst", "Acme", "Buscamos analista.", raw_newline_in_description=True
    )
    posting = extract_job_posting_ld_json(html)
    assert posting is not None
    assert posting["title"] == "Data Analyst"


def test_extract_job_posting_returns_none_with_no_jobposting_block():
    html = '<script type="application/ld+json">{"@type": "WebSite"}</script>'
    assert extract_job_posting_ld_json(html) is None


def test_slug_to_text_normalizes_hyphens_and_underscores():
    assert slug_to_text("responsable-de_plataforma-sap") == "responsable de plataforma sap"


# ---------------------------------------------------------------------------
# Hireline
# ---------------------------------------------------------------------------

_HIRELINE_MATCH_URL = "https://hireline.io/mx/empleos/analista-de-datos-sr/12345"
_HIRELINE_OFF_TOPIC_URL = "https://hireline.io/mx/empleos/ejecutivo-de-ventas/99999"


def _hireline_transport(job_pages: dict[str, str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "sitemap_ofertas.xml" in url:
            return httpx.Response(200, text=_sitemap_xml(list(job_pages) + [_HIRELINE_OFF_TOPIC_URL]))
        if url in job_pages:
            return httpx.Response(200, text=job_pages[url])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_hireline_parses_a_real_shaped_posting_unescaping_entities(monkeypatch):
    page = _job_posting_page(
        "Analista de Datos Sr.", "Acme MX", "Requisitos&nbsp;SQL y Power BI&nbsp;avanzado."
    )
    client = httpx.Client(transport=_hireline_transport({_HIRELINE_MATCH_URL: page}))

    jobs = list(HirelineCollector(client=client).collect())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "hireline"
    assert job.title == "Analista de Datos Sr."
    assert job.company == "Acme MX"
    assert "&nbsp;" not in job.description
    assert job.source_job_id == "12345"
    assert job.url == _HIRELINE_MATCH_URL
    assert job.remote_status == RemoteStatus.UNKNOWN  # the gate decides this, not the collector


def test_hireline_never_fetches_a_slug_that_matches_no_search_term(monkeypatch):
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        fetched.append(url)
        if "sitemap_ofertas.xml" in url:
            return httpx.Response(
                200, text=_sitemap_xml([_HIRELINE_MATCH_URL, _HIRELINE_OFF_TOPIC_URL])
            )
        return httpx.Response(
            200, text=_job_posting_page("Analista de Datos Sr.", "Acme", "SQL y Power BI.")
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    list(HirelineCollector(client=client).collect())

    assert _HIRELINE_OFF_TOPIC_URL not in fetched  # filtered by slug, never fetched at all


def test_hireline_stops_fetching_once_cancellation_is_requested(monkeypatch):
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "sitemap_ofertas.xml" in url:
            return httpx.Response(
                200,
                text=_sitemap_xml(
                    [
                        "https://hireline.io/mx/empleos/analista-de-datos-uno/1",
                        "https://hireline.io/mx/empleos/analista-de-datos-dos/2",
                    ]
                ),
            )
        fetched.append(url)
        cancellation.request()
        return httpx.Response(200, text=_job_posting_page("Analista de Datos", "Acme", "SQL."))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(cancellation.RunCancelled):
        list(HirelineCollector(client=client).collect())

    assert len(fetched) == 1  # the second candidate was never fetched


# ---------------------------------------------------------------------------
# RemotoJob
# ---------------------------------------------------------------------------

_REMOTOJOB_MATCH_URL = "https://remotojob.com/oferta/analista-de-datos-senior/"
_REMOTOJOB_OFF_TOPIC_URL = "https://remotojob.com/oferta/disenador-grafico/"


def _remotojob_transport(job_pages: dict[str, str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "rj-job-sitemap1.xml" in url:
            return httpx.Response(200, text=_sitemap_xml(list(job_pages) + [_REMOTOJOB_OFF_TOPIC_URL]))
        if url in job_pages:
            return httpx.Response(200, text=job_pages[url])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_remotojob_parses_html_description_and_tolerates_the_raw_newline_gotcha():
    page = _job_posting_page(
        "Analista de Datos Senior",
        "Beta LatAm",
        "<p>Buscamos analista de datos con experiencia en SQL.</p>",
        raw_newline_in_description=True,
    )
    client = httpx.Client(transport=_remotojob_transport({_REMOTOJOB_MATCH_URL: page}))

    jobs = list(RemotoJobCollector(client=client).collect())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "remotojob"
    assert job.title == "Analista de Datos Senior"
    assert "<p>" not in job.description
    assert "Buscamos analista de datos" in job.description
    assert job.source_job_id == "analista-de-datos-senior"


def test_remotojob_never_fetches_an_off_topic_slug():
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        fetched.append(url)
        if "rj-job-sitemap1.xml" in url:
            return httpx.Response(
                200, text=_sitemap_xml([_REMOTOJOB_MATCH_URL, _REMOTOJOB_OFF_TOPIC_URL])
            )
        return httpx.Response(
            200, text=_job_posting_page("Analista de Datos Senior", "Beta", "<p>SQL.</p>")
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    list(RemotoJobCollector(client=client).collect())

    assert _REMOTOJOB_OFF_TOPIC_URL not in fetched


# ---------------------------------------------------------------------------
# WeRemoto
# ---------------------------------------------------------------------------

_WEREMOTO_JOB_URL = "https://www.weremoto.com/job-posts/id-analista-de-datos-senior"


def _weremoto_category_page(job_urls: list[str]) -> str:
    links = "".join(f'<a href="{u}">ver</a>' for u in job_urls)
    return f"<html><body>{links}</body></html>"


def test_weremoto_parses_a_real_shaped_posting_across_its_three_categories():
    page = _job_posting_page("Analista de Datos Senior", "Remote Talent LatAm", "SQL y dashboards.")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/categoria-de-trabajo/analista-de-datos" in url:
            return httpx.Response(200, text=_weremoto_category_page([_WEREMOTO_JOB_URL]))
        if "/categoria-de-trabajo/" in url:
            return httpx.Response(200, text=_weremoto_category_page([]))
        if url == _WEREMOTO_JOB_URL:
            return httpx.Response(200, text=page)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(WeremotoCollector(client=client).collect())

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "weremoto"
    assert job.title == "Analista de Datos Senior"
    assert job.company == "Remote Talent LatAm"
    assert job.source_job_id == "id-analista-de-datos-senior"


def test_weremoto_deduplicates_a_url_shared_across_two_categories():
    page = _job_posting_page("Analista de Datos Senior", "Acme", "SQL.")
    fetched_job_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/categoria-de-trabajo/" in url:
            # Same URL listed under every category, as it plausibly could be.
            return httpx.Response(200, text=_weremoto_category_page([_WEREMOTO_JOB_URL]))
        if url == _WEREMOTO_JOB_URL:
            fetched_job_pages.append(url)
            return httpx.Response(200, text=page)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    jobs = list(WeremotoCollector(client=client).collect())

    assert len(jobs) == 1
    assert len(fetched_job_pages) == 1  # fetched once, not once per category


# ---------------------------------------------------------------------------
# Registration — all three satisfy the shared Collector protocol/registry
# ---------------------------------------------------------------------------


def _empty_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".xml"):
            return httpx.Response(200, text=_sitemap_xml([]))
        return httpx.Response(200, text="<html><body></body></html>")

    return httpx.MockTransport(handler)


def test_all_three_satisfy_the_collector_protocol():
    client = httpx.Client(transport=_empty_transport())
    assert isinstance(HirelineCollector(client=client), Collector)
    assert isinstance(WeremotoCollector(client=client), Collector)
    assert isinstance(RemotoJobCollector(client=client), Collector)


def test_all_three_register_and_run_through_the_registry():
    client = httpx.Client(transport=_empty_transport())
    registry = CollectorRegistry()
    registry.register("hireline", lambda: HirelineCollector(client=client))
    registry.register("weremoto", lambda: WeremotoCollector(client=client))
    registry.register("remotojob", lambda: RemotoJobCollector(client=client))

    assert set(registry.enabled_names()) == {"hireline", "weremoto", "remotojob"}

    results = registry.run_enabled()

    assert set(results) == {"hireline", "weremoto", "remotojob"}
    for source, (jobs, result) in results.items():
        assert jobs == []
        assert result.source == source
        assert result.status == CollectorStatus.EMPTY
